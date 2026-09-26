"""Client for ARCONEL's public statistics reports (`reportes.arconel.gob.ec`)
— the electricity regulator's report builder: distributor balances, energy
bought/sold/produced, losses, billing, infrastructure (substations, lines,
meters), service-quality indicators, 1998 to the current year, no login.

Protocol mapped in docs/RESEARCH.md § Vigésima pasada (2026-09-06) and the
pagination rule confirmed in § Trigésimo segunda pasada (2026-09-25). In
short, it is ASP.NET WebForms + MS AJAX UpdatePanels + an SSRS
ReportViewer 11 control:

1. GET `/` seeds `__VIEWSTATE`/`__VIEWSTATEGENERATOR`/`__EVENTVALIDATION`.
2. One async postback per filter, in order: `dpTipo`, `dpAnio`, optional
   `dpMes`, `dpGrupoEmpresa`. Each answer is an MS AJAX "delta"
   (`len|type|id|content|` blocks) carrying the new hidden fields.
3. "Generar Reporte" returns only the viewer's shell; the first page arrives
   in a second postback the viewer's JS normally fires by itself
   (`...$ctl09$Reserved_AsyncLoadTarget`).
4. Each further page is `__doPostBack` on the Next button's wrapper div
   (`...$ctl05$ctl00$Next$ctl00`), not the `<input>` inside it.

SSRS never knows the page count upfront: it only reveals one page ahead
("2 ?", "3 ?", ...). Every page's startup script carries
`ToolBarUpdate: {'CurrentPage':N,'TotalPages':M,'IsEstimatePageCount':bool}`;
the report is complete when the count is no longer an estimate and
CurrentPage == TotalPages. A request past the end returns an `Error`
ReportArea instead of data, and a malformed Next postback silently returns
page 1 again — so CurrentPage is checked after every step rather than
trusting the loop.

Each page is 200+ KB and can take 20+ seconds server-side, so reports are
cached for a day and page count is capped by the caller.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip
from helpers.tls import os_trust_context

logger = logging.getLogger(MAIN_LOGGER_NAME)

_URL = "https://reportes.arconel.gob.ec/"
_TIMEOUT = httpx.Timeout(90.0, connect=30.0)
_RV = "ctl00$contenidoCentro$ReportViewer1$"
_ASYNC_LOAD = _RV + "ctl09$Reserved_AsyncLoadTarget"
_NEXT = _RV + "ctl05$ctl00$Next$ctl00"
_MAX_PAGINAS_TOPE = 40

# ASP.NET's browser detection treats an unrecognized User-Agent (such as the
# project-wide `ecuador-mcp/...`) as a downlevel browser, and every async
# postback then fails with a bare `0|error|500||` — confirmed 2026-09-25.
# A generic Mozilla token is enough to get the uplevel code path.
_USER_AGENT = (
    "Mozilla/5.0 (compatible; ecuador-mcp; +https://github.com/DweskZ/EcuDataMCP)"
)

GRUPOS = {
    "todos": "1",
    "cnel": "2",
    "empresas_electricas": "3",
}

_reportes_cache = TtlCache(ttl_seconds=86400.0, max_entries=64)
_catalogo_cache = TtlCache(ttl_seconds=86400.0, max_entries=1)

# The server keeps one report per ASP.NET session, and a single report can
# take minutes; serializing keeps concurrent tool calls from hammering it.
_report_lock = asyncio.Lock()

_HIDDEN_RE = re.compile(
    r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"'
)
_RV_INPUT_RE = re.compile(
    r'<input[^>]*name="(ctl00\$contenidoCentro\$ReportViewer1\$[^"]+)"[^>]*value="([^"]*)"'
)
_SELECT_RE = r'<select[^>]*name="ctl00\${name}"([^>]*)>(.*?)</select>'
_OPTION_RE = re.compile(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)')
_TOOLBAR_RE = re.compile(
    r"'CurrentPage':(\d+),'TotalPages':(\d+),'IsEstimatePageCount':(true|false)"
)
_TABLE_TAG_RE = re.compile(r"<(/?)(table|tr|td)\b[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_NUMBER_RE = re.compile(r"^-?\d+(,\d+)?$")


class ArconelError(Exception):
    """A report request the server rejected or answered unexpectedly."""


# --- MS AJAX delta ---------------------------------------------------------


def parse_delta(text: str) -> list[tuple[str, str, str]]:
    """Split an MS AJAX delta into (type, id, content) blocks. The length
    prefix is the only reliable delimiter: content may contain `|`."""
    blocks = []
    i = 0
    while i < len(text):
        j = text.index("|", i)
        length = int(text[i:j])
        k = text.index("|", j + 1)
        m = text.index("|", k + 1)
        blocks.append((text[j + 1 : k], text[k + 1 : m], text[m + 1 : m + 1 + length]))
        i = m + 1 + length + 1
    return blocks


# --- HTML helpers ------------------------------------------------------------


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", fragment))).strip()


def _select_options(page: str, name: str) -> tuple[list[tuple[str, str]], bool]:
    """Options of a <select> and whether it is disabled."""
    m = re.search(_SELECT_RE.format(name=name), page, re.DOTALL)
    if not m:
        return [], True
    opciones = [(html.unescape(v), _text(t)) for v, t in _OPTION_RE.findall(m.group(2))]
    return opciones, 'disabled="disabled"' in m.group(1)


def _children(fragment: str, tag: str) -> list[str]:
    """Inner HTML of the top-level <tag> elements, tracking only
    table/tr/td nesting (enough for SSRS output; no HTML parser needed)."""
    out: list[str] = []
    stack: list[str] = []
    start = None
    for m in _TABLE_TAG_RE.finditer(fragment):
        closing, name = m.group(1), m.group(2).lower()
        if not closing:
            if not stack and name == tag:
                start = m.end()
            stack.append(name)
            continue
        while stack and stack[-1] != name:
            stack.pop()
        if stack:
            stack.pop()
        if not stack and name == tag and start is not None:
            out.append(fragment[start : m.start()])
            start = None
    return out


def _all_tables(fragment: str) -> list[str]:
    tables = []
    for table in _children(fragment, "table"):
        tables.append(table)
        for tr in _children(table, "tr"):
            for td in _children(tr, "td"):
                tables.extend(_all_tables(td))
    return tables


def _leaf_grid(table: str) -> list[list[str]] | None:
    """Rows of a table with no nested tables, else None (a layout wrapper)."""
    rows = []
    for tr in _children(table, "tr"):
        tds = _children(tr, "td")
        if any("<table" in td.lower() for td in tds):
            return None
        rows.append([_text(td) for td in tds])
    return rows


def extract_grid(report_area: str) -> list[list[str]]:
    """The report's data grid: SSRS nests it under 1x1 layout tables, so
    take the largest table that contains no further tables."""
    grids = [g for g in (_leaf_grid(t) for t in _all_tables(report_area)) if g]
    if not grids:
        return []
    return max(grids, key=lambda g: len(g) * max(len(r) for r in g))


def _to_value(cell: str) -> Any:
    # ARCONEL uses a decimal comma with no thousands separator
    # (`64769,242139`), so a comma always means decimals here.
    if not cell:
        return None
    if not _NUMBER_RE.match(cell):
        return cell
    return float(cell.replace(",", ".")) if "," in cell else int(cell)


# --- Session ----------------------------------------------------------------


async def _request(
    client: httpx.AsyncClient, method: str, **kwargs: Any
) -> httpx.Response:
    # The server intermittently refuses or drops connections (seen several
    # times on 2026-09-25 between otherwise successful requests); a short
    # backoff retry rides through it. Only connection-level failures are
    # retried: a POST that reached the server has already moved the
    # session's state forward.
    for attempt in range(3):
        try:
            return await client.request(method, _URL, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            if attempt == 2:
                raise
            await asyncio.sleep(2.0 * (attempt + 1))
    raise AssertionError("unreachable")


class _Session:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.hidden: dict[str, str] = {}
        self.viewer: dict[str, str] = {}
        self.sel = {"tipo": "", "anio": "0", "mes": "0", "grupo": "0"}

    def _body(self, extra: dict[str, str], manager: str) -> dict[str, str]:
        body = {
            "ctl00$ScriptManager1": manager,
            "ctl00$dpTipo": self.sel["tipo"],
            "ctl00$dpAnio": self.sel["anio"],
            "ctl00$dpMes": self.sel["mes"],
            "ctl00$dpGrupoEmpresa": self.sel["grupo"],
            "ctl00$txtObservacion": "",
            _RV + "ctl03$ctl00": "",
            _RV + "ctl03$ctl01": "",
            _RV + "ctl10": "ltr",
            _RV + "ctl11": "standards",
            _RV + "AsyncWait$HiddenCancelField": "False",
            _RV + "ToggleParam$store": "",
            _RV + "ToggleParam$collapse": "false",
            _RV + "ctl08$ClientClickedId": "",
            _RV + "ctl07$store": "",
            _RV + "ctl07$collapse": "false",
            _RV + "ctl09$VisibilityState$ctl00": "None",
            _RV + "ctl09$ScrollPosition": "",
            _RV + "ctl09$ReportControl$ctl02": "",
            _RV + "ctl09$ReportControl$ctl03": "",
            _RV + "ctl09$ReportControl$ctl04": "100",
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__ASYNCPOST": "true",
        }
        body.update(self.viewer)
        body.update(self.hidden)
        body.update(extra)
        return body

    async def start(self) -> str:
        resp = await _request(self.client, "GET")
        resp.raise_for_status()
        self.hidden = {n: html.unescape(v) for n, v in _HIDDEN_RE.findall(resp.text)}
        return resp.text

    async def post(
        self, extra: dict[str, str], manager: str
    ) -> list[tuple[str, str, str]]:
        resp = await _request(
            self.client,
            "POST",
            data=self._body(extra, manager),
            headers={
                "X-MicrosoftAjax": "Delta=true",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        resp.raise_for_status()
        if not resp.text[:1].isdigit():
            raise ArconelError(
                "respuesta inesperada del servidor (no es un delta MS AJAX)"
            )
        blocks = parse_delta(resp.text)
        for typ, id_, content in blocks:
            if typ == "hiddenField":
                self.hidden[id_] = content
            elif typ == "error" or typ == "pageRedirect":
                raise ArconelError(f"el servidor respondió {typ}: {content[:200]}")
            for name, value in _RV_INPUT_RE.findall(content):
                self.viewer[name] = html.unescape(value)
        return blocks

    async def change(self, field: str) -> str:
        target = f"ctl00${field}"
        blocks = await self.post(
            {"__EVENTTARGET": target}, f"ctl00$UpdatePanel1|{target}"
        )
        return "".join(
            c for t, i, c in blocks if t == "updatePanel" and i == "UpdatePanel1"
        )


def _panel(blocks: list[tuple[str, str, str]], suffix: str) -> str:
    return next(
        (c for t, i, c in blocks if t == "updatePanel" and i.endswith(suffix)), ""
    )


def _toolbar(blocks: list[tuple[str, str, str]]) -> tuple[int, int, bool] | None:
    for _, _, content in blocks:
        m = _TOOLBAR_RE.search(content)
        if m:
            return int(m.group(1)), int(m.group(2)), m.group(3) == "true"
    return None


def _check_option(opciones: list[tuple[str, str]], value: str, what: str) -> None:
    valid = [v for v, _ in opciones if v not in ("", "0") and not v.startswith("---")]
    if value not in valid:
        raise ArconelError(
            f"{what} no disponible: {value!r}. Opciones: {', '.join(valid)}"
        )


def _client() -> httpx.AsyncClient:
    # reportes.arconel.gob.ec omits its GoGetSSL intermediate; the bundled
    # one completes the chain with verification still on (helpers/tls.py).
    return httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        timeout=_TIMEOUT,
        verify=os_trust_context(),
        follow_redirects=True,
    )


# --- Public API --------------------------------------------------------------


async def list_arconel_reportes() -> dict[str, Any]:
    """Report types (grouped by section), years and company groups."""
    cached = _catalogo_cache.get("catalogo")
    if cached is not None:
        return cached

    async with _client() as client:
        page = await _Session(client).start()

    tipos: list[dict[str, str]] = []
    seccion = None
    for value, label in _select_options(page, "dpTipo")[0]:
        if value.startswith("---"):
            seccion = label.strip("- ").strip()
            continue
        if value:
            tipos.append({"tipo": value, "seccion": seccion or ""})
    anios = [v for v, _ in _select_options(page, "dpAnio")[0] if v != "0"]
    catalogo = {
        "tipos": tipos,
        "anios": anios,
        "grupos": {k: v for k, v in GRUPOS.items()},
        "url_fuente": _URL,
    }
    if tipos:
        _catalogo_cache.set("catalogo", catalogo)
    return catalogo


async def get_arconel_reporte(
    tipo: str,
    anio: int | str,
    grupo: str = "todos",
    mes: int | None = None,
    max_paginas: int = 10,
) -> dict[str, Any]:
    """
    Run one ARCONEL report and return its rows.

    Args:
        tipo: Report name exactly as ARCONEL lists it (see
            list_arconel_reportes), matched accent/case-insensitively.
        anio: Year, 1998 to current.
        grupo: todos | cnel | empresas_electricas.
        mes: 1-12, only for report types whose month filter is enabled.
        max_paginas: Stop after this many pages (1-40); the result says
            whether the report was complete.
    """
    grupo_value = GRUPOS.get(grupo.strip().lower())
    if grupo_value is None:
        raise ArconelError(f"grupo inválido: {grupo!r}. Opciones: {', '.join(GRUPOS)}")
    max_paginas = max(1, min(int(max_paginas), _MAX_PAGINAS_TOPE))
    anio_str = str(anio).strip()
    mes_str = str(int(mes)) if mes else "0"

    catalogo = await list_arconel_reportes()
    tipo_real = next(
        (t["tipo"] for t in catalogo["tipos"] if _strip(t["tipo"]) == _strip(tipo)),
        None,
    )
    if tipo_real is None:
        raise ArconelError(
            f"tipo de reporte desconocido: {tipo!r} (ver list_arconel_reportes)"
        )

    key = f"{tipo_real}|{anio_str}|{mes_str}|{grupo_value}|{max_paginas}"
    cached = _reportes_cache.get(key)
    if cached is not None:
        return cached

    async with _report_lock, _client() as client:
        result = await _run_report(
            client, tipo_real, anio_str, mes_str, grupo_value, max_paginas
        )

    result.update(
        {
            "tipo": tipo_real,
            "anio": anio_str,
            "mes": mes,
            "grupo": grupo,
            "url_fuente": _URL,
        }
    )
    if result["filas"]:
        _reportes_cache.set(key, result)
    return result


async def _run_report(
    client: httpx.AsyncClient,
    tipo: str,
    anio: str,
    mes: str,
    grupo: str,
    max_paginas: int,
) -> dict[str, Any]:
    s = _Session(client)
    await s.start()

    logger.info(
        "ARCONEL: generando reporte %s %s grupo=%s mes=%s", tipo, anio, grupo, mes
    )
    s.sel["tipo"] = tipo
    form = await s.change("dpTipo")

    # Years and the month filter depend on the report type; check against
    # what the server just rendered instead of a fixed list.
    _check_option(_select_options(form, "dpAnio")[0], anio, "año")
    s.sel["anio"] = anio
    form = await s.change("dpAnio")

    mes_opciones, mes_disabled = _select_options(form, "dpMes")
    if mes != "0":
        if mes_disabled:
            raise ArconelError(f"el reporte {tipo!r} no se filtra por mes")
        _check_option(mes_opciones, mes, "mes")
        s.sel["mes"] = mes
        form = await s.change("dpMes")

    _check_option(_select_options(form, "dpGrupoEmpresa")[0], grupo, "grupo")
    s.sel["grupo"] = grupo
    await s.change("dpGrupoEmpresa")

    generar = "ctl00$contenidoCentro$brtGenerar"
    await s.post({generar: "Generar Reporte"}, f"ctl00$UpdatePanel1|{generar}")
    blocks = await s.post(
        {"__EVENTTARGET": _ASYNC_LOAD}, f"{_RV}ctl09$ReportArea|{_ASYNC_LOAD}"
    )

    columnas: list[str] = []
    filas: list[list[str]] = []
    paginas = 0
    completo = False
    total_paginas = None
    while True:
        area = _panel(blocks, "ReportArea")
        if "ReportAreaContent.Error" in area:
            raise ArconelError(f"el visor devolvió un error en la página {paginas + 1}")
        paginas += 1
        for row in extract_grid(area):
            if not any(row):
                continue
            if not columnas:
                columnas = row
                continue
            if row == columnas:
                continue
            filas.append(row)

        toolbar = _toolbar(blocks)
        if toolbar is None:
            raise ArconelError(
                f"no se encontró el estado de paginación en la página {paginas}"
            )
        current, total, estimado = toolbar
        if current != paginas:
            raise ArconelError(
                f"paginación desincronizada: se esperaba la página {paginas}, llegó la {current}"
            )
        total_paginas = f"{total}{' ?' if estimado else ''}"
        if not estimado and current == total:
            completo = True
            break
        if paginas >= max_paginas:
            break

        s.viewer[_RV + "ctl09$VisibilityState$ctl00"] = "ReportPage"
        s.viewer[_RV + "ctl05$ctl00$CurrentPage"] = str(current)
        blocks = await s.post(
            {"__EVENTTARGET": _NEXT, _RV + "ctl05$ctl03$ctl00": ""},
            f"ctl00$ScriptManager1|{_NEXT}",
        )

    # SSRS pads every row and header with empty spacer columns; drop them.
    keep = [
        i
        for i, c in enumerate(columnas)
        if c or any(i < len(r) and r[i] for r in filas)
    ]
    columnas = [columnas[i] for i in keep]
    registros = [
        {
            columnas[n]: _to_value(r[i]) if i < len(r) else None
            for n, i in enumerate(keep)
        }
        for r in filas
    ]
    return {
        "columnas": columnas,
        "filas": registros,
        "total_filas": len(registros),
        "paginas_leidas": paginas,
        "paginas_total": total_paginas,
        "completo": completo,
    }
