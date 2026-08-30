"""Client for Banco Central del Ecuador's BCEData statistical API.

BCEData (https://contenido.bce.fin.ec/bcedata/) is a JS grid app built on
top of a WordPress plugin (bcedata-grid). It isn't publicly documented as
an API, but inspecting its own network traffic shows it's backed by a
clean, versioned, public REST namespace under `/wp-json/bcedata/v1/` that
works with a plain unauthenticated GET (verified with curl, no cookies or
session needed) -- discovered by reading the app's own requests rather than
from any published reference.

Three endpoints, used together:

- `GET /tree` -- a flat list of ~98 catalog nodes (category headers with no
  `id_grupo`, and leaf groups that have one), covering four top-level
  sections: Estadisticas Monetarias y Financieras, Finanzas Publicas,
  Sector Externo (comercio exterior) and Sector Real (PIB, inflacion,
  desempleo, confianza del consumidor, etc). Small and effectively static,
  so the whole tree is cached in memory rather than re-fetched per search.
- `GET /bundle/{id_grupo}` -- metadata for one group: which frequencies
  and units it's available in, the date range it covers per frequency, and
  the list of individual series inside it (a group can hold a single
  series or dozens, broken out under section headers -- e.g. consumer
  confidence split by nacional/urbano/rural x situacion
  presente/futura/confianza del consumidor). Search needs this too, not
  just the tree: some topics only show up as a *series* inside a
  differently-named group -- "desempleo" isn't in any group title, it's a
  series inside group 68 ("Indicadores del mercado laboral nacional,
  urbano y rural"), alongside empleo/subempleo counterparts. So
  `search_indicadores` fetches every leaf group's bundle once (concurrently,
  cached alongside the tree) and matches against series labels too, not
  just group descriptions.
- `GET /grid?id_grupo=X&frecuencia=Y&unidad=Z&desde=YYYY-MM&hasta=YYYY-MM`
  -- the actual time series: one column per period, one row per series.
  Verified that desde/hasta outside the real data range are silently
  clamped to it rather than erroring, so `get_indicador` doesn't need to
  duplicate that clamping -- it only needs sensible defaults when the
  caller omits them, taken from the bundle's own reported range.

An invalid `id_grupo` or `unidad` gets a clean JSON error from the API
itself (`{"code": ..., "message": ..., "data": {"status": ...}}`), which
`_get_json` surfaces as the exception message instead of a generic HTTP
error, so callers get something actionable ("Unidad invalida para
frecuencia") without needing bespoke validation for every combination.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.text_utils import strip_accents as _strip
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE_URL = "https://contenido.bce.fin.ec/wp-json/bcedata/v1"
_TIMEOUT = 30.0

# The catalog tree is small (~98 nodes) and rarely changes; a day balances
# staleness against not re-fetching it on every search.
_tree_cache = TtlCache(ttl_seconds=86400.0, max_entries=1)
# Bundles (per-group metadata) change even less often than the tree itself.
_bundle_cache = TtlCache(ttl_seconds=86400.0, max_entries=256)
# The tree's leaf groups enriched with their series labels (see
# _fetch_catalog_with_series) -- same lifetime as the tree/bundles it's
# built from, cached separately since building it costs ~78 concurrent
# bundle fetches, not worth repeating per search.
_catalog_cache = TtlCache(ttl_seconds=86400.0, max_entries=1)

_SOURCE_NAME = "Banco Central del Ecuador — BCEData"
_TREE_URL = f"{_BASE_URL}/tree"


async def _get_json(
    path: str,
    params: dict[str, Any] | None = None,
    session: httpx.AsyncClient | None = None,
) -> Any:
    own = session is None
    if own:
        session = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=_TIMEOUT
        )
    assert session is not None
    try:
        resp = await session.get(f"{_BASE_URL}/{path.lstrip('/')}", params=params)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message")
            except Exception:
                detail = None
            logger.warning(
                "BCEData %s devolvió %d: %s", path, resp.status_code, detail
            )
            raise ValueError(detail or f"BCEData devolvió HTTP {resp.status_code}")
        return resp.json()
    finally:
        if own:
            await session.aclose()


async def _fetch_tree() -> list[dict[str, Any]]:
    cached = _tree_cache.get("tree")
    if cached is not None:
        return cached
    tree = await _get_json("tree")
    if not isinstance(tree, list):
        raise TypeError("BCEData /tree devolvió un formato inesperado")
    _tree_cache.set("tree", tree)
    return tree


def _index_tree(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten the tree to its leaf groups, each tagged with its section/subsection.

    The tree is a flat list ordered depth-first, with `num_nivel` the only
    signal of hierarchy -- there are no parent pointers. Most leaves sit at
    nivel 3, but a handful (verified live: 10 of the 78 groups) sit directly
    at nivel 2 with no nivel-3 sub-branch, and a couple sit one level deeper
    at nivel 4 (e.g. group 96/99 under "4.1.2 Exportaciones de petróleo
    crudo..."). `id_grupo` presence, not a fixed nivel, is what makes a node
    a leaf here -- walking in order and remembering the last-seen
    nivel-1/nivel-2 labels reconstructs the breadcrumb each leaf belongs to
    regardless of which nivel it's actually at.
    """
    section = ""
    subsection = ""
    indexed: list[dict[str, Any]] = []
    for node in tree:
        nivel = node.get("num_nivel")
        desc = node.get("desc_clasificador", "")
        if nivel == 1:
            section = desc
        elif nivel == 2:
            subsection = desc
        if node.get("id_grupo") is not None:
            indexed.append(
                {
                    "id_grupo": node["id_grupo"],
                    "descripcion": desc,
                    "seccion": section,
                    "subseccion": subsection if subsection != desc else "",
                }
            )
    return indexed


async def _fetch_bundle(
    id_grupo: int, session: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    cached = _bundle_cache.get(id_grupo)
    if cached is not None:
        return cached
    bundle = await _get_json(f"bundle/{id_grupo}", session=session)
    if not isinstance(bundle, dict):
        raise TypeError("BCEData /bundle devolvió un formato inesperado")
    _bundle_cache.set(id_grupo, bundle)
    return bundle


async def _fetch_catalog_snapshot() -> dict[str, Any]:
    """Leaf groups from the tree, each enriched with its series labels.

    One bundle fetch per leaf group (~78), done concurrently over a shared
    session -- a group whose bundle fails to load (network hiccup, or a
    genuinely empty group) is recorded in ``errores`` rather than failing the
    whole search. The complete snapshot is also used by the BCEData audit
    tool, so it retains metadata that normal search results omit.
    """
    cached = _catalog_cache.get("catalog")
    if cached is not None:
        return cached

    tree = await _fetch_tree()
    groups = _index_tree(tree)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=_TIMEOUT
    ) as session:
        bundles = await asyncio.gather(
            *(_fetch_bundle(g["id_grupo"], session=session) for g in groups),
            return_exceptions=True,
        )

    enriched: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for group, bundle in zip(groups, bundles, strict=True):
        if isinstance(bundle, dict):
            rows = bundle.get("rows")
            bundle_ok = isinstance(rows, list)
            if not isinstance(rows, list):
                errors.append(
                    {
                        "id_grupo": group["id_grupo"],
                        "tipo": "schema",
                        "detalle": "BCEData /bundle no devolvió una lista de filas",
                    }
                )
                rows = []
            series_labels = [
                row.get("label", "")
                for row in rows
                if isinstance(row, dict)
                and row.get("tipo") == "Series"
                and row.get("label")
            ]
            context = bundle.get("context") or {}
            frecuencias = bundle.get("frecuencias") or []
            unidades = bundle.get("unidades") or {}
            range_by_freq = bundle.get("range_by_freq") or {}
            enriched.append(
                {
                    **group,
                    "nombre": context.get("nom_grupo", ""),
                    "series": series_labels,
                    "total_series": len(series_labels),
                    "frecuencias": frecuencias,
                    "unidades": unidades,
                    "rango": bundle.get("range") or {},
                    "rango_por_frecuencia": range_by_freq,
                    "bundle_ok": bundle_ok,
                }
            )
        elif isinstance(bundle, BaseException):
            logger.warning(
                "No se pudo cargar el bundle del grupo %d para el índice de "
                "búsqueda: %s",
                group["id_grupo"],
                bundle,
            )
            errors.append(
                {
                    "id_grupo": group["id_grupo"],
                    "descripcion": group["descripcion"],
                    "tipo": "solicitud",
                    "detalle": str(bundle),
                }
            )
            enriched.append(
                {
                    **group,
                    "nombre": "",
                    "series": [],
                    "total_series": 0,
                    "frecuencias": [],
                    "unidades": {},
                    "rango": {},
                    "rango_por_frecuencia": {},
                    "bundle_ok": False,
                }
            )

    snapshot = {
        "source": _SOURCE_NAME,
        "url_fuente": _TREE_URL,
        "consultado_en": datetime.now(UTC).isoformat(),
        "total_nodos": len(tree),
        "total_grupos": len(groups),
        "grupos": enriched,
        "errores": errors,
    }
    _catalog_cache.set("catalog", snapshot)
    return snapshot


async def _fetch_catalog_with_series() -> list[dict[str, Any]]:
    snapshot = await _fetch_catalog_snapshot()
    return snapshot["grupos"]


async def audit_catalog(incluir_grupos: bool = False) -> dict[str, Any]:
    """Return a compact, reproducible coverage report for the BCEData API.

    The audit fetches the tree and every leaf group's bundle. It does not
    download every grid value, because grids can contain many years of data;
    ``get_indicador`` remains the complete value retrieval path for any group,
    frequency, unit and requested period.
    """
    snapshot = await _fetch_catalog_snapshot()
    groups = snapshot["grupos"]
    successful = [group for group in groups if group["bundle_ok"]]
    sections: dict[str, int] = {}
    for group in groups:
        sections[group["seccion"]] = sections.get(group["seccion"], 0) + 1

    result = {
        "source": snapshot["source"],
        "url_fuente": snapshot["url_fuente"],
        "consultado_en": snapshot["consultado_en"],
        "total_nodos": snapshot["total_nodos"],
        "total_grupos": snapshot["total_grupos"],
        "grupos_exitosos": len(successful),
        "grupos_con_error": len(snapshot["errores"]),
        "total_series": sum(group["total_series"] for group in successful),
        "secciones": sections,
        "errores": snapshot["errores"],
    }
    if incluir_grupos:
        result["grupos"] = groups
    return result


_SEARCH_RESULT_FIELDS = ("id_grupo", "descripcion", "seccion", "subseccion")


def _public_entry(item: dict[str, Any]) -> dict[str, Any]:
    """Strip the audit-only fields _fetch_catalog_snapshot adds for audit_catalog."""
    return {key: item[key] for key in _SEARCH_RESULT_FIELDS}


async def search_indicadores(
    query: str = "", limit: int = 20, offset: int = 0
) -> dict[str, Any]:
    """
    Search the BCEData catalog of statistical indicator groups.

    Matches against each group's own description/section/subsection *and*
    the labels of the individual series inside it -- some topics (e.g.
    "desempleo") only exist as one series among several inside a
    differently-named group ("Indicadores del mercado laboral..."), not as
    a group title of their own.

    Args:
        query: Free text matched (accent-insensitive) against the group's
            description, its section/subsection, and its series labels.
        limit: Max results returned.
        offset: Pagination offset over the matched set.
    """
    catalog = await _fetch_catalog_with_series()

    q = _strip(query)
    if not q:
        matched = [_public_entry(item) for item in catalog]
    else:
        matched = []
        for item in catalog:
            group_hit = (
                q in _strip(item["descripcion"])
                or q in _strip(item["seccion"])
                or q in _strip(item["subseccion"])
            )
            # A group broken out by nacional/urbano/rural (or by city) often
            # repeats the exact same series label under each breakdown --
            # e.g. "DESEMPLEO" appears once per region/city, all with
            # identical text. Dedup (order-preserving) so a result doesn't
            # list "DESEMPLEO" nine times for what's really one concept.
            series_hits = list(
                dict.fromkeys(s for s in item["series"] if q in _strip(s))
            )
            if not group_hit and not series_hits:
                continue
            entry = _public_entry(item)
            if series_hits and not group_hit:
                # Only attach when the group title itself didn't match, so
                # a plain group-title hit doesn't get cluttered with every
                # series in a group that can hold dozens of them.
                entry["series_coincidentes"] = series_hits
            matched.append(entry)

    page = matched[offset : offset + limit]
    snapshot = await _fetch_catalog_snapshot()
    return {
        "source": snapshot["source"],
        "url_fuente": snapshot["url_fuente"],
        "consultado_en": snapshot["consultado_en"],
        "total": len(matched),
        "offset": offset,
        "indicadores": page,
    }


async def get_indicador(
    id_grupo: int,
    desde: str = "",
    hasta: str = "",
    frecuencia: str = "",
    unidad: str = "",
) -> dict[str, Any]:
    """
    Time series data for one BCEData indicator group.

    Args:
        id_grupo: The group id from search_indicadores.
        desde: Start period as YYYY-MM. Defaults to the group's earliest
            available period for the chosen frequency.
        hasta: End period as YYYY-MM. Defaults to the group's latest
            available period for the chosen frequency.
        frecuencia: One of the group's available frequencies (Semanal,
            Mensual, Trimestral, Anual). Defaults to the first one the
            group offers.
        unidad: One of the group's available units for the chosen
            frequency (varies by group, e.g. "Millones de USD", "Indice",
            "Porcentaje"). Defaults to the first one available.
    """
    bundle = await _fetch_bundle(id_grupo)
    context = bundle.get("context") or {}
    frecuencias: list[str] = bundle.get("frecuencias") or []
    if not frecuencias:
        return {
            "error": "sin_datos",
            "id_grupo": id_grupo,
            "grupo": context.get("nom_grupo"),
        }

    if frecuencia:
        match = next(
            (f for f in frecuencias if f.casefold() == frecuencia.casefold()), None
        )
        if match is None:
            disponibles = ", ".join(frecuencias)
            raise ValueError(
                f"Frecuencia inválida '{frecuencia}' para el grupo {id_grupo}. "
                f"Disponibles: {disponibles}"
            )
        frecuencia = match
    freq = frecuencia or frecuencias[0]
    unidades_disponibles: list[str] = (bundle.get("unidades") or {}).get(freq, [])
    if not unidades_disponibles:
        return {
            "error": "sin_datos",
            "id_grupo": id_grupo,
            "grupo": context.get("nom_grupo"),
            "frecuencia": freq,
        }
    if unidad:
        match = next(
            (u for u in unidades_disponibles if u.casefold() == unidad.casefold()),
            None,
        )
        if match is None:
            disponibles = ", ".join(unidades_disponibles)
            raise ValueError(
                f"Unidad inválida '{unidad}' para el grupo {id_grupo} y frecuencia "
                f"{freq}. Disponibles: {disponibles}"
            )
        unidad = match
    unit = unidad or unidades_disponibles[0]

    range_for_freq = (bundle.get("range_by_freq") or {}).get(
        freq, bundle.get("range") or {}
    )
    d = desde.strip() or range_for_freq.get("minYm", "")
    h = hasta.strip() or range_for_freq.get("maxYm", "")

    grid = await _get_json(
        "grid",
        params={
            "id_grupo": id_grupo,
            "frecuencia": freq,
            "unidad": unit,
            "desde": d,
            "hasta": h,
        },
    )

    if not isinstance(grid, dict):
        raise TypeError("BCEData /grid devolvió un formato inesperado")

    rows = grid.get("rows") or []
    if not isinstance(rows, list):
        raise TypeError("BCEData /grid no devolvió una lista de filas")

    series = [
        {
            "label": row.get("label"),
            "ruta": row.get("ruta", ""),
            "valores": row.get("values", {}),
        }
        for row in rows
        if isinstance(row, dict)
        if row.get("tipo") == "Series"
    ]

    return {
        "source": _SOURCE_NAME,
        "url_fuente": f"{_BASE_URL}/grid",
        "consultado_en": datetime.now(UTC).isoformat(),
        "id_grupo": id_grupo,
        "grupo": context.get("nom_grupo"),
        "frecuencia": freq,
        "unidad": unit,
        "desde": d,
        "hasta": h,
        "periodos": grid.get("columns", []),
        "series": series,
    }
