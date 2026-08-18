# Changelog

## Unreleased

Integración con el Banco Central del Ecuador (BCEData) y datasets del SRI,
más integración completa de la Superintendencia de Compañías (Supercías):
directorio, ranking financiero, y registro de auditores externos. Prompt
`explorar_tema`, tool `download_resource`, y verificación e2e de cifras de
referencia del roadmap. Endurecimiento de seguridad e infraestructura
(guardia SSRF, uv.lock, Dockerfile, CI).

### Added
- Integración con el Banco Central del Ecuador vía BCEData
  (`contenido.bce.fin.ec/wp-json/bcedata/v1/`): API REST pública y sin
  autenticación, no documentada oficialmente pero descubierta inspeccionando
  el tráfico de red de la app JS del propio BCE (`contenido.bce.fin.ec/bcedata/`)
  y verificada con `curl` plano. Nuevos tools `search_indicadores_bce` (busca
  en el catálogo de ~78 grupos de indicadores: monetario/financiero, finanzas
  públicas, sector externo, sector real) y `get_indicador_bce` (serie de
  tiempo de un grupo, con frecuencia/unidad/rango configurables y defaults
  tomados de la metadata propia del grupo).
- `helpers/bce_client.py`: cachea el árbol completo del catálogo en memoria
  (~98 nodos, TTL 24h — es efectivamente estático) y cada bundle de metadata
  por grupo consultado; la serie de tiempo en sí no se cachea, se pide fresca
  cada vez.
- `search_indicadores_bce` también busca en los nombres de las series
  individuales dentro de cada grupo, no solo en el título del grupo —
  verificado que "desempleo" no aparece en ningún título de grupo (vive
  como serie dentro de "Indicadores del mercado laboral..."), así que una
  búsqueda por título solo se lo hubiera perdido. Arma un índice
  consultando el bundle de los ~78 grupos concurrentemente (primer uso
  tras expirar el caché de 24h tarda ~10-15s), deduplicando series con
  nombre idéntico repetido entre desagregaciones (ej. "DESEMPLEO" aparece
  igual en nacional/urbano/rural).
- Integración con el SRI: tool `search_sri_datasets` sobre `helpers/sri_client.py`,
  que indexa los ~130 archivos (catastro RUC por provincia, recaudación,
  ventas/compras, vehículos, CEL, diccionarios de variables) que el SRI
  publica en su propia página (`sri.gob.ec/datasets`), fuera del portal
  CKAN, por lo que `search_datasets` no los encuentra. Esa página es un
  CMS Liferay sin API — cada archivo vive en un `<p>` con una etiqueta
  corta junto al link de descarga; **ojo:** el agrupamiento por sección que
  ofrece el HTML no es confiable (al menos una sección está mal titulada:
  "Prueba" contiene en realidad los archivos reales de Recaudación), así
  que el parser indexa cada archivo por su propia etiqueta/URL en vez de
  confiar en el título de la sección que lo contiene. Caché de 6h.
- Fuente `sri` en `ecuador://fuentes`
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
- Prompt MCP `explorar_tema`: exploración temática transversal (datasets,
  trámites, regulaciones, contratos y riesgos) en una sola guía, en vez de
  requerir un prompt por fuente
- Tool `download_resource(resource_id, format="json")`: baja el archivo
  crudo de un recurso en base64 (máx. 5 MB, mismo límite que
  `preview_resource_data`) para formatos que no se pueden previsualizar
  como tabla — pensado sobre todo para `.rar`, `.tar.gz` y `.xls` legacy,
  pero sirve para cualquier resource_id. `format="text"` (el default) solo
  confirma la descarga; hace falta `format="json"` para recibir
  `content_base64`
- `preview_resource_data` señala `.rar`, `.tar.gz` y `.xls` explícitamente
  (`rar_no_soportado`, `tar_gz_no_soportado`, `xls_no_soportado`, antes
  algunos de estos caían en el genérico "formato no soportado" o incluso
  se intentaban parsear como CSV — ver fix debajo), y esos mensajes apuntan
  a `download_resource`
- `helpers/safe_download.py`: guardia SSRF centralizada (`assert_public_url`,
  `safe_stream`) para descargas cuya URL viene de metadata externa no
  confiable — hoy `preview_resource_data` y `download_resource` (URLs de
  recursos CKAN, definidas por quien publica el dataset, no por este código).
  Valida la URL inicial y cada hop de redirección contra IPs
  privadas/loopback/link-local/multicast/reservadas/no especificadas antes
  de conectar; tope de 5 redirecciones. No cubre DNS rebinding (documentado
  explícitamente en el docstring del módulo).
- `helpers/csv_reader.py`: `download_bytes()` ahora usa `safe_stream()` en
  vez de `httpx` con `follow_redirects=True`.

### Changed
- `uv.lock` ahora se commitea (`.gitignore` tenía `*.lock` sin excepción);
  CI usa `uv sync --locked` y corre en Python 3.11/3.12/3.13 (antes solo
  3.12, pese a que `pyproject.toml` declara `>=3.11` y el Dockerfile usa
  3.13).
- Dockerfile: copiaba `pyproject.toml` e instalaba antes de copiar el código
  fuente — `pip install .` corría sin los paquetes (`helpers/`, `tools/`,
  etc.) ni el `README.md` que el propio `pyproject.toml` declara, y solo
  "funcionaba" porque el `COPY . .` posterior ponía los archivos crudos en
  el path de Python. Ahora usa `uv sync --locked --no-dev` con el código
  copiado antes.
- Nuevo `.dockerignore` (`.git/`, `.env`, caches, `tests/` no entraban al
  build context antes).

### Fixed
- `preview_resource_data` evaluaba el `format` declarado por CKAN *antes*
  que la extensión de la URL del recurso. Un recurso declarado `CSV` en
  CKAN pero servido como `.tar.gz` o `.xlsx` (ambos casos reales,
  encontrados en SRI y MPCEIP durante la verificación e2e) terminaba
  enviado al parser de CSV en vez de a un mensaje de error o al parser
  correcto. Ahora una extensión de URL reconocible tiene prioridad sobre
  un `format` declarado inconsistente
- Límite de descarga de 5 MB inconsistente: el chequeo de `Content-Length`
  usaba `>` pero el acumulador de bytes en streaming usaba `>=`, así que un
  archivo de exactamente 5 MB podía marcarse como truncado pese a que la
  documentación dice "máx. 5 MB". Ambos chequeos ahora usan `>`

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
