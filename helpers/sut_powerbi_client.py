"""Client for the Ministerio del Trabajo/SUT's public Power BI "Indicadores"
dashboards (linked from sut.trabajo.gob.ec/mrl/contenido/indicadores/*.xhtml).

These are NOT static files -- each dashboard is a live semantic model
(Power BI's "Analysis Services" query engine) queried through a public,
unauthenticated JSON API. Reverse-engineered 2026-08-30/31 after an earlier
pass wrongly concluded these dashboards "just visualize the same data
already exported to CKAN" (refuted live: the "Contratos MDT v1" dashboard
has a monthly 2015-present series by industry/province/gender/contract
status that has no CKAN equivalent -- the only CKAN resource for contratos
is a single current-month stock snapshot with no time dimension at all).

## How this works

Each dashboard's `app.powerbi.com/view?r=<token>` embed URL is public; the
token base64-decodes to `{"k": resource_key, "t": tenant_id, "c": 4}`. The
resource_key alone is sufficient -- no login, no cookies, no session:

1. `GET  {_BASE}/public/reports/{resource_key}/modelsAndExploration`
   (header `X-PowerBI-ResourceKey: {resource_key}`) returns the report's
   `reportId`/`modelId`/`dataset id (models[0].dbName)` plus a full
   `exploration.sections[].visualContainers[]` layout -- each visual's
   `config` JSON embeds its own `prototypeQuery` (exact Select/From it
   runs), which is how every field in every dashboard was catalogued
   here (_collect_fields) without ever clicking through the UI.
2. `POST {_BASE}/public/reports/querydata?synchronous=true` (same header)
   with a `SemanticQueryDataShapeCommand` body runs an arbitrary query
   against the model -- any combination of the columns/measures found in
   step 1, not just what a specific visual already shows. This is what
   makes month x industry (or any other combination) possible even though
   no single visual in the dashboard displays it that way.

A request to querydata WITHOUT the `X-PowerBI-ResourceKey` header can
still return 200 for a query some real session already ran (served from
an edge/CDN cache keyed by request body) -- this is a trap: it looks like
open access but a genuinely new query 401s without the header. Always
send it.

## Decoding the response (DSR format)

The response's `dsr` field is Power BI's compact "Data Shape Result"
encoding, not a plain row array: the first entry in a `DM0` list carries
`"S"` (the column schema, with a `"DN"` pointing into `ValueDicts` for
any dictionary-encoded/categorical column); every entry after that is one
row, giving only the values that changed since the previous row -- `"C"`
holds those changed values in schema-column order, `"R"` is a bitmask
(bit i set => column i repeats the previous row's value, contributes
nothing to "C"), and `"Ø"` is the equivalent bitmask for a null value.
`_decode_dsr` implements this and was validated against ground truth read
directly off the live "Contratos MDT v1" dashboard's own "Show as a
table" export (enero 2015 = 92,306 contratos) before being trusted here.

## Scope

Read-only, metadata/data only -- no visual rendering, no write access
(there isn't any). Query field/row caps exist to keep responses agent-
sized; this is not a general Power BI client.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from helpers.cache import TtlCache
from helpers.logging import MAIN_LOGGER_NAME
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_BASE = "https://wabi-south-central-us-c-primary-api.analysis.windows.net"
_TIMEOUT = 30.0
_DEFAULT_ROW_LIMIT = 20000
# Hard cap on the DataReduction window: a wider request would never fit the
# client's context anyway and gives Power BI a reason to answer with an
# error body rather than rows.
_MAX_ROW_LIMIT = 20000

# Consejo de la Judicatura's Portal de Estadística Judicial
# (fsweb.funcionjudicial.gob.ec/estadisticas/*.html) embeds Power BI
# "publish to web" reports that live on a different cluster than the SUT
# ones. The resource key only resolves on its own cluster (wrong cluster =>
# 401 UnableToFindKeyInDBorCacheException), so each registry entry may carry
# its own `base`; entries without one use _BASE.
_JUDICATURA_BASE = "https://wabi-paas-1-scus-api.analysis.windows.net"
_FUENTES = ("sut", "judicatura")

# Power BI AggregateFunction codes seen live on the Judicatura dashboards and
# worth exposing as fields; other codes (min/max/count) are skipped.
_AGG_LABELS = {0: "suma", 1: "promedio"}

_INDICADORES: list[dict[str, str]] = [
    {
        "indicador": "contratos",
        "nombre": "Contratos MDT v1 — contratos registrados en el SUT",
        "resource_key": "19718e1d-8f2d-4aa5-9528-80af28eaacfa",
    },
    {
        "indicador": "denuncias_publico",
        "nombre": "Denuncias del Servicio Público",
        "resource_key": "7e03a6bc-ba85-46e4-845d-cc3db796866c",
    },
    {
        "indicador": "estrategias_empleabilidad",
        "nombre": "Estrategias EMPRENDE EC y FORTALECE EMPLEO",
        "resource_key": "f379e098-fd5e-4cd3-b3dc-d9aa697e9ca7",
    },
    {
        "indicador": "capacitacion_certificacion",
        "nombre": "Capacitaciones y Certificaciones del MDT (SETEC)",
        "resource_key": "14f8a945-dc82-4f7c-8abc-4793b3032093",
    },
    {
        "indicador": "encuentra_empleo",
        "nombre": "Encuentra Empleo",
        "resource_key": "b8e5e644-7c64-49d6-9c78-9a011c495d98",
    },
    {
        "indicador": "encuesta_demanda_laboral",
        "nombre": "Encuesta de Demanda Laboral y Habilidades (empleadores)",
        "resource_key": "37e00bcb-7bf1-41e3-8b1a-5a925038b638",
    },
    {
        "indicador": "plan_nacional_desarrollo",
        "nombre": "Plan Nacional de Desarrollo — metas laborales",
        "resource_key": "9abd3389-634b-4122-b781-c19f5cff32d6",
    },
    {
        "indicador": "sentencia_genero",
        "nombre": (
            "Sentencia — género, ambientes laborales y política pública "
            "(PEA, brechas salariales, lactarios, cuidado infantil, teletrabajo)"
        ),
        "resource_key": "5b212c21-2363-4f5b-84c6-bb4f5a439c77",
    },
]
_JUDICATURA_INDICADORES: list[dict[str, str]] = [
    {
        "indicador": "audiencias",
        "nombre": "Audiencias judiciales (programadas, realizadas, fallidas)",
        "resource_key": "fe27a4d9-983c-45b1-8e89-2d212b47b0ce",
    },
    {
        "indicador": "boletas",
        "nombre": "Boletas de apremio y de encarcelamiento",
        "resource_key": "e2884a27-b6d0-42eb-ab3f-7ffc2a0a230f",
    },
    {
        "indicador": "capacitaciones",
        "nombre": "Capacitaciones de la Escuela de la Función Judicial",
        "resource_key": "bfa7ccf9-5dfe-4deb-9d54-89a359a47367",
    },
    {
        "indicador": "destituciones",
        "nombre": "Destituciones de servidores judiciales",
        "resource_key": "09d997b3-c75b-40fb-b818-039cc624750b",
    },
    {
        "indicador": "escritos",
        "nombre": "Escritos y trámites ingresados",
        "resource_key": "753fcfb9-057d-4707-b52d-5ceeb9784c07",
    },
    {
        "indicador": "mediacion",
        "nombre": "Mediación (actas, mediadores, tiempos)",
        "resource_key": "9d6e0ecf-6776-471c-9d97-9cb56e749927",
    },
    {
        "indicador": "notarial",
        "nombre": "Servicio notarial (actos, notarías, recaudación, sorteos)",
        "resource_key": "23dd94b9-e402-4a8a-8c8a-72cf6b1088ae",
    },
    {
        "indicador": "productividad_jueces",
        "nombre": "Productividad de jueces (trámites, tasa de resolución)",
        "resource_key": "789ae560-e736-437e-9aef-85564a353257",
    },
    {
        "indicador": "remates_judiciales",
        "nombre": "Remates judiciales",
        "resource_key": "979b6b41-4fa3-492a-a463-03d2d307e377",
    },
    {
        "indicador": "supa",
        "nombre": "SUPA — pensiones alimenticias (recaudación, incidentes, boletas de apremio)",
        "resource_key": "6a820389-fb8b-44c1-b93d-d1d29bbe58af",
    },
]
for _entry in _INDICADORES:
    _entry["fuente"] = "sut"
for _entry in _JUDICATURA_INDICADORES:
    _entry["fuente"] = "judicatura"
    _entry["base"] = _JUDICATURA_BASE
_INDICADORES.extend(_JUDICATURA_INDICADORES)
_INDICADORES_BY_KEY = {i["indicador"]: i for i in _INDICADORES if i["fuente"] == "sut"}
_INDICADORES_BY_FUENTE_KEY = {(i["fuente"], i["indicador"]): i for i in _INDICADORES}

# denuncias_publico and encuentra_empleo ship an older/compressed report
# layout: modelsAndExploration still returns reportId/modelId/dataset id
# fine, but each visualContainer is just {id,x,y,z,width,height,objectName}
# -- no "config" JSON, so _collect_fields legitimately finds nothing (not
# a bug in the parser). Their real fields were recovered 2026-08-31 the
# same way indiContratos' month x industry combination was found in the
# first place: driving the live dashboard in a browser with window.fetch/
# XMLHttpRequest hooked, changing a filter to force a fresh query, and
# reading the exact Select/Where shape Power BI's own frontend sent.
# Kept as a manual override merged on top of whatever _collect_fields
# finds (currently nothing for these two) rather than a special case in
# the query path, so query_indicador/get_indicador_schema don't need to
# know these are "different" -- they just see a fuller campos dict.
_MANUAL_CAMPOS: dict[str, dict[str, dict[str, Any]]] = {
    "denuncias_publico": {
        spec["label"]: spec
        for spec in [
            {
                "label": "REGISTROS.1.-Fecha de Ingreso al MDT [Año]",
                "entity": "REGISTROS",
                "property": "1.-Fecha de Ingreso al MDT",
                "kind": "hierarchy",
                "level": "Año",
                "hierarchy_name": "Jerarquía de fechas",
                "variation_name": "Variación",
                "query_name": "REGISTROS.1.-Fecha de Ingreso al MDT.Variación.Jerarquía de fechas.Año",
            },
            {
                "label": "REGISTROS.1.-Fecha de Ingreso al MDT [Mes]",
                "entity": "REGISTROS",
                "property": "1.-Fecha de Ingreso al MDT",
                "kind": "hierarchy",
                "level": "Mes",
                "hierarchy_name": "Jerarquía de fechas",
                "variation_name": "Variación",
                "query_name": "REGISTROS.1.-Fecha de Ingreso al MDT.Variación.Jerarquía de fechas.Mes",
            },
            {
                "label": "REGISTROS.5.-Motivo de la Denuncia",
                "entity": "REGISTROS",
                "property": "5.-Motivo de la Denuncia",
                "kind": "column",
                "query_name": "REGISTROS.5.-Motivo de la Denuncia",
            },
            {
                "label": "REGISTROS.0.-Regional Asignada",
                "entity": "REGISTROS",
                "property": "0.-Regional Asignada",
                "kind": "column",
                "query_name": "REGISTROS.0.-Regional Asignada",
            },
            {
                "label": "REGISTROS.Estado",
                "entity": "REGISTROS",
                "property": "Estado",
                "kind": "column",
                "query_name": "REGISTROS.Estado",
            },
            {
                "label": "REGISTROS.Año ingreso al MDT",
                "entity": "REGISTROS",
                "property": "Año ingreso al MDT",
                "kind": "column",
                "query_name": "REGISTROS.Año ingreso al MDT",
            },
            {
                "label": "REGISTROS.Fecha de Carga",
                "entity": "REGISTROS",
                "property": "Fecha de Carga",
                "kind": "column",
                "query_name": "REGISTROS.Fecha de Carga",
            },
            {
                "label": "REGISTROS.Cantidad denuncias [medida]",
                "entity": "REGISTROS",
                "property": "Cantidad denuncias",
                "kind": "measure",
                "query_name": "REGISTROS.Cantidad denuncias",
            },
        ]
    },
    "encuentra_empleo": {
        spec["label"]: spec
        for spec in [
            {
                "label": "CONSOLIDADO.Fecha de Corte [Año]",
                "entity": "CONSOLIDADO",
                "property": "Fecha de Corte",
                "kind": "hierarchy",
                "level": "Año",
                "hierarchy_name": "Jerarquía de fechas",
                "variation_name": "Variación",
                "query_name": "CONSOLIDADO.Fecha de Corte.Variación.Jerarquía de fechas.Año",
            },
            {
                "label": "CONSOLIDADO.Fecha de Corte [Mes]",
                "entity": "CONSOLIDADO",
                "property": "Fecha de Corte",
                "kind": "hierarchy",
                "level": "Mes",
                "hierarchy_name": "Jerarquía de fechas",
                "variation_name": "Variación",
                "query_name": "CONSOLIDADO.Fecha de Corte.Variación.Jerarquía de fechas.Mes",
            },
            {
                "label": "CONSOLIDADO.Fecha de Corte [Día]",
                "entity": "CONSOLIDADO",
                "property": "Fecha de Corte",
                "kind": "hierarchy",
                "level": "Día",
                "hierarchy_name": "Jerarquía de fechas",
                "variation_name": "Variación",
                "query_name": "CONSOLIDADO.Fecha de Corte.Variación.Jerarquía de fechas.Día",
            },
            {
                "label": "CONSOLIDADO.Encuentra Empleo",
                "entity": "CONSOLIDADO",
                "property": "Encuentra Empleo",
                "kind": "column",
                "query_name": "CONSOLIDADO.Encuentra Empleo",
            },
            {
                "label": "CONSOLIDADO.Provincia",
                "entity": "CONSOLIDADO",
                "property": "Provincia",
                "kind": "column",
                "query_name": "CONSOLIDADO.Provincia",
            },
            {
                "label": "CONSOLIDADO.Año",
                "entity": "CONSOLIDADO",
                "property": "Año",
                "kind": "column",
                "query_name": "CONSOLIDADO.Año",
            },
            {
                "label": "CONSOLIDADO.Fecha de Carga",
                "entity": "CONSOLIDADO",
                "property": "Fecha de Carga",
                "kind": "column",
                "query_name": "CONSOLIDADO.Fecha de Carga",
            },
            {
                "label": "CONSOLIDADO.Número de Personas [medida]",
                "entity": "CONSOLIDADO",
                "property": "Número de Personas",
                "kind": "aggregated_sum",
                "query_name": "Sum(CONSOLIDADO.Número de Personas)",
            },
        ]
    },
}

# Exploration schemas change rarely (a report redesign); query results are
# NOT cached here -- always live, since the whole point is fresh data.
_schema_cache = TtlCache(ttl_seconds=21600.0, max_entries=len(_INDICADORES))
_fetch_lock = asyncio.Lock()


def list_indicadores(fuente: str = "sut") -> list[dict[str, str]]:
    """The fixed Power BI dashboards of one fuente (default: the eight SUT ones)."""
    _check_fuente(fuente)
    return [dict(i) for i in _INDICADORES if i["fuente"] == fuente]


def _check_fuente(fuente: str) -> None:
    if fuente not in _FUENTES:
        raise ValueError(f"Fuente '{fuente}' no reconocida. Válidas: {', '.join(_FUENTES)}")


def _lookup(indicador: str, fuente: str) -> dict[str, str]:
    _check_fuente(fuente)
    info = _INDICADORES_BY_FUENTE_KEY.get((fuente, indicador))
    if info is None:
        valid = ", ".join(sorted(k for f, k in _INDICADORES_BY_FUENTE_KEY if f == fuente))
        raise ValueError(f"Indicador '{indicador}' no reconocido en la fuente '{fuente}'. Válidos: {valid}")
    return info


_TYPE_NAMES = {
    "int": "int", "int32": "int", "int64": "int", "integer": "int", "whole": "int", "long": "int",
    "double": "decimal", "decimal": "decimal", "float": "decimal", "number": "decimal", "currency": "decimal",
    "boolean": "bool", "bool": "bool", "logical": "bool",
    "datetime": "datetime", "date": "datetime", "time": "datetime",
    "text": "string", "string": "string",
}


def _normalize_data_type(raw: Any) -> str | None:
    """Map a Power BI type name (DataType / ConceptualDataType, when the
    response spells it out) to int|decimal|bool|datetime|string, else None.
    Bare numeric codes are deliberately ignored: their meaning differs
    between the conceptual schema and the DSR and was never verified."""
    if isinstance(raw, str):
        return _TYPE_NAMES.get(raw.strip().lower())
    return None


def _type_from_node(body: dict[str, Any]) -> str | None:
    for key in ("DataType", "ConceptualDataType", "dataType"):
        found = _normalize_data_type(body.get(key))
        if found:
            return found
    return None


def _looks_numeric(valor: Any) -> bool:
    try:
        float(str(valor).strip())
    except ValueError:
        return False
    return True


def _field_label(entity: str, prop: str, kind: str, level: str | None = None, func: int | None = None) -> str:
    if kind == "measure":
        return f"{entity}.{prop} [medida]"
    if kind == "hierarchy":
        return f"{entity}.{prop} [{level}]"
    if kind == "aggregation":
        return f"{entity}.{prop} [{_AGG_LABELS[func]}]"
    return f"{entity}.{prop}"


def _spec_from_select_item(item: dict[str, Any], alias_to_entity: dict[str, str]) -> dict[str, Any] | None:
    """Turn one prototypeQuery Select entry into a field spec, or None if
    its shape isn't one of the three kinds seen live (Column/Measure/
    HierarchyLevel-with-PropertyVariationSource) -- callers must treat
    None as "skip, don't crash the whole schema fetch"."""
    if "Column" in item:
        c = item["Column"]
        entity = alias_to_entity.get(c["Expression"]["SourceRef"]["Source"])
        if entity is None:
            return None
        prop = c["Property"]
        spec = {"entity": entity, "property": prop, "kind": "column", "query_name": f"{entity}.{prop}"}
        dtype = _type_from_node(c) or _type_from_node(item)
        if dtype:
            spec["data_type"] = dtype
        return spec
    if "Measure" in item:
        m = item["Measure"]
        entity = alias_to_entity.get(m["Expression"]["SourceRef"]["Source"])
        if entity is None:
            return None
        prop = m["Property"]
        return {"entity": entity, "property": prop, "kind": "measure", "query_name": f"{entity}.{prop}"}
    if "Aggregation" in item:
        a = item["Aggregation"]
        func = a.get("Function")
        column = (a.get("Expression") or {}).get("Column") or {}
        entity = alias_to_entity.get(column["Expression"]["SourceRef"]["Source"])
        if entity is None or func not in _AGG_LABELS:
            return None
        prop = column["Property"]
        return {
            "entity": entity,
            "property": prop,
            "kind": "aggregation",
            "function": func,
            "query_name": f"{_AGG_LABELS[func]}({entity}.{prop})",
        }
    if "HierarchyLevel" in item:
        hl = item["HierarchyLevel"]
        h = hl["Expression"]["Hierarchy"]
        pvs = h["Expression"].get("PropertyVariationSource")
        if pvs is None:
            # A handful of visuals build hierarchies a different way
            # (confirmed live on indiEstrategiasEmpleabilidad) -- not
            # worth chasing every shape, just skip this field.
            return None
        entity = alias_to_entity.get(pvs["Expression"]["SourceRef"]["Source"])
        if entity is None:
            return None
        prop = pvs["Property"]
        level = hl.get("Level", "?")
        return {
            "entity": entity,
            "property": prop,
            "kind": "hierarchy",
            "level": level,
            "hierarchy_name": h["Hierarchy"],
            "variation_name": pvs["Name"],
            "query_name": f"{entity}.{prop}.{pvs['Name']}.{h['Hierarchy']}.{level}",
        }
    return None


def _collect_fields(exploration: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """campo label -> field spec, scanning every visual's prototypeQuery
    across every section (page) of the report. Sections/visuals with no
    parseable query (text boxes, images, slicer-only containers) simply
    contribute nothing -- not an error."""
    campos: dict[str, dict[str, Any]] = {}
    for section in exploration.get("sections") or []:
        for vc in section.get("visualContainers") or []:
            cfg_raw = vc.get("config")
            if not cfg_raw:
                continue
            try:
                cfg = json.loads(cfg_raw)
            except Exception:
                logger.debug("Config de visualContainer no es JSON válido, se omite.", exc_info=True)
                continue
            query = (cfg.get("singleVisual") or {}).get("prototypeQuery") or {}
            alias_to_entity = {f["Name"]: f["Entity"] for f in query.get("From") or []}
            for sel in query.get("Select") or []:
                try:
                    spec = _spec_from_select_item(sel, alias_to_entity)
                except (KeyError, TypeError):
                    spec = None
                if spec is None:
                    continue
                label = _field_label(spec["entity"], spec["property"], spec["kind"], spec.get("level"), spec.get("function"))
                campos.setdefault(label, spec)
    return campos


def _walk_entity_fields(node: Any, found: dict[str, dict[str, Any]]) -> None:
    """Recursively collect Entity/Property references (Column, Measure,
    Aggregation) anywhere in a report layout, descending into JSON strings.

    Newer reports (confirmed live on the Judicatura dashboards) ship their
    visuals as a PBIR document under exploration.explorationContent -- or as
    configs whose prototypeQuery has no usable From/Select -- so
    _collect_fields finds nothing. The Entity/Property pairs are still there
    in plain JSON, which is all a query needs."""
    if isinstance(node, dict):
        for kind in ("Column", "Measure"):
            body = node.get(kind)
            if isinstance(body, dict) and "Property" in body:
                entity = ((body.get("Expression") or {}).get("SourceRef") or {}).get("Entity")
                if entity and not entity.startswith("LocalDateTable_"):
                    prop = body["Property"]
                    spec_kind = "measure" if kind == "Measure" else "column"
                    label = _field_label(entity, prop, spec_kind)
                    spec = {"entity": entity, "property": prop, "kind": spec_kind, "query_name": f"{entity}.{prop}"}
                    dtype = _type_from_node(body)
                    if dtype and spec_kind == "column":
                        spec["data_type"] = dtype
                    found.setdefault(label, spec)
        agg = node.get("Aggregation")
        if isinstance(agg, dict):
            column = (agg.get("Expression") or {}).get("Column") or {}
            entity = ((column.get("Expression") or {}).get("SourceRef") or {}).get("Entity")
            func = agg.get("Function")
            if entity and column.get("Property") and func in _AGG_LABELS and not entity.startswith("LocalDateTable_"):
                prop = column["Property"]
                label = f"{entity}.{prop} [{_AGG_LABELS[func]}]"
                found.setdefault(
                    label,
                    {
                        "entity": entity,
                        "property": prop,
                        "kind": "aggregation",
                        "function": func,
                        "query_name": f"{_AGG_LABELS[func]}({entity}.{prop})",
                    },
                )
        for value in node.values():
            _walk_entity_fields(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk_entity_fields(value, found)
    elif isinstance(node, str) and node[:1] in ("{", "["):
        try:
            _walk_entity_fields(json.loads(node), found)
        except ValueError:
            pass


async def _get_bootstrap(resource_key: str, indicador: str, base: str = _BASE) -> dict[str, Any]:
    cached = _schema_cache.get(resource_key)
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _schema_cache.get(resource_key)
        if cached is not None:
            return cached

        logger.info("Descargando esquema (modelsAndExploration) SUT Power BI: %s", resource_key)
        url = f"{base}/public/reports/{resource_key}/modelsAndExploration"
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT, "X-PowerBI-ResourceKey": resource_key}
        ) as session:
            resp = await session.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

        models = data.get("models") or []
        model = models[0] if models else {}
        exploration = data.get("exploration") or {}
        campos = _collect_fields(exploration)
        if not campos:
            _walk_entity_fields(exploration, campos)
        campos.update(_MANUAL_CAMPOS.get(indicador, {}))
        result = {
            "report_id": exploration.get("reportId"),
            "model_id": model.get("id"),
            "dataset_id": model.get("dbName"),
            "campos": campos,
        }
        _schema_cache.set(resource_key, result)
        return result


async def get_indicador_schema(indicador: str, fuente: str = "sut") -> dict[str, Any]:
    """
    List every column/measure/date-level findable in one SUT dashboard's
    visuals, discovered from the report's own layout definition (not by
    guessing or clicking through the UI) -- plus a small manually-captured
    set for the two dashboards whose report layout doesn't expose visual
    queries this way (see _MANUAL_CAMPOS).

    Args:
        indicador: A key from list_indicadores(fuente).
        fuente: "sut" (default) or "judicatura".
    """
    info = _lookup(indicador, fuente)

    bootstrap = await _get_bootstrap(info["resource_key"], indicador, info.get("base", _BASE))
    return {
        "indicador": indicador,
        "fuente": fuente,
        "nombre": info["nombre"],
        "campos": sorted(bootstrap["campos"]),
    }


def _build_select_item(spec: dict[str, Any], alias: str) -> dict[str, Any]:
    if spec["kind"] == "measure":
        return {
            "Measure": {"Expression": {"SourceRef": {"Source": alias}}, "Property": spec["property"]},
            "Name": spec["query_name"],
            "NativeReferenceName": spec["property"],
        }
    if spec["kind"] in ("aggregated_sum", "aggregation"):
        # A plain column that visuals aggregate with SUM() at query time,
        # rather than a pre-built DAX measure -- e.g. encuentra_empleo's
        # "Número de Personas". Function 0 is Sum in Power BI's
        # AggregateFunction enum (confirmed live: Function 4 was Min, seen
        # on a "Fecha de Carga" min-date query on the same report).
        return {
            "Aggregation": {
                "Expression": {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": spec["property"]}},
                "Function": spec.get("function", 0),
            },
            "Name": spec["query_name"],
            "NativeReferenceName": spec["property"],
        }
    if spec["kind"] == "hierarchy":
        return {
            "HierarchyLevel": {
                "Expression": {
                    "Hierarchy": {
                        "Expression": {
                            "PropertyVariationSource": {
                                "Expression": {"SourceRef": {"Source": alias}},
                                "Name": spec["variation_name"],
                                "Property": spec["property"],
                            }
                        },
                        "Hierarchy": spec["hierarchy_name"],
                    }
                },
                "Level": spec["level"],
            },
            "Name": spec["query_name"],
            "NativeReferenceName": f"{spec['property']} {spec['level']}",
        }
    return {
        "Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": spec["property"]},
        "Name": spec["query_name"],
        "NativeReferenceName": spec["property"],
    }


def _literal_value(spec: dict[str, Any], valor: Any) -> str:
    """Power BI literal text for a filter value.

    Strings are single-quoted with embedded quotes doubled. When the column's
    discovered `data_type` is numeric/boolean (int/integer/long -> 123L,
    decimal/double/float -> 1.5D, bool/boolean -> true/false) the value is
    emitted as a typed literal; if the type is unknown or the value does not
    parse, the string behavior is kept."""
    kind = str(spec.get("data_type") or "").lower()
    text = str(valor).strip()
    try:
        if kind in ("int", "integer", "int64", "long"):
            return f"{int(text)}L"
        if kind in ("decimal", "double", "float", "number", "numeric"):
            return f"{float(text)!r}D"
        if kind in ("bool", "boolean") and text.lower() in ("true", "false"):
            return text.lower()
    except ValueError:
        pass
    return "'" + str(valor).replace("'", "''") + "'"


def _decode_dsr(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Decode a querydata response's data['dsr'] into full rows, keyed by
    the query_name each Select item was sent with (see module docstring
    for the R/Ø repeat/null-bitmask format)."""
    descriptor_name_by_value = {sel["Value"]: sel["Name"] for sel in data["descriptor"]["Select"]}
    ds0 = data["dsr"]["DS"][0]
    value_dicts = ds0.get("ValueDicts", {})
    dm0 = ((ds0.get("PH") or [{}])[0]).get("DM0") or []

    rows: list[dict[str, Any]] = []
    schema: list[dict[str, Any]] = []
    prev: list[Any] = []
    for entry in dm0:
        if "S" in entry:
            schema = entry["S"]
            prev = [None] * len(schema)
        if "C" not in entry and schema and "R" not in entry and "Ø" not in entry:
            # A one-column result is sent as {"G0": value} (key = the schema
            # column's own name) instead of the C/R/Ø packing; a repeated value
            # simply omits the key (confirmed live on the Judicatura reports).
            cur = list(prev)
            for i, col in enumerate(schema):
                if col["N"] in entry:
                    cur[i] = entry[col["N"]]
            prev = cur
            row = {}
            for col, val in zip(schema, cur):
                if val is not None and "DN" in col and isinstance(val, int):
                    val = value_dicts[col["DN"]][val]
                row[descriptor_name_by_value.get(col["N"], col["N"])] = val
            rows.append(row)
            continue
        c_vals = entry.get("C", [])
        r_mask = entry.get("R", 0)
        o_mask = entry.get("Ø", 0)
        cur = list(prev)
        ci = 0
        for i in range(len(schema)):
            bit = 1 << i
            if r_mask & bit:
                continue
            if o_mask & bit:
                cur[i] = None
                continue
            cur[i] = c_vals[ci]
            ci += 1
        prev = cur

        row: dict[str, Any] = {}
        for col, val in zip(schema, cur):
            if val is not None and "DN" in col and isinstance(val, int):
                val = value_dicts[col["DN"]][val]
            name = descriptor_name_by_value.get(col["N"], col["N"])
            row[name] = val
        rows.append(row)
    return rows


async def query_indicador(
    indicador: str,
    campos: list[str],
    filtros: dict[str, str] | None = None,
    limite: int = _DEFAULT_ROW_LIMIT,
    fuente: str = "sut",
) -> dict[str, Any]:
    """
    Run a live query against one SUT dashboard's semantic model -- any
    combination of the columns/measures/date-levels from
    get_indicador_schema, not just what one specific visual displays
    (this is what makes e.g. month x industry possible even though no
    single chart in the dashboard shows it broken down that way).

    Args:
        indicador: A key from list_indicadores(fuente).
        campos: Field labels exactly as returned by get_indicador_schema
            (e.g. "public contratos.nombre_padre_activ_econ_empresa",
            "Medidas.Cantidad de Contratos [medida]").
        filtros: Optional {campo: valor} equality filters (a plain-column
            campo, not a measure/hierarchy). Values are matched as text.
        limite: Row cap (server-side, via the query's own DataReduction
            window) -- keep well under the platform's context budget.
        fuente: "sut" (default) or "judicatura".
    """
    info = _lookup(indicador, fuente)
    base = info.get("base", _BASE)
    if not campos:
        raise ValueError("Se requiere al menos un campo en 'campos'.")
    limite = max(1, min(int(limite), _MAX_ROW_LIMIT))

    bootstrap = await _get_bootstrap(info["resource_key"], indicador, base)
    campos_by_label = bootstrap["campos"]

    def resolve(label: str) -> dict[str, Any]:
        spec = campos_by_label.get(label)
        if spec is None:
            raise ValueError(
                f"Campo '{label}' no existe en '{indicador}'. "
                "Usa get_sut_indicador_schema para ver los campos válidos."
            )
        return spec

    select_specs = [resolve(c) for c in campos]

    alias_by_entity: dict[str, str] = {}
    entities: list[dict[str, Any]] = []

    def alias_for(entity: str) -> str:
        alias = alias_by_entity.get(entity)
        if alias is None:
            alias = chr(ord("a") + len(alias_by_entity))
            alias_by_entity[entity] = alias
            entities.append({"Name": alias, "Entity": entity, "Type": 0})
        return alias

    select_items = [_build_select_item(spec, alias_for(spec["entity"])) for spec in select_specs]

    where: list[dict[str, Any]] = []
    untyped_numeric: list[str] = []
    for label, valor in (filtros or {}).items():
        fspec = resolve(label)
        if fspec["kind"] != "column":
            raise ValueError(f"El filtro '{label}' debe ser una columna, no una medida/jerarquía.")
        if not fspec.get("data_type") and _looks_numeric(valor):
            untyped_numeric.append(label)
        alias = alias_for(fspec["entity"])
        where.append(
            {
                "Condition": {
                    "In": {
                        "Expressions": [
                            {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": fspec["property"]}}
                        ],
                        "Values": [[{"Literal": {"Value": _literal_value(fspec, valor)}}]],
                    }
                }
            }
        )

    query: dict[str, Any] = {"Version": 2, "From": entities, "Select": select_items}
    if where:
        query["Where"] = where

    body = {
        "version": "1.0.0",
        "queries": [
            {
                "Query": {
                    "Commands": [
                        {
                            "SemanticQueryDataShapeCommand": {
                                "Query": query,
                                "Binding": {
                                    "Primary": {"Groupings": [{"Projections": list(range(len(select_items)))}]},
                                    "DataReduction": {"DataVolume": 4, "Primary": {"Window": {"Count": limite}}},
                                    "Version": 1,
                                },
                                "ExecutionMetricsKind": 1,
                            }
                        }
                    ]
                },
                "QueryId": "",
                "ApplicationContext": {
                    "DatasetId": bootstrap["dataset_id"],
                    "Sources": [{"ReportId": str(bootstrap["report_id"]), "VisualId": "ecuador-datos-mcp"}],
                },
            }
        ],
        "cancelQueries": [],
        "modelId": bootstrap["model_id"],
    }

    async with httpx.AsyncClient(
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json;charset=UTF-8",
            "X-PowerBI-ResourceKey": info["resource_key"],
        }
    ) as session:
        resp = await session.post(f"{base}/public/reports/querydata?synchronous=true", json=body, timeout=_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()

    _raise_on_query_error(payload)
    result = payload["results"][0]["result"]
    if "data" not in result or "dsr" not in result.get("data", {}):
        filas: list[dict[str, Any]] = []
    else:
        filas = _decode_dsr(result["data"])

    out: dict[str, Any] = {
        "indicador": indicador,
        "fuente": fuente,
        "nombre": info["nombre"],
        "campos": campos,
        "filas": filas,
        "limite": limite,
        # The window cap filled up: Power BI reports no "more rows" signal,
        # so hitting the cap exactly is the only hint the result is partial.
        "truncado": len(filas) >= limite,
    }
    if not filas and untyped_numeric:
        out["aviso"] = (
            "Sin filas: el filtro numérico sobre "
            + ", ".join(f"'{c}'" for c in untyped_numeric)
            + " se envió como texto porque no se pudo determinar el tipo de la columna; "
            "si la columna es numérica (p. ej. un año) no coincidirá con ningún valor."
        )
    return out


def _raise_on_query_error(payload: Any) -> None:
    """Power BI answers HTTP 200 to a rejected query, with an error object
    where the rows would be. Surface it instead of reporting zero rows."""
    # The tool layer maps ValueError to a user-facing error, so a non-object
    # body is reported the same way as a rejected query, not as a TypeError.
    error = payload.get("error") if isinstance(payload, dict) else "respuesta no es un objeto JSON"
    results = payload.get("results") if isinstance(payload, dict) else None
    if error is None and isinstance(results, list) and results:
        first = results[0] if isinstance(results[0], dict) else {}
        error = first.get("error") or (first.get("result") or {}).get("error")
    if error is not None:
        if isinstance(error, dict):
            detail = error.get("message") or error.get("code") or json.dumps(error, ensure_ascii=False)
        else:
            detail = str(error)
        raise ValueError(f"Power BI rechazó la consulta: {detail}")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise ValueError("Power BI devolvió una respuesta sin 'results'.")
