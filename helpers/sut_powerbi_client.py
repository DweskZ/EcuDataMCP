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
_INDICADORES_BY_KEY = {i["indicador"]: i for i in _INDICADORES}

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


def list_indicadores() -> list[dict[str, str]]:
    """The eight fixed SUT Power BI dashboards."""
    return [dict(i) for i in _INDICADORES]


def _field_label(entity: str, prop: str, kind: str, level: str | None = None) -> str:
    if kind == "measure":
        return f"{entity}.{prop} [medida]"
    if kind == "hierarchy":
        return f"{entity}.{prop} [{level}]"
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
        return {"entity": entity, "property": prop, "kind": "column", "query_name": f"{entity}.{prop}"}
    if "Measure" in item:
        m = item["Measure"]
        entity = alias_to_entity.get(m["Expression"]["SourceRef"]["Source"])
        if entity is None:
            return None
        prop = m["Property"]
        return {"entity": entity, "property": prop, "kind": "measure", "query_name": f"{entity}.{prop}"}
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
                label = _field_label(spec["entity"], spec["property"], spec["kind"], spec.get("level"))
                campos.setdefault(label, spec)
    return campos


async def _get_bootstrap(resource_key: str, indicador: str) -> dict[str, Any]:
    cached = _schema_cache.get(resource_key)
    if cached is not None:
        return cached

    async with _fetch_lock:
        cached = _schema_cache.get(resource_key)
        if cached is not None:
            return cached

        logger.info("Descargando esquema (modelsAndExploration) SUT Power BI: %s", resource_key)
        url = f"{_BASE}/public/reports/{resource_key}/modelsAndExploration"
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
        campos.update(_MANUAL_CAMPOS.get(indicador, {}))
        result = {
            "report_id": exploration.get("reportId"),
            "model_id": model.get("id"),
            "dataset_id": model.get("dbName"),
            "campos": campos,
        }
        _schema_cache.set(resource_key, result)
        return result


async def get_indicador_schema(indicador: str) -> dict[str, Any]:
    """
    List every column/measure/date-level findable in one SUT dashboard's
    visuals, discovered from the report's own layout definition (not by
    guessing or clicking through the UI) -- plus a small manually-captured
    set for the two dashboards whose report layout doesn't expose visual
    queries this way (see _MANUAL_CAMPOS).

    Args:
        indicador: A key from list_indicadores().
    """
    info = _INDICADORES_BY_KEY.get(indicador)
    if info is None:
        valid = ", ".join(sorted(_INDICADORES_BY_KEY))
        raise ValueError(f"Indicador '{indicador}' no reconocido. Válidos: {valid}")

    bootstrap = await _get_bootstrap(info["resource_key"], indicador)
    return {
        "indicador": indicador,
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
    if spec["kind"] == "aggregated_sum":
        # A plain column that visuals aggregate with SUM() at query time,
        # rather than a pre-built DAX measure -- e.g. encuentra_empleo's
        # "Número de Personas". Function 0 is Sum in Power BI's
        # AggregateFunction enum (confirmed live: Function 4 was Min, seen
        # on a "Fecha de Carga" min-date query on the same report).
        return {
            "Aggregation": {
                "Expression": {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": spec["property"]}},
                "Function": 0,
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
) -> dict[str, Any]:
    """
    Run a live query against one SUT dashboard's semantic model -- any
    combination of the columns/measures/date-levels from
    get_indicador_schema, not just what one specific visual displays
    (this is what makes e.g. month x industry possible even though no
    single chart in the dashboard shows it broken down that way).

    Args:
        indicador: A key from list_indicadores().
        campos: Field labels exactly as returned by get_indicador_schema
            (e.g. "public contratos.nombre_padre_activ_econ_empresa",
            "Medidas.Cantidad de Contratos [medida]").
        filtros: Optional {campo: valor} equality filters (a plain-column
            campo, not a measure/hierarchy). Values are matched as text.
        limite: Row cap (server-side, via the query's own DataReduction
            window) -- keep well under the platform's context budget.
    """
    info = _INDICADORES_BY_KEY.get(indicador)
    if info is None:
        valid = ", ".join(sorted(_INDICADORES_BY_KEY))
        raise ValueError(f"Indicador '{indicador}' no reconocido. Válidos: {valid}")
    if not campos:
        raise ValueError("Se requiere al menos un campo en 'campos'.")

    bootstrap = await _get_bootstrap(info["resource_key"], indicador)
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
    for label, valor in (filtros or {}).items():
        fspec = resolve(label)
        if fspec["kind"] != "column":
            raise ValueError(f"El filtro '{label}' debe ser una columna, no una medida/jerarquía.")
        alias = alias_for(fspec["entity"])
        where.append(
            {
                "Condition": {
                    "In": {
                        "Expressions": [
                            {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": fspec["property"]}}
                        ],
                        "Values": [[{"Literal": {"Value": f"'{valor}'"}}]],
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
        resp = await session.post(f"{_BASE}/public/reports/querydata?synchronous=true", json=body, timeout=_TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()

    result = payload["results"][0]["result"]
    if "data" not in result or "dsr" not in result.get("data", {}):
        filas: list[dict[str, Any]] = []
    else:
        filas = _decode_dsr(result["data"])

    return {"indicador": indicador, "nombre": info["nombre"], "campos": campos, "filas": filas}
