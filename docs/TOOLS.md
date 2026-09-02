# Herramientas disponibles

Referencia detallada de las herramientas MCP de EcuDataMCP. Casi todas
aceptan `format="json"` además de texto.

## Entrada unificada

| Tool | Descripción |
|------|-------------|
| `list_capabilities` | Resume fuentes, tools, prompts y límites del servidor. |
| `search_ecuador` | Busca a la vez en datasets, organizaciones, trámites, regulaciones, contratos y riesgos. |
| `lookup_ubicacion` | Provincias, cantones y parroquias con códigos INEC, región y población. |

## Datos abiertos

| Tool | Descripción |
|------|-------------|
| `search_datasets` | Buscar datasets por palabras clave y categoría. Expande siglas comunes como ENEMDU, RUC e IESS. |
| `list_recent_datasets` | Datasets más recientemente actualizados en el portal. |
| `get_dataset_info` | Metadata detallada de un dataset: título, descripción, organización, tags, licencia y fechas. |
| `list_dataset_resources` | Listar los archivos de un dataset con formato, tamaño, URL y fechas de creación/modificación. |
| `get_resource_info` | Información detallada de un archivo específico. |
| `preview_resource_data` | Preview de CSV/TSV, JSON/GeoJSON, Excel (XLS/XLSX) o archivos comprimidos compatibles como tabla. |
| `download_resource` | Descargar el archivo crudo de un recurso en base64 para formatos que no se pueden previsualizar como tabla. |
| `query_resource_data` | Consulta tabular vía CKAN DataStore con filtros, texto y paginación. |
| `detect_series_pattern` | Comparar archivos periódicos para determinar si son acumulados o incrementales. |
| `search_sri_datasets` | Buscar archivos estadísticos del SRI publicados fuera del portal CKAN. |
| `search_sri_estadisticas_recaudacion` | Buscar reportes públicos de recaudación por impuesto, provincia, cantón y actividad económica. |
| `get_sri_ruc_info` | Consultar la ficha pública de un RUC exacto, incluidos establecimientos. |
| `search_sri_ruc` | Buscar contribuyentes en el RUC por razón social o nombre comercial. |
| `list_sri_saiku_cubes` | Listar cubos OLAP visibles en la instancia pública de Saiku del SRI. |
| `describe_sri_saiku_cube` | Ver dimensiones, jerarquías, niveles y medidas de un cubo Saiku público. |
| `query_sri_saiku_aggregate` | Ejecutar una consulta agregada limitada con una dimensión y una medida. |

Los tools CKAN aceptan `source="nacional"` (default) o `source="cuenca"`
para consultar el catálogo nacional o el portal municipal Cuenca en Datos.

## Trámites gubernamentales

| Tool | Descripción |
|------|-------------|
| `search_tramites` | Buscar trámites del gobierno ecuatoriano. |
| `get_tramite_info` | Detalle completo: requisitos, procedimiento, costo y tiempo estimado. |
| `get_tramite_estadisticas` | Serie mensual de atenciones/quejas de transparencia de un trámite, desde 2021. |
| `list_instituciones` | Listar instituciones públicas del Ecuador. |
| `get_institucion_info` | Detalle de una institución: sector, web y descripción. |

## ANDA (INEC)

| Tool | Descripción |
|------|-------------|
| `search_anda` | Buscar encuestas y censos en el catálogo ANDA/NADA del INEC. |
| `get_anda_survey_info` | Metadata completa de una encuesta: resumen, variables, confidencialidad y contacto. |
| `download_anda_microdata` | Links directos de descarga de archivos de microdatos. |

## Ecuador en Cifras (INEC)

| Tool | Descripción |
|------|-------------|
| `search_inec_estadisticas` | Buscar temas estadísticos como IPC, ENEMDU, ENSANUT y pobreza. |
| `get_inec_estadistica_files` | Links directos a boletines, metodologías y series históricas. |
| `search_inec_publicaciones` | Búsqueda de texto completo en las publicaciones de INEC. |
| `get_inec_publicacion_archivos` | Links directos de una publicación específica. |
| `search_biinec_extras` | Lista verificada de registros exclusivos del BIINEC. |
| `search_censo_recursos` | Microdatos completos del Censo 2022 y recursos históricos relacionados. |

## Macroeconomía (BCE)

| Tool | Descripción |
|------|-------------|
| `search_indicadores_bce` | Buscar en el catálogo estadístico BCEData. |
| `get_indicador_bce` | Serie temporal por grupo, período, frecuencia y unidad. |
| `audit_bce_catalog` | Auditar grupos, series, secciones, frecuencias, unidades, rangos y errores de carga; puede probar valores recientes de `/grid` y guardar snapshots. |
| `compare_bce_sources` | Generar un mapa candidato de traslapes entre etiquetas de BCEData e IEM, sin declarar equivalencias metodológicas automáticamente. |
| `search_bce_iem` | Buscar tablas XLSX individuales del archivo IEM, actual o histórico; `hash_archivos=true` permite un manifiesto SHA-256 acotado. |
| `get_bce_iem_table` | Leer una tabla XLSX IEM con filtro de período y elegir una versión histórica. |

## Compañías (Supercías)

| Tool | Descripción |
|------|-------------|
| `search_companias` | Buscar compañías por nombre, RUC, provincia o situación legal. |
| `get_compania_info` | Ficha completa de una compañía. |
| `search_ranking` | Rankear o filtrar compañías por indicadores financieros. |
| `get_financials` | Historial financiero y ratios de una compañía. |
| `search_auditores` | Buscar auditores externos autorizados. |
| `get_auditor_info` | Ficha completa de un auditor externo. |

## Regulaciones y contratos

| Tool | Descripción |
|------|-------------|
| `search_regulaciones` | Buscar o listar regulaciones en gob.ec. |
| `get_regulacion_info` | Detalle de una regulación y enlace al PDF. |
| `search_contratos` | Buscar procedimientos de contratación pública en SERCOP/OCDS. |
| `get_contrato_info` | Expediente OCDS con comprador, licitación, adjudicaciones y contratos. |

## Riesgos y sismos

| Tool | Descripción |
|------|-------------|
| `search_eventos_riesgo` | Buscar eventos de emergencia o riesgo del COE. |
| `list_sat_tsunami` | Listar estaciones SAT de alerta temprana por tsunami. |
| `search_sismos` | Buscar sismos recientes del catálogo IG-EPN. |

## Exploración

| Tool | Descripción |
|------|-------------|
| `search_organizations` | Buscar instituciones que publican datos. |
| `get_organization_info` | Información de una organización y sus datasets. |
| `list_categories` | Listar categorías temáticas con conteo de datasets. |
| `get_category_info` | Detalle de una categoría y datasets de ejemplo. |

## Flujo de trabajo típico

```text
1. search_ecuador("recaudación tributaria")  → Orientación rápida
2. list_dataset_resources("dataset-id")       → Ve los archivos disponibles
3. query_resource_data("resource-id", ...)     → Consulta tabular (DataStore)
   o preview_resource_data("resource-id")      → Preview del archivo
```

## Prompts MCP

Plantillas listas para el cliente: `explorar_datos`, `explorar_tema`,
`consultar_tramite`, `investigar_contrato`, `buscar_regulacion`, `buscar_inec`
y `monitorear_riesgos`.

## Resources MCP

| URI | Contenido |
|-----|-----------|
| `ecuador://fuentes` | Fuentes integradas y tools asociadas. |
| `ecuador://provincias` | 24 provincias. |
| `ecuador://cantones` | 224 cantones. |
| `ecuador://parroquias` | Parroquias con referencia geográfica. |
| `ecuador://instituciones-clave` | IDs frecuentes de gob.ec. |
## Auditorías BCEData e IEM

- `audit_bce_catalog` comprueba el catálogo BCEData, puede persistir snapshots
  y comparar el actual con el último completo.
- `search_bce_iem` descubre tablas del boletín mensual o archivo histórico;
  puede guardar el catálogo y calcular hashes XLSX de forma acotada.
- `compare_bce_sources` genera candidatos BCEData ↔ IEM. Con
  `guardar_revision=true` guarda una cola revisable bajo
  `BCE_EQUIVALENCE_REVIEW_DIR`; nunca declara equivalencia metodológica solo
  por el título.
