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
from typing import Any
from unicodedata import category, normalize

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
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


def _strip(text: str) -> str:
    nfkd = normalize("NFKD", text or "")
    return "".join(c for c in nfkd if category(c) != "Mn").lower()


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

    The tree is a flat list ordered depth-first, with `num_nivel` (1/2/3)
    the only signal of hierarchy -- there are no parent pointers. Walking
    it in order and remembering the last-seen nivel-1/nivel-2 labels
    reconstructs the breadcrumb each leaf belongs to.
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


async def _fetch_catalog_with_series() -> list[dict[str, Any]]:
    """Leaf groups from the tree, each enriched with its series labels.

    One bundle fetch per leaf group (~78), done concurrently over a shared
    session -- a group whose bundle fails to load (network hiccup, or a
    genuinely empty group) just gets an empty series list rather than
    failing the whole search.
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
    for group, bundle in zip(groups, bundles, strict=True):
        series_labels: list[str] = []
        if isinstance(bundle, dict):
            series_labels = [
                row.get("label", "")
                for row in bundle.get("rows", [])
                if row.get("tipo") == "Series"
            ]
        elif isinstance(bundle, BaseException):
            logger.warning(
                "No se pudo cargar el bundle del grupo %d para el índice de "
                "búsqueda: %s",
                group["id_grupo"],
                bundle,
            )
        enriched.append({**group, "series": series_labels})

    _catalog_cache.set("catalog", enriched)
    return enriched


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
        matched = [
            {k: v for k, v in item.items() if k != "series"} for item in catalog
        ]
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
            entry = {k: v for k, v in item.items() if k != "series"}
            if series_hits and not group_hit:
                # Only attach when the group title itself didn't match, so
                # a plain group-title hit doesn't get cluttered with every
                # series in a group that can hold dozens of them.
                entry["series_coincidentes"] = series_hits
            matched.append(entry)

    page = matched[offset : offset + limit]
    return {"total": len(matched), "offset": offset, "indicadores": page}


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

    freq = frecuencia if frecuencia in frecuencias else frecuencias[0]
    unidades_disponibles: list[str] = (bundle.get("unidades") or {}).get(freq, [])
    if not unidades_disponibles:
        return {
            "error": "sin_datos",
            "id_grupo": id_grupo,
            "grupo": context.get("nom_grupo"),
            "frecuencia": freq,
        }
    unit = unidad if unidad in unidades_disponibles else unidades_disponibles[0]

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

    series = [
        {
            "label": row.get("label"),
            "ruta": row.get("ruta", ""),
            "valores": row.get("values", {}),
        }
        for row in grid.get("rows", [])
        if row.get("tipo") == "Series"
    ]

    return {
        "id_grupo": id_grupo,
        "grupo": context.get("nom_grupo"),
        "frecuencia": freq,
        "unidad": unit,
        "desde": d,
        "hasta": h,
        "periodos": grid.get("columns", []),
        "series": series,
    }
