# Changelog

## 0.5.4 — 2026-08-16

Integración completa de la Superintendencia de Compañías (Supercías):
directorio, ranking financiero, y registro de auditores externos.

### Added
- **Directorio de compañías** (`search_companias`/`get_compania_info`):
  el directorio nacional de compañías (226k+, actualizado a diario) —
  situación legal, representante legal, capital suscrito, CIIU, dirección.
  `helpers/supercias_client.py` parsea el export Excel del portal con
  `ElementTree.iterparse` (el `<dimension>` del archivo viene mal
  declarado y rompe el modo `read_only` de openpyxl), cacheado en memoria
  6h (parseo CPU-bound corre en `asyncio.to_thread` para no bloquear el
  event loop con clientes HTTP concurrentes).
- **Ranking financiero** (`search_ranking`/`get_financials`): segundo
  dataset de Supercías (`bi_ranking.csv`, ~356 MB / ~9M filas) — ingresos,
  activos, patrimonio y ~38 ratios financieros por compañía y año fiscal,
  derivados de balances reales. `helpers/supercias_financials.py` consulta
  un SQLite local construido de antemano por
  `scripts/build_supercias_financials_db.py` (recortado a los últimos 5
  años fiscales, autoajustable), con su propia tabla `companias`
  (expediente, ruc, nombre) cargada desde `bi_compania.csv` — resuelve
  nombre/RUC sin depender del directorio, que se cachea y refresca por
  separado. El build es atómico: construye en `<db>.building`, verifica
  integridad y columnas requeridas, y recién entonces reemplaza la base
  que ya funciona — un build fallido nunca la deja sin datos.
  `helpers/tls.py` gana `legacy_cipher_context()` para el handshake TLS de
  `appscvsmovil.supercias.gob.ec` (host distinto del directorio, exige un
  mínimo de cifrado que OpenSSL 3 rechaza por defecto — mecanismo separado
  del fallback de certificados vencidos).
- **Registro de auditores externos** (`search_auditores`/`get_auditor_info`):
  tercer dataset de Supercías, el registro de firmas/personas autorizadas
  para actuar como auditores externos (1,447 filas, ~190 KB, mismo host y
  patrón de refresco diario que el directorio). `_parse_xlsx` generalizado
  para aceptar `header_markers` configurables, ya que este export usa
  `IDENTIFICACION` como columna de identificación en vez de `RUC`.

## 0.5.1 — 2026-08-13

### Added
- `created` y `last_modified` por recurso en `list_dataset_resources`, para
  poder identificar el archivo más reciente de un dataset con archivos
  periódicos sin tener que llamar a `get_resource_info` por cada uno
- `get_dataset_info` ahora incluye `source_url` (el campo "Fuente" del
  dataset: link a donde la entidad publicadora mantiene el dato original,
  fuera del portal) y `extras` (metadatos personalizados que la entidad haya
  agregado más allá del esquema estándar)
- `preview_resource_data` (CSV) ahora descarta columnas de geometría/WKT
  (`geom`, `wkt`, polígonos detectados por contenido) para no inundar el
  preview con coordenadas, y convierte columnas en formato decimal europeo
  (`7.760,2` → `7760.2`) a notación estándar. El mismo descarte de columnas
  de geometría aplica también al preview de JSON plano (arrays de objetos)
- `list_dataset_resources` ahora avisa cuando 3+ recursos de un dataset
  parecen ser una serie periódica (nombres casi idénticos, solo cambian
  números/fechas), para que quien consulte revise si cada archivo nuevo
  reemplaza a los anteriores o los complementa antes de sumar valores

### Changed
- `CKAN_INSECURE_TLS` ahora es `0` (desactivado) por defecto — el
  certificado de `www.datosabiertos.gob.ec` que expiró el 2026-07-28 fue
  renovado el 2026-08-07 (válido hasta 2026-11-05). Seguía activado por
  defecto desde que se agregó el fallback; poner `CKAN_INSECURE_TLS=1` solo
  si el certificado del portal vuelve a fallar

## 0.5.0 — 2026-08-10

### Added
- Integración Instituto Geofísico EPN (IG-EPN): tool `search_sismos` sobre el
  catálogo sísmico público (`portal/eventos/www/events.csv`) con filtros por
  texto, magnitud mínima y días, hora local (UTC-5) + UTC, y enlace al detalle
  de cada evento
- `helpers/igepn_client.py` con caché TTL (~2 min) y parseo tolerante del CSV
  (cabecera opcional, comas sin comillas en `place`)
- Fuente `igepn` en `ecuador://fuentes`; paso de sismos en el prompt
  `monitorear_riesgos`

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
