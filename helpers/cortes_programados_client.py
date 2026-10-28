"""Client for the planned-maintenance outage notices of three distributors,
documented in docs/RESEARCH.md § Distribuidoras — cortes de mantenimiento
vigentes y archivo de crisis (Trigésimo quinta pasada, re-checked
2026-10-26).

Unlike the EEQ and Centrosur crisis archives (one PDF per schedule), these
are routine maintenance notices, one per job:

- Emelnorte (Imbabura, Carchi, north of Pichincha): WordPress category 7
  "Trabajos Programados", ~310 posts since April 2024. The body is plain
  text: a motive heading, then `FECHA(S):`, `HORA: DE 08:00 A 10:00` and
  `SECTORES AFECTADOS:`. Large jobs (substation maintenance) publish the
  schedule only as images; those notices come back with the image links
  and no rows.
- ElecGalápagos: WordPress categories 77/78/79 (San Cristóbal, Santa Cruz,
  Isabela), ~350 posts since December 2021, almost daily. One `Fecha:` and
  then one block per job: `De 09H00 a 12H00`, `Sector(es):`, `Instituciones
  afectadas:` and the motive.
- EEASA (Tungurahua, Pastaza, part of Napo and Morona Santiago): the page
  moved to `/trabajos-programados/` (the old `/suspensiones-programadas/`
  is a 404 served as 200). Server-rendered cards (`Fecha / Horario / Sector
  / Motivo`) for the coming days only; `wp-json` needs authorization, so
  there is no archive.

Each notice is one `archivo` for get_cortes_horarios: the WordPress post id
for Emelnorte and ElecGalápagos, `vigentes` for EEASA's single page.
"""

from __future__ import annotations

import asyncio
import json
import re
from html import unescape
from typing import Any

from helpers.cache import TtlCache
from helpers.csv_reader import download_bytes
from helpers.text_utils import strip_accents as _strip

_POSTS = 100

_FUENTES: dict[str, dict[str, Any]] = {
    "emelnorte": {
        "source": "Emelnorte — Trabajos Programados (Imbabura, Carchi, norte de Pichincha)",
        "url": (
            "https://www.emelnorte.com/wp-json/wp/v2/posts?categories=7"
            f"&per_page={_POSTS}&_fields=id,date,link,title,content,categories"
        ),
    },
    "elecgalapagos": {
        "source": "ElecGalápagos — Mantenimientos Programados (San Cristóbal, Santa Cruz, Isabela)",
        "url": (
            "https://www.elecgalapagos.com.ec/wp-json/wp/v2/posts?categories=77,78,79"
            f"&per_page={_POSTS}&_fields=id,date,link,title,content,categories"
        ),
    },
    "eeasa": {
        "source": "EEASA — Trabajos Programados (Tungurahua, Pastaza, Napo, Morona Santiago)",
        "url": "https://www.eeasa.com.ec/trabajos-programados/",
    },
}
_ISLAS = {77: "San Cristóbal", 78: "Santa Cruz", 79: "Isabela"}

# New notices land several times a week; half an hour keeps a day's
# questions on one fetch without missing a same-day notice for long.
_cache = TtlCache(ttl_seconds=1800.0, max_entries=8)
_locks: dict[str, asyncio.Lock] = {}

_TAG_RE = re.compile(r"<[^>]+>")
_SHORTCODE_RE = re.compile(r"\[/?vc_[^\]]*\]")
_HORA_RE = re.compile(
    r"(?:de\s+)?(\d{1,2})\s*[:hH]\s*(\d{2})\s*(?:a|hasta|[-–—])\s*(\d{1,2})\s*[:hH]\s*(\d{2})",
    re.IGNORECASE,
)
_HORA_SOLA_RE = re.compile(
    r"^\s*\d{1,2}\s*[:hH]\s*\d{2}\s*(?:a|hasta|[-–—])\s*\d{1,2}\s*[:hH]\s*\d{2}\s*$", re.IGNORECASE
)
_HORA_PUNTO_RE = re.compile(r"(\d{1,2})\s*[:hH]\s*(\d{2})")
_DIA_RE = re.compile(r"^(lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b")
_IMG_RE = re.compile(r'<a href="(https?://[^"]+\.(?:png|jpe?g|webp))"', re.IGNORECASE)
_EEASA_CARD_RE = re.compile(r'<div class="card-body">(.*?)</div>', re.DOTALL)
_EEASA_FIELD_RE = re.compile(r"<strong>\s*([^<:]+):\s*</strong>(.*?)</(?:h5|p)>", re.DOTALL)


def _lines(html: str) -> list[str]:
    text = unescape(_TAG_RE.sub("\n", _SHORTCODE_RE.sub("", html)))
    lines: list[str] = []
    for line in text.split("\n"):
        line = " ".join(line.split())
        if not line:
            continue

        # "FECHAS" and ": lunes 15 de junio" can land on separate lines.
        if line.startswith(":") and lines:
            lines[-1] += line
        else:
            lines.append(line)
    return lines


def _horarios(text: str) -> list[str]:
    return [f"{int(a):02d}:{b}-{int(c):02d}:{d}" for a, b, c, d in _HORA_RE.findall(text)]


def _label(line: str, *labels: str) -> str | None:
    """The value after `LABEL:` when the line starts with one of the labels
    and a colon (accent/case-insensitive), "" when the value is on the next
    line. "Sector Gruta del Socavón" has no colon, so it is a value."""
    head, colon, value = line.partition(":")
    if not colon:
        return None
    key = _strip(head)
    # Optional plural "s" ("FECHAS", "Sectores") and stray spaces before ":".
    if any(key.rstrip("s ") == label or key.startswith(label) for label in labels):
        return value.strip()
    return None


def _parse_emelnorte(post: dict[str, Any]) -> dict[str, Any]:
    html = post["content"]["rendered"]
    lines = _lines(html)
    motivo: list[str] = []
    campos: dict[str, list[str]] = {}
    actual: str | None = None
    for line in lines:
        for clave, etiquetas in (
            ("fecha", ("fecha",)),
            ("hora", ("hora",)),
            ("sectores", ("sectores afectados", "sector")),
        ):
            value = _label(line, *etiquetas)
            if value is not None:
                actual = clave
                campos[actual] = [value] if value else []
                break
        else:
            if actual is None:
                motivo.append(line)
            elif not line.startswith("Pedimos disculpas") and line != "DIRECCIÓN DE DISTRIBUCIÓN":
                campos.setdefault(actual, []).append(line)

    if "hora" not in campos:
        imagenes = sorted(set(_IMG_RE.findall(html)))
        return {"filas": [], "imagenes": imagenes, "motivo": " ".join(motivo) or None}

    sectores = [s for s in campos.get("sectores", []) if not s.startswith("Pedimos disculpas")]
    return {
        "filas": [
            {
                "pagina": 1,
                "fecha_texto": " ".join(campos.get("fecha", [])),
                "horario": _horarios(" ".join(campos["hora"])),
                "sectores": " ".join(sectores),
                "motivo": " ".join(motivo).strip('“”" ') or None,
            }
        ],
        "imagenes": [],
    }


def _parse_elecgalapagos(post: dict[str, Any]) -> dict[str, Any]:
    lines = _lines(post["content"]["rendered"])
    isla = next((_ISLAS[c] for c in post.get("categories") or [] if c in _ISLAS), None)
    fecha = ""
    filas: list[dict[str, Any]] = []

    def nueva_fila(horario: list[str]) -> None:
        filas.append(
            {
                "pagina": 1,
                "fecha_texto": fecha,
                "horario": horario,
                "zona": isla,
                "sectores": "",
                "instituciones": None,
                "motivo": None,
            }
        )

    def asignar(clave: str, value: str) -> None:
        nonlocal fecha
        if clave in ("fecha", "fecha_inicio"):
            fecha = value
        elif clave == "hora":
            nueva_fila(_horarios(value))
        elif clave == "hora_inicio":
            nueva_fila([])
            filas[-1]["_inicio"] = value
        elif clave == "hora_fin" and filas:
            inicio = _HORA_PUNTO_RE.search(filas[-1].pop("_inicio", "") or "")
            fin = _HORA_PUNTO_RE.search(value)
            if inicio and fin:
                filas[-1]["horario"] = [
                    f"{int(inicio[1]):02d}:{inicio[2]}-{int(fin[1]):02d}:{fin[2]}"
                ]
        elif clave == "fecha_fin" and filas:
            filas[-1]["fecha_fin"] = value
        elif clave == "fecha_fin":
            fecha = f"{fecha} al {value}"
        elif filas:
            filas[-1][clave] = value

    # Three layouts: "De 09H00 a 12H00" opening each job (2025 on),
    # "Hora:" / "Sector:" / "Actividades:" labels, or "Hora de inicio/fin"
    # for jobs that run overnight. A label with nothing after the colon, or
    # a date cut after the weekday ("Viernes,"), continues on the next line.
    etiquetas = (
        ("fecha_inicio", "fecha de inicio"),
        ("fecha_fin", "fecha de fin"),
        ("hora_inicio", "hora de inicio"),
        ("hora_fin", "hora de fin"),
        ("fecha", "fecha"),
        ("hora", "hora"),
        ("sectores", "sector"),
        ("instituciones", "instituciones"),
        ("motivo", "actividades"),
    )
    pendiente: str | None = None
    previo = ""
    for line in lines:
        if pendiente:
            asignar(pendiente, f"{previo} {line}".strip())
            pendiente, previo = None, ""
            continue

        clave, value = next(
            ((k, v) for k, label in etiquetas if (v := _label(line, label)) is not None),
            (None, None),
        )
        if clave is not None:
            if not value or (clave.startswith("fecha") and value.endswith(",")):
                pendiente, previo = clave, value or ""
            else:
                asignar(clave, value)
            continue

        # The oldest layout drops the labels: "Viernes 14/08/2026", then
        # "08H00 a 12H00" on its own line.
        horario = _horarios(line)
        if horario and (_strip(line).startswith("de ") or _HORA_SOLA_RE.match(line)):
            nueva_fila(horario)
        elif _DIA_RE.match(_strip(line)) and len(line) < 60:
            fecha = line
        elif filas:
            filas[-1]["motivo"] = " ".join(filter(None, (filas[-1]["motivo"], line)))
    for fila in filas:
        fila.pop("_inicio", None)
    return {"filas": filas, "imagenes": []}


def _parse_eeasa(html: str) -> list[dict[str, Any]]:
    filas = []
    for card in _EEASA_CARD_RE.findall(html):
        campos = {
            _strip(k): " ".join(unescape(_TAG_RE.sub(" ", v)).replace("ü", " ").split())
            for k, v in _EEASA_FIELD_RE.findall(card)
        }
        if "fecha" not in campos:
            continue
        filas.append(
            {
                "pagina": 1,
                "fecha_texto": campos["fecha"],
                "horario": _horarios(campos.get("horario", "")),
                "sectores": campos.get("sector", ""),
                "motivo": campos.get("motivo"),
            }
        )
    return filas


async def _fetch(distribuidora: str) -> Any:
    cached = _cache.get(distribuidora)
    if cached is not None:
        return cached
    lock = _locks.setdefault(distribuidora, asyncio.Lock())
    async with lock:
        cached = _cache.get(distribuidora)
        if cached is not None:
            return cached
        content, truncated = await download_bytes(_FUENTES[distribuidora]["url"])
        if truncated:
            raise ValueError(f"La respuesta de {distribuidora} superó el límite de descarga.")
        text = content.decode("utf-8", errors="replace")
        data = _parse_eeasa(text) if distribuidora == "eeasa" else json.loads(text)
        _cache.set(distribuidora, data)
        return data


async def search(distribuidora: str, query: str = "") -> dict[str, Any]:
    """List the utility's latest notices (EEASA: its one page of current
    notices), filtered by free text against the title and body."""
    fuente = _FUENTES[distribuidora]
    data = await _fetch(distribuidora)
    q = _strip(query)
    if distribuidora == "eeasa":
        archivos = [
            {
                "archivo": "vigentes",
                "titulo": f"Trabajos programados vigentes ({len(data)} aviso(s))",
                "fecha": None,
                "url": fuente["url"],
            }
        ]
        if q and not any(q in _strip(f"{f['fecha_texto']} {f['sectores']}") for f in data):
            archivos = []
        total = 1
    else:
        archivos = [
            {
                "archivo": str(p["id"]),
                "titulo": unescape(p["title"]["rendered"]),
                "fecha": p["date"][:10],
                "url": p["link"],
            }
            for p in data
            if not q or q in _strip(f"{p['title']['rendered']} {p['content']['rendered']}")
        ]
        total = len(data)
    return {
        "total": len(archivos),
        "total_en_archivo": total,
        "source": fuente["source"],
        "url_fuente": fuente["url"],
        "archivos": archivos,
    }


async def get_horarios(distribuidora: str, archivo: str, query: str = "") -> dict[str, Any]:
    """Rows of one notice: date, time blocks, sectors and motive."""
    fuente = _FUENTES[distribuidora]
    data = await _fetch(distribuidora)
    nota = None
    if distribuidora == "eeasa":
        filas, url, imagenes = data, fuente["url"], []
    else:
        post = next((p for p in data if str(p["id"]) == archivo.strip()), None)
        if post is None:
            raise ValueError(
                f"Aviso '{archivo}' no está entre los {len(data)} más recientes de "
                f"{distribuidora}; usa un archivo de search_cortes."
            )
        parser = _parse_emelnorte if distribuidora == "emelnorte" else _parse_elecgalapagos
        parsed = parser(post)
        filas, url, imagenes = parsed["filas"], post["link"], parsed["imagenes"]
        if not filas and imagenes:
            nota = (
                f"El aviso publica el horario solo como imagen ({parsed.get('motivo') or 'sin motivo'}); "
                "revisa los enlaces de `imagenes`."
            )

    q = _strip(query)
    matched = [
        f
        for f in filas
        if not q or q in _strip(f"{f['sectores']} {f.get('zona') or ''} {f.get('motivo') or ''}")
    ]
    return {
        "total": len(matched),
        "total_en_archivo": len(filas),
        "paginas": 1,
        "url": url,
        "nota": nota,
        "imagenes": imagenes,
        "filas": matched,
    }
