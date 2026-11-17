"""Refresh the homepage's stored answers and terminal transcripts.

Re-runs the same tool calls that produced ``web/data/stored_answers.json`` and
``web/data/transcripts.json`` (and their ``web/en/data`` twins), in-process
(no running server), and regenerates the texts from small ES/EN templates so
the numbers stay current and are always traceable to a tool result.

Usage (from the repo root, with the project environment)::

    uv run python web/scripts/refresh_answers.py [--dry-run] [--report FILE]

Rules the script enforces:

* An answer is rebuilt only when every call succeeded and every value parsed.
  Otherwise the previous version stays byte-for-byte (answer and transcript),
  a warning is recorded and the answer keeps its own ``extracted_at`` so the
  file-level date never claims more than was verified.
* ES and EN are rendered together; a unit is applied to both or to neither.
* Exit code: 0 for a full or partial refresh, 2 for unexpected errors (broken
  JSON, ES/EN parity violation, ...), 3 when no answer could be refreshed.

The tool layer is imported lazily (``make_caller``) so the pure helpers here
can be tested with only the standard library.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import difflib
import json
import re
import sys
import tomllib
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
FILES = {
    "es_answers": WEB / "data" / "stored_answers.json",
    "en_answers": WEB / "en" / "data" / "stored_answers.json",
    "es_transcripts": WEB / "data" / "transcripts.json",
    "en_transcripts": WEB / "en" / "data" / "transcripts.json",
}

ECUADOR_TZ = timezone(timedelta(hours=-5))
CALL_TIMEOUT = 180  # seconds; the Supercias directory download is ~37 MB

Caller = Callable[..., Awaitable[dict]]


class RefreshError(Exception):
    """A call failed or a value could not be parsed: keep the old answer."""


# --------------------------------------------------------------------------
# Locale helpers
# --------------------------------------------------------------------------

MONTHS = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
}  # fmt: skip
WEEKDAYS = {
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}
ORDINAL_QUARTER = {
    "es": ["primer", "segundo", "tercer", "cuarto"],
    "en": ["first", "second", "third", "fourth"],
}
ROMAN_QUARTER = {"I": 1, "II": 2, "III": 3, "IV": 4}


def strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def norm(text: str) -> str:
    """Lowercase, accent-less, single-spaced: for tolerant substring checks."""
    return re.sub(r"\s+", " ", strip_accents(text or "").lower()).strip()


def to_decimal(value: float | str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def fmt_number(value: float | str | Decimal, decimals: int, lang: str) -> str:
    """ES ``7.728`` / ``18,2``; EN ``7,728`` / ``18.2``. Rounds half up."""
    q = Decimal(1).scaleb(-decimals)
    d = to_decimal(value).quantize(q, rounding=ROUND_HALF_UP)
    text = f"{abs(d):,.{decimals}f}"  # EN style first: 7,728.0
    if lang == "es":
        text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return ("-" if d < 0 else "") + text


def fmt_usd_millions(millions: float | Decimal, decimals: int, lang: str) -> str:
    """``US$ 7.728 millones`` / ``US$ 7,728 million`` (value already in millions)."""
    rounded = to_decimal(millions).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)
    unit = {"es": "millón" if rounded == 1 else "millones", "en": "million"}[lang]
    return f"US$ {fmt_number(rounded, decimals, lang)} {unit}"


def fmt_percent(value: float | Decimal, decimals: int, lang: str) -> str:
    """ES ``18,2 %`` (with a space), EN ``18.2%``."""
    n = fmt_number(value, decimals, lang)
    return f"{n} %" if lang == "es" else f"{n}%"


def fmt_date_long(d: date, lang: str) -> str:
    """ES ``30 de noviembre de 1957``; EN ``November 30, 1957``."""
    month = MONTHS[lang][d.month - 1]
    if lang == "es":
        return f"{d.day} de {month} de {d.year}"
    return f"{month} {d.day}, {d.year}"


def fmt_day_month(d: date, lang: str) -> str:
    month = MONTHS[lang][d.month - 1]
    return f"{d.day} de {month}" if lang == "es" else f"{month} {d.day}"


def join_list(items: list[str], lang: str, conj: dict[str, str], oxford: bool = False) -> str:
    """``a, b y c`` / ``a, b, and c``. ``conj`` maps lang to the conjunction."""
    if len(items) == 1:
        return items[0]
    head, last = ", ".join(items[:-1]), items[-1]
    comma = "," if (oxford and lang == "en" and len(items) > 2) else ""
    return f"{head}{comma} {conj[lang]} {last}"


SMALL_WORDS = {"de", "del", "la", "las", "el", "los", "y", "e", "en", "a", "al", "o", "para"}
KEEP_UPPER = {"IESS", "EP", "EPA", "ECU", "CNEL", "MSP", "SRI", "GAD", "S.A.", "C.A.", "CIA.", "LTDA."}


# Source names come unaccented and in capitals; restore accents for words we have seen.
WORD_FIXES = {
    "Pillaro": "Píllaro", "Banos": "Baños", "Fatima": "Fátima", "Canar": "Cañar",
    "Publica": "Pública", "Publico": "Público", "Canton": "Cantón", "Depuracion": "Depuración",
    "Liquidos": "Líquidos", "Autonomo": "Autónomo", "Educacion": "Educación",
    "Gestion": "Gestión", "Policia": "Policía", "Union": "Unión", "Ministerio": "Ministerio",
}  # fmt: skip


def smart_title(text: str) -> str:
    """Title-case an ALL-CAPS name, keeping connectors lowercase and known acronyms."""
    words = []
    for i, w in enumerate(re.split(r"\s+", text.strip())):
        core = w.strip(",.;:()")
        if core.upper() in KEEP_UPPER:
            words.append(w.upper())
            continue
        out = w[:1].upper() + w[1:].lower()
        if i > 0 and core.lower() in SMALL_WORDS:
            out = w.lower()
        words.append(re.sub(r"[A-Za-zÁÉÍÓÚáéíóúñ]+", lambda m: WORD_FIXES.get(m.group(0), m.group(0)), out))
    return " ".join(words)


# --------------------------------------------------------------------------
# JSON IO preserving the files' hand-formatted layout
# --------------------------------------------------------------------------


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def dump_answers(data: dict) -> str:
    """indent=2, but each ``tools`` array stays on one line (as in the repo)."""
    lines = [
        "{",
        f'  "extracted_at": {_j(data["extracted_at"])},',
        f'  "server_version": {_j(data["server_version"])},',
        '  "answers": [',
    ]
    blocks = []
    for ans in data["answers"]:
        fields = [f"      {_j(k)}: {_j(v)}" for k, v in ans.items()]
        blocks.append("    {\n" + ",\n".join(fields) + "\n    }")
    lines.append(",\n".join(blocks))
    lines += ["  ]", "}"]
    return "\n".join(lines) + "\n"


def dump_transcripts(items: list[dict]) -> str:
    """One step per line, as in the repo's hand-written file."""
    blocks = []
    for t in items:
        steps = ",\n".join(f"      {_j(s)}" for s in t["steps"])
        blocks.append(
            "  {\n"
            f'    "id": {_j(t["id"])},\n'
            f'    "label": {_j(t["label"])},\n'
            f'    "source": {_j(t["source"])},\n'
            '    "steps": [\n'
            f"{steps}\n"
            "    ]\n"
            "  }"
        )
    return "[\n" + ",\n".join(blocks) + "\n]\n"


def server_version(pyproject: Path | None = None) -> str:
    path = pyproject or ROOT / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]["version"]


# --------------------------------------------------------------------------
# Unit definition
# --------------------------------------------------------------------------


@dataclass
class Ctx:
    """Clock for the run (Ecuador local time), injectable for tests."""

    now: datetime = field(default_factory=lambda: datetime.now(ECUADOR_TZ))

    @property
    def today(self) -> date:
        return self.now.date()


@dataclass
class Unit:
    """One stored answer (and optionally one transcript) and how to rebuild it.

    ``fetch`` runs the tool calls and returns plain facts (or raises).
    ``render`` turns facts into the answer fields to overwrite, per language.
    ``transcript`` rewrites the transcript's steps in place, per language.
    """

    id: str
    fetch: Callable[[Caller, Ctx], Awaitable[dict]]
    render: Callable[[dict, str], dict]
    transcript_id: str | None = None
    transcript: Callable[[dict, str, list[dict]], None] | None = None


def find_step(steps: list[dict], kind: str, tool: str | None = None) -> dict:
    for s in steps:
        if s.get("kind") == kind and (tool is None or s.get("tool") == tool):
            return s
    raise RefreshError(f"transcript step not found: {kind} {tool or ''}".strip())


def count_label(n: int, lang: str, one_es: str, many_es: str, one_en: str, many_en: str) -> str:
    if lang == "es":
        return f"{n} {one_es if n == 1 else many_es}"
    return f"{n} {one_en if n == 1 else many_en}"


# --------------------------------------------------------------------------
# Pasaporte
# --------------------------------------------------------------------------


async def fetch_pasaporte(call: Caller, ctx: Ctx) -> dict:
    found = await call("search_tramites", query="pasaporte", institution_id="23")
    results = found.get("results") or []
    adult = [r for r in results if "mayores de 18" in norm(r.get("nombre", ""))]
    if len(adult) != 1:
        raise RefreshError(f"expected one adult passport trámite, found {len(adult)}")
    minors = any("menores de 18" in norm(r.get("nombre", "")) for r in results)
    tid = str(adult[0]["tramite_id"])
    info = await call("get_tramite_info", tramite_id=tid)
    req = norm(info.get("requisitos_obligatorios", ""))
    proc = info.get("procedimiento", "") or ""

    channels = []
    if "en linea" in req:
        channels.append("online")
    if "banco corresponsal" in req:
        channels.append("bank")
    if "banca interna" in req or "agencia presencial" in req:
        channels.append("office")
    if "comprobante de pago" not in req or not channels:
        raise RefreshError("payment proof requirement not found")
    if "cedula" not in req or "fisica o digital" not in req:
        raise RefreshError("ID card requirement not found")

    line = next((ln for ln in proc.splitlines() if "mismo día" in ln.lower()), None)
    if line is None:
        raise RefreshError("same-day delivery sentence not found")
    cities = [c for c in ("Quito", "Guayaquil", "Cuenca") if c in line]
    hours = re.search(r"(\d+)\s+a\s+(\d+)\s+horas", line)
    if not cities or not hours:
        raise RefreshError("delivery cities/hours not parsed")
    return {
        "tramite_id": tid,
        "url": info.get("url") or adult[0].get("url"),
        "n_tramites": int(found.get("total", len(results))),
        "has_minors": minors,
        "channels": channels,
        "renewal_previous": "pasaporte anterior" in req,
        "cities": cities,
        "hours": (int(hours.group(1)), int(hours.group(2))),
    }


_CHANNELS = {
    "es": {"online": "en línea", "bank": "banco corresponsal", "office": "en la agencia"},
    "en": {"online": "online", "bank": "at a partner bank", "office": "at the office"},
}


def _passport_parts(f: dict, lang: str) -> tuple[str, str, str]:
    chans = join_list([_CHANNELS[lang][c] for c in f["channels"]], lang, {"es": "o", "en": "or"}, True)
    cities = join_list(f["cities"], lang, {"es": "y", "en": "and"})
    return chans, cities, f"{f['hours'][0]} to {f['hours'][1]}"


def render_pasaporte(f: dict, lang: str) -> dict:
    chans, cities, span = _passport_parts(f, lang)
    a, b = f["hours"]
    if lang == "es":
        renew = "; si renuevas, el pasaporte anterior" if f["renewal_previous"] else ""
        text = (
            f"Si eres mayor de 18 años: comprobante de pago ({chans}) y cédula física "
            f"o digital vigente{renew}. En {cities} lo entregan el mismo día; en otras "
            f"agencias, en {a} a {b} horas."
        )
    else:
        renew = "; if you are renewing, your previous passport" if f["renewal_previous"] else ""
        text = (
            f"If you are over 18: proof of payment ({chans}) and a valid physical or "
            f"digital ID card{renew}. In {cities} it is issued the same day; at other "
            f"offices, within {span} hours."
        )
    return {"answer": text, "url": f["url"]}


def transcript_pasaporte(f: dict, lang: str, steps: list[dict]) -> None:
    chans, cities, span = _passport_parts(f, lang)
    a, b = f["hours"]
    s1 = find_step(steps, "call", "search_tramites")
    n = f["n_tramites"]
    if lang == "es":
        s1["result"] = f"{n} trámites" + (" · mayores y menores de 18 años" if f["has_minors"] else "")
    else:
        s1["result"] = f"{n} procedures" + (" · adults and minors under 18" if f["has_minors"] else "")
    find_step(steps, "call", "get_tramite_info")["args"] = f'tramite_id="{f["tramite_id"]}"'
    if lang == "es":
        prev = " y, si renuevas, el pasaporte anterior" if f["renewal_previous"] else ""
        text = (
            f"Para mayores de 18 años necesitas: **1)** el comprobante de pago ({chans}), "
            f"**2)** tu cédula física o digital vigente{prev}. En {cities} lo entregan "
            f"el mismo día; en otras agencias, de {a} a {b} horas."
        )
    else:
        prev = " and, if you are renewing, your previous passport" if f["renewal_previous"] else ""
        text = (
            f"For adults over 18 you need: **1)** the proof of payment ({chans}), "
            f"**2)** your valid physical or digital ID card{prev}. In {cities} it is "
            f"issued the same day; at other offices, within {span} hours."
        )
    find_step(steps, "answer")["text"] = text


# --------------------------------------------------------------------------
# Sismos
# --------------------------------------------------------------------------

SISMOS_DIAS = 7
SISMOS_MAG_MIN = 3.5
ECUADOR_PROVINCES = {
    "azuay", "bolivar", "canar", "carchi", "chimborazo", "cotopaxi", "el oro",
    "esmeraldas", "galapagos", "guayas", "imbabura", "loja", "los rios", "manabi",
    "morona santiago", "napo", "orellana", "pastaza", "pichincha", "santa elena",
    "santo domingo de los tsachilas", "santo domingo", "sucumbios", "tungurahua",
    "zamora chinchipe",
}  # fmt: skip
# Fallback only when the place text has no ", region" part. (lat_min, lat_max,
# lon_min, lon_max): mainland Ecuador and the Galápagos.
ECUADOR_BBOXES = [(-5.1, 1.5, -81.1, -75.1), (-1.7, 1.8, -92.2, -89.0)]
_LOC = re.compile(r"^a\s+([\d.,]+)\s*km\s+de\s+(.+?),\s*(.+)$", re.IGNORECASE)


def sismo_in_ecuador(ev: dict) -> bool:
    """True when the event is inside Ecuador.

    The place text ("a 9.59 km de Pasaje, El Oro") names the region: it is
    authoritative, so "Talara, Piura" or "Chaparral, Tolima" are out even when
    they sit near the border. Coordinates (bounding box) decide only when the
    text has no region.
    """
    loc = (ev.get("localizacion") or "").strip()
    if "," in loc:
        region = norm(loc.rsplit(",", 1)[1])
        return region in ECUADOR_PROVINCES or "galapagos" in region
    lat, lon = ev.get("latitud"), ev.get("longitud")
    if lat is None or lon is None:
        return False
    return any(a <= lat <= b and c <= lon <= d for a, b, c, d in ECUADOR_BBOXES)


def _place(ev: dict) -> tuple[str | None, str]:
    """(distance_km as '45.66' or None, 'Salinas (Santa Elena)')."""
    loc = (ev.get("localizacion") or "").strip()
    m = _LOC.match(loc)
    if m:
        return m.group(1), f"{m.group(2).strip()} ({m.group(3).strip()})"
    return None, loc


def _event_facts(ev: dict) -> dict:
    when = datetime.fromisoformat(ev["tiempo_local"])
    dist, place = _place(ev)
    return {
        "magnitud": float(ev["magnitud"]),
        "profundidad": float(ev["profundidad_km"]),
        "distancia": dist,
        "lugar": place,
        "fecha": when.date().isoformat(),
        "hora": when.strftime("%H:%M"),
        "id": ev.get("id"),
        "url": ev.get("url"),
    }


async def fetch_sismos(call: Caller, ctx: Ctx) -> dict:
    data = await call("search_sismos", dias=SISMOS_DIAS, magnitud_minima=SISMOS_MAG_MIN, limit=100)
    events = data.get("events")
    if events is None:
        raise RefreshError("search_sismos returned no 'events' field")
    total = int(data.get("total", len(events)))
    if total > len(events):
        raise RefreshError(f"only {len(events)} of {total} events returned; strongest may be missing")
    inside = [e for e in events if sismo_in_ecuador(e)]
    inside.sort(key=lambda e: (-float(e["magnitud"]), e["tiempo_utc"]))
    return {
        "total": total,
        "inside": len(inside),
        "strongest": _event_facts(inside[0]) if inside else None,
        "second": _event_facts(inside[1]) if len(inside) > 1 else None,
        "source_url": data.get("url_fuente"),
    }


def render_sismos(f: dict, lang: str, *, bold: bool = False) -> dict:
    mag_min = fmt_number(SISMOS_MAG_MIN, 1, lang)
    s, second = f["strongest"], f["second"]
    if s is None:
        if lang == "es":
            text = (
                f"No hubo sismos de magnitud {mag_min} o más dentro de Ecuador en los "
                f"últimos {SISMOS_DIAS} días, según el catálogo del IG-EPN."
            )
        else:
            text = (
                f"There were no earthquakes of magnitude {mag_min} or higher within "
                f"Ecuador in the last {SISMOS_DIAS} days, according to the IG-EPN catalog."
            )
        return {"answer": text, "url": f["source_url"]}
    d = date.fromisoformat(s["fecha"])
    mag = fmt_number(s["magnitud"], 1, lang)
    depth = fmt_number(s["profundidad"], 1, lang)
    if lang == "es":
        mag_txt = f"**magnitud {mag}**" if bold else f"magnitud {mag}"
        where = (
            f"a {fmt_number(s['distancia'].replace(',', '.'), 1, lang)} km de {s['lugar']}"
            if s["distancia"]
            else f"cerca de {s['lugar']}"
        )
        lead = "El más fuerte en Ecuador fue de" if bold else "El más fuerte en territorio ecuatoriano fue de"
        text = (
            f"{lead} {mag_txt}, {where}, el {fmt_day_month(d, lang)} a las {s['hora']}, "
            f"a {depth} km de profundidad."
        )
        if second:
            text += f" También hubo uno de {fmt_number(second['magnitud'], 1, lang)} cerca de {second['lugar']}."
    else:
        mag_txt = f"**magnitude {mag}**" if bold else f"magnitude {mag}"
        where = (
            f"{fmt_number(s['distancia'], 1, lang)} km from {s['lugar']}"
            if s["distancia"]
            else f"near {s['lugar']}"
        )
        lead = "The strongest in Ecuador was" if bold else "The strongest within Ecuadorian territory was"
        text = (
            f"{lead} {mag_txt}, {where}, on {fmt_day_month(d, lang)} at {s['hora']}, "
            f"at a depth of {depth} km."
        )
        if second:
            text += f" There was also a {fmt_number(second['magnitud'], 1, lang)} near {second['lugar']}."
    return {"answer": text, "url": s["url"] or f["source_url"]}


def transcript_sismos(f: dict, lang: str, steps: list[dict]) -> None:
    n = f["total"]
    find_step(steps, "call", "search_sismos")["result"] = (
        count_label(n, lang, "evento", "eventos", "event", "events")
        + (" · catálogo IG-EPN" if lang == "es" else " · IG-EPN catalog")
    )
    ans = find_step(steps, "answer")
    ans["text"] = render_sismos(f, lang, bold=True)["answer"]
    s = f["strongest"]
    if s and s["id"]:
        ans["cite"] = f"igepn.edu.ec · {'evento' if lang == 'es' else 'event'} {s['id']}"
    else:
        ans["cite"] = f"igepn.edu.ec · {'catálogo sísmico' if lang == 'es' else 'seismic catalog'}"


# --------------------------------------------------------------------------
# Remesas
# --------------------------------------------------------------------------

REMESAS_LABEL = "Remesas de trabajadores"


def _parse_period(p: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d{4})-(I{1,3}|IV)", p)
    if not m:
        raise RefreshError(f"unexpected quarter label: {p!r}")
    return int(m.group(1)), ROMAN_QUARTER[m.group(2)]


async def fetch_remesas(call: Caller, ctx: Ctx) -> dict:
    found = await call("search_indicadores_bce", query="remesas")
    group = next(
        (
            i
            for i in found.get("indicadores") or []
            if REMESAS_LABEL in (i.get("series_coincidentes") or [])
        ),
        None,
    )
    if group is None:
        raise RefreshError(f"no BCE group lists the series {REMESAS_LABEL!r}")
    data = await call("get_indicador_bce", id_grupo=group["id_grupo"], frecuencia="Trimestral")
    # Credit side = money coming in. The debit series carries the same label.
    series = next(
        (
            s
            for s in data.get("series") or []
            if s.get("label") == REMESAS_LABEL and "\\crédito\\" in s.get("ruta", "")
        ),
        None,
    )
    if series is None:
        raise RefreshError("credit series 'Remesas de trabajadores' not found")
    by_year: dict[int, dict[int, float]] = {}
    for period, value in (series.get("valores") or {}).items():
        if value is None:
            continue
        y, q = _parse_period(period)
        by_year.setdefault(y, {})[q] = float(value)
    complete = sorted(y for y, qs in by_year.items() if len(qs) == 4)
    if not complete:
        raise RefreshError("no complete calendar year in the series")
    year = complete[-1]
    if year - 1 not in complete:
        raise RefreshError(f"previous year {year - 1} is not complete")
    total, prev = sum(by_year[year].values()), sum(by_year[year - 1].values())
    ly, lq = max((y, q) for y, qs in by_year.items() for q in qs)
    return {
        "year": year,
        "total": total,
        "prev_year": year - 1,
        "prev_total": prev,
        "pct": (total / prev - 1) * 100,
        "last_year": ly,
        "last_quarter": lq,
        "last_value": by_year[ly][lq],
    }


def render_remesas(f: dict, lang: str) -> dict:
    pct = fmt_percent(abs(f["pct"]), 1, lang)
    total = fmt_usd_millions(f["total"], 0, lang)
    prev = fmt_usd_millions(f["prev_total"], 0, lang)
    last = fmt_usd_millions(f["last_value"], 0, lang)
    q = ORDINAL_QUARTER[lang][f["last_quarter"] - 1]
    if lang == "es":
        cmp_ = "más" if f["pct"] >= 0 else "menos"
        text = (
            f"En {f['year']} ingresaron {total} en remesas, {pct} {cmp_} que en "
            f"{f['prev_year']} ({prev}). En el {q} trimestre de {f['last_year']} llegaron {last}."
        )
    else:
        cmp_ = "more" if f["pct"] >= 0 else "less"
        text = (
            f"In {f['year']}, remittances reached {total}, {pct} {cmp_} than in "
            f"{f['prev_year']} ({prev}). In the {q} quarter of {f['last_year']}, {last} arrived."
        )
    return {"answer": text}


# --------------------------------------------------------------------------
# Corporación Favorita
# --------------------------------------------------------------------------

FAVORITA_RUC = "1790016919001"
COMPANY_TYPES = {  # source value -> (ES, EN)
    "ANONIMA": ("Sociedad anónima", "corporation (sociedad anónima)"),
    "LIMITADA": ("Compañía limitada", "limited company (compañía limitada)"),
    "ECONOMIA MIXTA": ("Compañía de economía mixta", "mixed-economy company (compañía de economía mixta)"),
}
COMPANY_STATUS = {
    "ACTIVA": ("activa", "Active"),
    "EN LIQUIDACION": ("en liquidación", "In liquidation"),
    "DISUELTA": ("disuelta", "Dissolved"),
    "INACTIVA": ("inactiva", "Inactive"),
    "CANCELADA": ("cancelada", "Cancelled"),
}
CIIU_ACTIVITY = {"G4711.01": ("comercio al por menor", "retail trade")}


def _company_key(text: str) -> str:
    return strip_accents(text or "").upper().strip()


def parse_capital(text: str) -> Decimal:
    """Supercias format ``900.000.000,00`` -> Decimal('900000000.00')."""
    try:
        return Decimal(text.replace(".", "").replace(",", "."))
    except Exception as e:
        raise RefreshError(f"capital not parsable: {text!r}") from e


async def fetch_favorita(call: Caller, ctx: Ctx) -> dict:
    data = await call("search_companias", query="CORPORACION FAVORITA")
    row = next((c for c in data.get("companias") or [] if c.get("ruc") == FAVORITA_RUC), None)
    if row is None:
        raise RefreshError(f"RUC {FAVORITA_RUC} not in search_companias results")
    tipo, estado = _company_key(row.get("tipo")), _company_key(row.get("situacion_legal"))
    if tipo not in COMPANY_TYPES:
        raise RefreshError(f"unmapped company type: {row.get('tipo')!r}")
    if estado not in COMPANY_STATUS:
        raise RefreshError(f"unmapped legal status: {row.get('situacion_legal')!r}")
    try:
        constituted = datetime.strptime(row["fecha_constitucion"], "%d/%m/%Y").date()
    except (KeyError, ValueError) as e:
        raise RefreshError("incorporation date not parsable") from e
    balance = str(row.get("ultimo_balance") or "")
    ciudad = row.get("ciudad") or row.get("canton")
    if not re.fullmatch(r"\d{4}", balance) or not ciudad or not row.get("ciiu_nivel_6"):
        raise RefreshError("city, CIIU or last balance year missing")
    # The legal representative is deliberately never read: it is personal data.
    return {
        "ruc": row["ruc"],
        "tipo": tipo,
        "estado": estado,
        "constituted": constituted.isoformat(),
        "ciudad": smart_title(ciudad),
        "capital": parse_capital(row.get("capital_suscrito", "")),
        "ciiu": row["ciiu_nivel_6"],
        "balance": balance,
    }


def _capital_label(cap: Decimal, lang: str) -> str:
    if cap >= 1_000_000:
        millions = cap / Decimal(1_000_000)
        decimals = 0 if millions == millions.to_integral_value() else 1
        return fmt_usd_millions(millions, decimals, lang)
    return f"US$ {fmt_number(cap, 0, lang)}"


def render_favorita(f: dict, lang: str) -> dict:
    i = 0 if lang == "es" else 1
    tipo, estado = COMPANY_TYPES[f["tipo"]][i], COMPANY_STATUS[f["estado"]][i]
    d = date.fromisoformat(f["constituted"])
    cap = _capital_label(f["capital"], lang)
    act = CIIU_ACTIVITY.get(f["ciiu"])
    if lang == "es":
        activity = f"{act[0]} (CIIU {f['ciiu']})" if act else f"CIIU {f['ciiu']}"
        text = (
            f"RUC {f['ruc']}. {tipo} {estado}, constituida el {fmt_date_long(d, lang)} en "
            f"{f['ciudad']}, con capital suscrito de {cap}. Actividad: {activity}. "
            f"Último balance presentado: {f['balance']}."
        )
    else:
        activity = f"{act[1]} (CIIU {f['ciiu']})" if act else f"CIIU {f['ciiu']}"
        text = (
            f"RUC {f['ruc']}. {estado} {tipo}, incorporated on {fmt_date_long(d, lang)} in "
            f"{f['ciudad']}, with subscribed capital of {cap}. Activity: {activity}. "
            f"Latest balance sheet filed: {f['balance']}."
        )
    return {"answer": text}


# --------------------------------------------------------------------------
# Compras Manta
# --------------------------------------------------------------------------


def buyer_name(raw: str, lang: str) -> str:
    up = strip_accents(raw).upper().strip()
    m = re.match(r"GOBIERNO AUTONOMO DESCENTRALIZADO MUNICIPAL DEL CANTON (.+)$", up)
    if m:
        place = smart_title(m.group(1))
        return f"el Municipio de {place}" if lang == "es" else f"the Municipality of {place}"
    m = re.match(r"HOSPITAL GENERAL (.+)$", up)
    if m:
        place = smart_title(m.group(1))
        return f"el Hospital General {place}" if lang == "es" else f"the {place} General Hospital"
    name = smart_title(raw)
    if len(name) > 60 and "," in name:  # "Empresa ... de Agua Potable, Alcantarillado, ..."
        name = name.split(",")[0]
    return name


async def fetch_compras(call: Caller, ctx: Ctx) -> dict:
    year = ctx.today.year - 1
    data = await call("get_resumen_compras", comprador="Manta", year=year)
    if data.get("parcial"):
        raise RefreshError(f"partial result ({data.get('paginas_fallidas')} failed pages)")
    procesos = data.get("total_en_fuente")
    monto = data.get("monto_total")
    con_monto = data.get("procesos_con_monto")
    if procesos is None or monto is None or con_monto is None:
        raise RefreshError("totals missing from get_resumen_compras")
    buyers = sorted(
        (b for b in data.get("compradores") or [] if b.get("monto_total") is not None),
        key=lambda b: -float(b["monto_total"]),
    )[:2]
    if procesos and not buyers:
        raise RefreshError("no buyers listed")
    return {
        "year": year,
        "procesos": int(procesos),
        "monto": float(monto),
        "con_monto": int(con_monto),
        "buyers": [(b["comprador"], float(b["monto_total"])) for b in buyers],
    }


def render_compras(f: dict, lang: str) -> dict:
    y = f["year"]
    question = {
        "es": f"¿Cuánto contrató el sector público en Manta en {y}?",
        "en": f"How much did the public sector contract in Manta in {y}?",
    }[lang]
    if f["procesos"] == 0:
        text = {
            "es": f"La fuente no registra procesos de compra pública de Manta en {y}.",
            "en": f"The source lists no public procurement procedures for Manta in {y}.",
        }[lang]
        return {"question": question, "answer": text}
    total = fmt_usd_millions(f["monto"] / 1e6, 1, lang)
    buyers = [
        f"{buyer_name(n, lang)} ({fmt_usd_millions(v / 1e6, 1, lang)})" for n, v in f["buyers"]
    ]
    if lang == "es":
        lead = "Los mayores compradores fueron" if len(buyers) > 1 else "El mayor comprador fue"
        text = (
            f"{f['procesos']} procesos por {total} (valor adjudicado o estimado de "
            f"{f['con_monto']} procesos con monto). {lead} {join_list(buyers, lang, {'es': 'y'})}."
        )
    else:
        lead = "The largest buyers were" if len(buyers) > 1 else "The largest buyer was"
        text = (
            f"{f['procesos']} procedures worth {total} (awarded or estimated value of "
            f"{f['con_monto']} procedures with an amount). {lead} {join_list(buyers, lang, {'en': 'and'})}."
        )
    return {"question": question, "answer": text}


# --------------------------------------------------------------------------
# Cortes EEASA
# --------------------------------------------------------------------------

_FECHA = re.compile(r"(\d{1,2})\s*-\s*([a-záéíóúñ]+)\s*-\s*(\d{4})", re.IGNORECASE)
def sector_label(raw: str, lang: str) -> str:
    """'BARRIO LA LIBERTAD ... PARROQUIA: PUYO' -> 'barrio La Libertad (Puyo)'."""
    t = re.sub(r"^SECTORES?:\s*", "", (raw or "").strip(), flags=re.IGNORECASE).rstrip(".")
    barrio = re.search(r"BARRIO\s+(.+?)(?:\s+DEL\s+CANT[ÓO]N|,|$)", t, re.IGNORECASE)
    area = re.search(r"PARROQUIA:?\s+(.+?)(?:\s+DEL\s+CANT[ÓO]N|,|$)", t, re.IGNORECASE) or re.search(
        r"CANT[ÓO]N:?\s+(.+?)(?:,|$)", t, re.IGNORECASE
    )
    if barrio:
        name = smart_title(barrio.group(1))
        where = f" ({smart_title(area.group(1))})" if area else ""
        return f"barrio {name}{where}" if lang == "es" else f"{name} neighborhood{where}"
    return smart_title(t)


def _notice_when(row: dict) -> tuple[date, datetime | None, str] | None:
    m = _FECHA.search(row.get("fecha_texto", ""))
    if not m:
        return None
    month = norm(m.group(2))
    names = [norm(x) for x in MONTHS["es"]]
    if month not in names:
        return None
    d = date(int(m.group(3)), names.index(month) + 1, int(m.group(1)))
    ranges = [h for h in row.get("horario") or [] if re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}", h)]
    if not ranges:
        return None
    end = datetime.strptime(ranges[-1].split("-")[1], "%H:%M").time()
    return d, datetime.combine(d, end, tzinfo=ECUADOR_TZ), ", ".join(ranges)


async def fetch_cortes(call: Caller, ctx: Ctx) -> dict:
    search = await call("search_cortes", distribuidora="eeasa")
    if not any(a.get("archivo") == "vigentes" for a in search.get("archivos") or []) and search.get("total"):
        raise RefreshError("search_cortes lists notices but no 'vigentes' file")
    if not search.get("total"):
        return {"count": 0, "examples": [], "url": search.get("url_fuente")}
    data = await call("get_cortes_horarios", distribuidora="eeasa", archivo="vigentes")
    rows = data.get("filas") or []
    count = int(data.get("total", len(rows)))
    if count != len(rows) and count:
        raise RefreshError(f"{count} notices announced, {len(rows)} rows parsed")
    upcoming = []
    for r in rows:
        w = _notice_when(r)
        if w is None:
            raise RefreshError(f"notice date/time not parsable: {r.get('fecha_texto')!r}")
        if w[1] > ctx.now:  # not finished yet
            upcoming.append((w[0], w[2], r.get("sectores", "")))
    upcoming.sort(key=lambda x: (x[0], x[1]))
    return {
        "count": count,
        "examples": [
            {"fecha": d.isoformat(), "horario": h, "sectores": s} for d, h, s in upcoming[:2]
        ],
        "url": data.get("url") or search.get("url_fuente"),
    }


def render_cortes(f: dict, lang: str) -> dict:
    url = f["url"]
    if f["count"] == 0:
        text = {
            "es": "No hay avisos de trabajos programados vigentes de la EEASA (Tungurahua, Pastaza, Napo y Morona Santiago) en este momento.",
            "en": "There are no active scheduled-work notices from EEASA (Tungurahua, Pastaza, Napo and Morona Santiago) at the moment.",
        }[lang]
        return {"answer": text, "url": url}
    n = f["count"]
    if not f["examples"]:
        text = {
            "es": f"La EEASA publica {n} {'aviso vigente' if n == 1 else 'avisos vigentes'}, pero todos corresponden a horarios que ya pasaron.",
            "en": f"EEASA lists {n} active {'notice' if n == 1 else 'notices'}, but all of them are for times that have already passed.",
        }[lang]
        return {"answer": text, "url": url}
    parts = []
    prev: date | None = None
    for ex in f["examples"]:
        d = date.fromisoformat(ex["fecha"])
        a, b = ex["horario"].split(", ")[0].split("-")
        extra = ex["horario"].count(",")
        wd = WEEKDAYS[lang][d.weekday()]
        where = sector_label(ex["sectores"], lang)
        if lang == "es":
            day = f"{wd} {d.day}" if prev and (prev.month, prev.year) == (d.month, d.year) else f"{wd} {fmt_day_month(d, lang)}"
            span = f"de {a} a {b}"
            more = " (más tramos ese día)" if extra else ""
            where_es = f"el {where}" if where.startswith("barrio") else where
            parts.append(f"{day}, {span}, en {where_es}{more}")
        else:
            span = f"from {a} to {b}"
            more = " (more slots that day)" if extra else ""
            where_en = f"the {where}" if "neighborhood" in where else where
            parts.append(f"{wd}, {fmt_day_month(d, lang)}, {span}, in {where_en}{more}")
        prev = d
    if lang == "es":
        head = f"Sí, {n} {'aviso vigente' if n == 1 else 'avisos vigentes'}."
        text = f"{head} Por ejemplo: {'; '.join(parts)}."
    else:
        head = f"Yes, {n} active {'notice' if n == 1 else 'notices'}."
        text = f"{head} For example: {'; '.join(parts)}."
    return {"answer": text, "url": url}


# --------------------------------------------------------------------------
# Census (static answers: verify they still resolve)
# --------------------------------------------------------------------------

CENSO_TIC_STEM = "03_2022_CPV_TIC"
ANDA_TITLE_EN = {
    "VIII Censo de Población y VII de Vivienda 2022": "VIII Population and VII Housing Census 2022",
}


def _tic_xlsx(archivos: list[dict]) -> str:
    names = [Path(urlparse(a.get("url", "")).path).name for a in archivos]
    if not any(n.startswith(CENSO_TIC_STEM) for n in names):
        raise RefreshError(f"{CENSO_TIC_STEM} not returned by search_archivos(censo, internet)")
    xlsx = next((n for n in names if n.startswith(CENSO_TIC_STEM) and n.endswith(".xlsx")), None)
    if xlsx is None:
        raise RefreshError(f"{CENSO_TIC_STEM}.xlsx not among the returned files")
    return xlsx


async def fetch_manta_internet(call: Caller, ctx: Ctx) -> dict:
    data = await call("search_archivos", fuente="censo", query="internet")
    return {"xlsx": _tic_xlsx(data.get("archivos") or [])}


def render_static(f: dict, lang: str) -> dict:
    """The census tabulado is static: verified, nothing rewritten."""
    return {}


async def fetch_censo(call: Caller, ctx: Ctx) -> dict:
    anda = await call("search_anda", query="censo poblacion vivienda 2022")
    hit = next((r for r in anda.get("results") or [] if r.get("idno")), None)
    if hit is None:
        raise RefreshError("search_anda found no census survey")
    dl = await call("download_anda_microdata", idno=hit["idno"])
    links = dl.get("enlaces_externos") or []
    if dl.get("tipo_acceso") != "enlace_externo" or not links:
        raise RefreshError(
            f"download_anda_microdata shape changed (tipo_acceso={dl.get('tipo_acceso')!r}); review the transcript by hand"
        )
    files = await call("search_archivos", fuente="censo", query="internet")
    link = urlparse(links[0]["url"])
    return {
        "idno": hit["idno"],
        "titulo": hit.get("titulo", ""),
        "tipo_acceso": hit.get("tipo_acceso") or dl["tipo_acceso"],
        "external": (link.netloc.removeprefix("www.") + link.path).rstrip("/"),
        "xlsx": _tic_xlsx(files.get("archivos") or []),
        "page": files.get("url_fuente"),
    }


def render_censo(f: dict, lang: str) -> dict:
    if lang == "es":
        text = (
            f"En el tabulado «Tecnologías de la información» del Censo 2022 ({f['xlsx']}), "
            "con hogares por disponibilidad de internet, computadora y celular por "
            "provincia, cantón y parroquia."
        )
    else:
        text = (
            f"In the «Information technologies» tabulation of the 2022 Census ({f['xlsx']}), "
            "with households by internet, computer and cell phone availability by "
            "province, canton and parish."
        )
    out = {"answer": text}
    if f["page"]:
        out["url"] = f["page"]
    return out


def transcript_censo(f: dict, lang: str, steps: list[dict]) -> None:
    title = f["titulo"]
    if lang == "en":
        if title not in ANDA_TITLE_EN:
            raise RefreshError(f"survey title changed, EN needs a translation: {title!r}")
        title = ANDA_TITLE_EN[title]
    micro = "microdatos" if lang == "es" else "microdata"
    s = find_step(steps, "call", "search_anda")
    s["result"] = f"{title} · {micro}: {f['tipo_acceso']}"
    find_step(steps, "call", "download_anda_microdata")["args"] = f'idno="{f["idno"]}"'
    find_step(steps, "call", "download_anda_microdata")["result"] = (
        f"tipo_acceso: {f['tipo_acceso']} → {f['external']}"
    )
    s3 = find_step(steps, "call", "search_archivos")
    # "8 tablas (...)" is not in the tool output: keep it, refresh the file name.
    s3["result"] = re.sub(r"^\S+", f["xlsx"], s3["result"], count=1)
    ans = find_step(steps, "answer")
    ans["text"] = (
        "El INEC publica el tabulado **Tecnologías de la información del Censo 2022**, con hogares por disponibilidad de internet, computadora y celular hasta nivel de parroquia."
        if lang == "es"
        else "INEC publishes the **Information technologies tabulation of the 2022 Census**, with households by internet, computer and cell phone availability down to parish level."
    )
    host = f["page"] and urlparse(f["page"]).netloc.removeprefix("www.")
    ans["cite"] = f"{host or 'censoecuador.gob.ec'} · {f['xlsx']}"


UNITS = [
    Unit("pasaporte", fetch_pasaporte, render_pasaporte, "pasaporte", transcript_pasaporte),
    Unit("sismos", fetch_sismos, render_sismos, "sismos", transcript_sismos),
    Unit("remesas", fetch_remesas, render_remesas),
    Unit("favorita", fetch_favorita, render_favorita),
    Unit("manta-compras", fetch_compras, render_compras),
    Unit("cortes-luz", fetch_cortes, render_cortes),
    Unit("manta-internet", fetch_manta_internet, render_static),
    Unit("censo-internet", fetch_censo, render_censo, "censo", transcript_censo),
]


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


@dataclass
class Result:
    unit: str
    status: str  # updated | unchanged | kept-previous
    detail: str = ""


@dataclass
class Refreshed:
    data: dict[str, Any]
    results: list[Result]

    @property
    def warnings(self) -> list[Result]:
        return [r for r in self.results if r.status == "kept-previous"]

    @property
    def succeeded(self) -> int:
        return sum(r.status != "kept-previous" for r in self.results)


def _by_id(items: list[dict], key: str = "id") -> dict[str, dict]:
    return {i[key]: i for i in items}


def check_parity(data: dict[str, Any]) -> None:
    """ES and EN must list the same ids, tools and URLs, in the same order."""
    es, en = data["es_answers"]["answers"], data["en_answers"]["answers"]
    if [a["id"] for a in es] != [a["id"] for a in en]:
        raise ValueError("ES/EN stored answers differ in ids or order")
    for a, b in zip(es, en, strict=True):
        for k in ("url", "tools"):
            if a.get(k) != b.get(k):
                raise ValueError(f"ES/EN mismatch in {a['id']}.{k}: {a.get(k)!r} != {b.get(k)!r}")
    es_t, en_t = data["es_transcripts"], data["en_transcripts"]
    if [t["id"] for t in es_t] != [t["id"] for t in en_t]:
        raise ValueError("ES/EN transcripts differ in ids or order")
    for a, b in zip(es_t, en_t, strict=True):
        if [(s["kind"], s.get("tool"), s.get("step")) for s in a["steps"]] != [
            (s["kind"], s.get("tool"), s.get("step")) for s in b["steps"]
        ]:
            raise ValueError(f"ES/EN transcript {a['id']} differ in step structure")


async def refresh(
    data: dict[str, Any],
    call: Caller,
    ctx: Ctx,
    version: str,
    units: list[Unit] | None = None,
) -> Refreshed:
    """Return a refreshed deep copy of ``data``; never mutates the input."""
    out = copy.deepcopy(data)
    prev_date = data["es_answers"]["extracted_at"]
    answers = {lang: _by_id(out[f"{lang}_answers"]["answers"]) for lang in ("es", "en")}
    transcripts = {lang: _by_id(out[f"{lang}_transcripts"]) for lang in ("es", "en")}
    results: list[Result] = []

    for unit in units or UNITS:
        try:
            facts = await asyncio.wait_for(unit.fetch(call, ctx), CALL_TIMEOUT * 4)
            new_answers: dict[str, dict] = {}
            new_steps: dict[str, list[dict]] = {}
            for lang in ("es", "en"):
                new_answers[lang] = unit.render(facts, lang)
                if unit.transcript and unit.transcript_id:
                    steps = copy.deepcopy(transcripts[lang][unit.transcript_id]["steps"])
                    unit.transcript(facts, lang, steps)
                    new_steps[lang] = steps
        except Exception as e:
            reason = f"{type(e).__name__}: {e}" if not isinstance(e, RefreshError) else str(e)
            for lang in ("es", "en"):  # stale marker: honest per-answer date
                ans = answers[lang].get(unit.id)
                if ans is not None and "extracted_at" not in ans:
                    ans["extracted_at"] = prev_date
            results.append(Result(unit.id, "kept-previous", reason))
            continue

        changed = False
        for lang in ("es", "en"):
            ans = answers[lang][unit.id]
            for k, v in new_answers[lang].items():
                if ans.get(k) != v:
                    ans[k] = v
                    changed = True
            ans.pop("extracted_at", None)
            if unit.transcript_id:
                tr = transcripts[lang][unit.transcript_id]
                if tr["steps"] != new_steps[lang]:
                    tr["steps"] = new_steps[lang]
                    changed = True
        results.append(Result(unit.id, "updated" if changed else "unchanged"))

    refreshed = Refreshed(out, results)
    if not refreshed.succeeded:  # nothing verified: leave every file as it was
        refreshed.data = copy.deepcopy(data)
    else:
        for lang in ("es", "en"):
            out[f"{lang}_answers"]["extracted_at"] = ctx.today.isoformat()
            out[f"{lang}_answers"]["server_version"] = version
    check_parity(refreshed.data)
    return refreshed


def load_all() -> dict[str, Any]:
    return {k: json.loads(p.read_text(encoding="utf-8")) for k, p in FILES.items()}


def render_files(data: dict[str, Any]) -> dict[str, str]:
    return {
        k: dump_answers(v) if k.endswith("answers") else dump_transcripts(v)
        for k, v in data.items()
    }


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def make_caller() -> Caller:
    """Call the real tool functions in-process (no server, no transport)."""
    sys.path.insert(0, str(ROOT))
    from mcp.server.mcpserver import MCPServer

    from tools import register_tools

    server = MCPServer("refresh-answers")
    register_tools(server)

    async def call(name: str, **args: Any) -> dict:
        result = await asyncio.wait_for(
            server.call_tool(name, {**args, "format": "json"}), CALL_TIMEOUT
        )
        if getattr(result, "isError", False):
            text = result.content[0].text if result.content else ""
            raise RefreshError(f"{name} returned an error: {text[:200]}")
        structured = getattr(result, "structured_content", None)
        if not isinstance(structured, dict):
            raise RefreshError(f"{name} returned no structured content")
        return structured

    return call


def format_report(res: Refreshed, dry_run: bool) -> str:
    lines = ["Stored answers refresh" + (" (dry run)" if dry_run else ""), ""]
    for r in res.results:
        tail = f": {r.detail}" if r.detail else ""
        lines.append(f"- [{r.status}] {r.unit}{tail}")
    if res.warnings:
        lines += ["", f"{len(res.warnings)} answer(s) kept at their previous version."]
    return "\n".join(lines)


def main(argv: list[str] | None = None, call: Caller | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="print a diff instead of writing")
    ap.add_argument("--report", type=Path, help="also write the summary to this file (PR body)")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD), for testing")
    args = ap.parse_args(argv)

    try:
        data = load_all()
        before = render_files(data)
        version = server_version()
        now = datetime.now(ECUADOR_TZ)
        if args.today:
            now = datetime.combine(date.fromisoformat(args.today), datetime.min.time(), ECUADOR_TZ)
        caller = call or make_caller()
        res = asyncio.run(refresh(data, caller, Ctx(now), version))
        after = render_files(res.data)
    except Exception as e:
        print(f"refresh_answers: unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    report = format_report(res, args.dry_run)
    if args.dry_run:
        for key, path in FILES.items():
            diff = difflib.unified_diff(
                before[key].splitlines(keepends=True),
                after[key].splitlines(keepends=True),
                fromfile=f"a/{_display(path)}",
                tofile=f"b/{_display(path)}",
            )
            sys.stdout.writelines(diff)
        print()
    else:
        for key, path in FILES.items():
            if after[key] != before[key]:
                path.write_text(after[key], encoding="utf-8")
    print(report)
    if args.report:
        note = (
            "\nAutomated refresh from live sources. Check each changed value against the "
            "official source before merging; this PR is never merged automatically.\n"
        )
        args.report.write_text(report + "\n" + note, encoding="utf-8")
    return 0 if res.succeeded else 3


if __name__ == "__main__":
    sys.exit(main())
