# Changelog

Este repositorio es un fork de [DweskZ/EcuDataMCP](https://github.com/DweskZ/EcuDataMCP).

## 0.4.4 — 2026-08-04

### Added
- `format=json` en tools restantes: `get_resource_info`, `get_organization_info`, `search_organizations`, `list_categories`, `get_category_info`, `list_instituciones`, `get_institucion_info`, `get_contrato_info`

## 0.4.3 — 2026-08-04

### Added
- DPA parroquias offline (~1040) + `lookup_ubicacion` con `nivel=parroquia`
- Resource MCP `ecuador://parroquias`
- Script `scripts/fetch_parroquias.py` (fuente ArcGIS Parroquias_del_Ecuador)
- `format=json` en `get_dataset_info`, `list_dataset_resources`, `preview_resource_data`, `query_resource_data`

## 0.4.2 — 2026-08-04

### Added / Improved
- SERCOP: cooldown + negative cache + `SercopRateLimitError` con mensaje claro
- Caché SERCOP ampliada a 30 min; respeta `Retry-After` cuando existe
- `format=json` en `search_tramites`, `search_regulaciones`, `get_tramite_info`, `get_regulacion_info`

## 0.4.1 — 2026-08-04

### Added
- `list_recent_datasets` (CKAN ordenado por `metadata_modified`)
- Smoke e2e `scripts/smoke_e2e.py`
- Más keywords auto-mapeadas en `search_tramites`
- `format=json` en `search_datasets`

## 0.4.0 — 2026-08-04

### Added
- DPA cantones offline (224) + `lookup_ubicacion` con `nivel=provincia|canton|auto`
- Resource MCP `ecuador://cantones`
- Integración SGR: `search_eventos_riesgo` (COE2) y `list_sat_tsunami`
- Prompt MCP `monitorear_riesgos`
- Parámetro `format=text|json` en tools clave (`list_capabilities`, `lookup_ubicacion`, `search_contratos`, eventos/SAT)
- Caché TTL (10 min) para búsquedas SERCOP

### Changed
- `search_contratos` corrige fallback de años cuando `year=0`
- README y capabilities actualizados (23 tools)

## 0.3.2 — 2026-08-04

- `list_capabilities`, `lookup_ubicacion` (provincias), resources `ecuador://*`

## 0.3.1 — 2026-08-04

- Prompts MCP, vínculo trámite→regulaciones, fallback de años SERCOP

## 0.3.0 — 2026-08-04

- Búsqueda unificada, DataStore, preview JSON/XLSX, regulaciones gob.ec, contratos SERCOP, CI/tests
