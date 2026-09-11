# Herramientas disponibles

Referencia detallada de las 115 herramientas MCP de EcuDataMCP. Casi todas
aceptan `format="json"` además de texto.

## Entrada unificada

| Tool | Descripción |
|------|-------------|
| `list_capabilities` | Resume fuentes, tools, prompts y límites del servidor. |
| `search_ecuador` | Busca a la vez en datasets, orgs, trámites, regulaciones, contratos y riesgos. |
| `lookup_ubicacion` | Provincias, cantones y parroquias (código INEC, región, población). |

## Datos Abiertos

| Tool | Descripción |
|------|-------------|
| `search_datasets` | Buscar datasets por palabras clave. Soporta filtro por categoría. |
| `list_recent_datasets` | Datasets más recientemente actualizados en el portal. |
| `get_dataset_info` | Metadata detallada de un dataset: título, descripción, organización, tags, licencia, fechas. |
| `list_dataset_resources` | Listar todos los archivos (recursos) de un dataset con formato, tamaño, URL y fechas de creación/modificación. |
| `get_resource_info` | Información detallada de un archivo específico. |
| `preview_resource_data` | Preview de CSV/TSV, JSON/GeoJSON o Excel (XLS/XLSX) como tabla (máx. 5 MB). |
| `download_resource` | Baja el archivo crudo de un recurso en base64 (máx. 5 MB), para formatos que no se pueden previsualizar como tabla (.rar, .tar.gz, etc.). |
| `query_resource_data` | Consulta tabular vía CKAN DataStore (filtros, texto, paginación) sin descargar el archivo. |
| `detect_series_pattern` | Para datasets con un archivo por período: determina si cada archivo nuevo reemplaza a los anteriores (acumulado) o los complementa (incremental). |
| `search_sri_datasets` | Buscar entre ~130 archivos del SRI publicados fuera del portal CKAN: catastro RUC por provincia, recaudación, ventas/compras, vehículos, CEL, diccionarios de variables. |

Los tools CKAN genéricos aceptan `source="nacional"` (default), `source="cuenca"` o `source="latacunga"` (portales municipales), o `source="iadb"` (data.iadb.org, el portal de datos abiertos del BID — NO exclusivo de Ecuador, un catálogo regional/global: Latin Macro Watch e indicadores del Banco Mundial/BID).

## Trámites Gubernamentales

| Tool | Descripción |
|------|-------------|
| `search_tramites` | Buscar trámites del gobierno ecuatoriano (cédula, pasaporte, RUC, licencia, etc.). |
| `get_tramite_info` | Detalle completo: requisitos, procedimiento, costo, tiempo estimado. |
| `get_tramite_estadisticas` | Serie mensual de atenciones/quejas de transparencia de un trámite, desde 2021. |
| `list_instituciones` | Listar instituciones públicas del Ecuador. |
| `get_institucion_info` | Detalle de una institución (sector, web, descripción). |

## ANDA (INEC)

| Tool | Descripción |
|------|-------------|
| `search_anda` | Buscar encuestas y censos en el catálogo ANDA del INEC (NADA/IHSN). Indica si cada encuesta tiene microdatos descargables. |
| `get_anda_survey_info` | Metadata completa de una encuesta ANDA: resumen, variables, confidencialidad y contacto. |
| `download_anda_microdata` | Links directos de descarga de los archivos de microdatos de una encuesta ANDA. |

## Macroeconomía (BCE)

| Tool | Descripción |
|------|-------------|
| `search_indicadores_bce` | Buscar en el catálogo estadístico del Banco Central del Ecuador (monetario/financiero, finanzas públicas, sector externo, sector real). |
| `get_indicador_bce` | Serie de tiempo de un indicador por id_grupo: período, frecuencia y unidad configurables (defaults según el grupo). |

## Compañías (Supercías)

| Tool | Descripción |
|------|-------------|
| `search_companias` | Buscar en el directorio de compañías de la Superintendencia de Compañías (226k+, por nombre/RUC, provincia, situación legal). |
| `get_compania_info` | Ficha completa de una compañía por RUC: representante legal, capital suscrito, CIIU, dirección. |
| `search_ranking` | Rankear/filtrar compañías por indicadores financieros (año, CIIU, cualquier columna); requiere el build local de la base financiera. |
| `get_financials` | Historial financiero de una compañía por expediente o RUC: ingresos, activos, patrimonio, ~38 ratios (liquidez, endeudamiento, rentabilidad). |
| `search_auditores` | Buscar en el registro de auditores externos autorizados (1,447 firmas/personas, por nombre o identificación, provincia). |
| `get_auditor_info` | Ficha completa de un auditor externo por identificación: resolución de autorización, nacionalidad, dirección, contacto. |

## Regulaciones y contratos

| Tool | Descripción |
|------|-------------|
| `search_regulaciones` | Buscar/listar regulaciones en gob.ec (con referencia al Registro Oficial). |
| `get_regulacion_info` | Detalle de una regulación + enlace al PDF. |
| `search_contratos` | Buscar procedimientos de contratación pública (SERCOP/OCDS). |
| `get_contrato_info` | Expediente OCDS: comprador, licitación, adjudicaciones, contratos. |

## Riesgos y sismos

| Tool | Descripción |
|------|-------------|
| `search_eventos_riesgo` | Eventos de emergencia/riesgo del COE (deslizamientos, inundaciones, etc.). |
| `list_sat_tsunami` | Estaciones SAT de alerta temprana por tsunami. |
| `search_sismos` | Sismos recientes del catálogo del Instituto Geofísico (IG-EPN): magnitud, profundidad, ubicación y estado de revisión. |
| `search_sgr_sitreps` | Archivo histórico de eventos adversos de la SGR (2016-2026). |
| `get_sgr_sitrep_archivos` | Reportes SITREP en PDF de un evento adverso de la SGR. |
| `list_sgr_biblioteca_categorias` | Categorías de la biblioteca documental de la SGR (~1660 documentos). |
| `get_sgr_biblioteca_categoria_archivos` | Documentos de una categoría de la biblioteca de la SGR. |
| `search_inamhi_capas` | Catálogo de capas del geoportal de INAMHI (meteorología e hidrología). |
| `get_inamhi_capa_datos` | Muestra de atributos reales de una capa del geoportal de INAMHI. |

## Exploración

| Tool | Descripción |
|------|-------------|
| `search_organizations` | Buscar entre 98+ instituciones que publican datos (INEC, SRI, BCE, MSP, etc.). |
| `get_organization_info` | Info de una organización, con datasets filtrables por texto. |
| `list_categories` | Categorías temáticas con conteo de datasets. |
| `get_category_info` | Detalle de una categoría y datasets de ejemplo. |

## BCE y series especializadas

| Tool | Descripción |
|------|-------------|
| `audit_bce_catalog` | Audita en vivo el catálogo BCEData y reporta su cobertura. |
| `compare_bce_sources` | Construye un mapa cauteloso de equivalencias candidatas entre BCEData e IEM. |
| `get_bce_iem_table` | Inspecciona una tabla XLSX oficial del boletín IEM más reciente del BCE. |
| `get_bce_indicador_diario` | Obtiene la serie temporal de un indicador diario/mensual del BCE (ej. Riesgo País). |
| `list_bce_indicadores_diarios` | Lista la familia de widgets "indicador" diarios/mensuales del BCE, publicados fuera de BCEData e IEM (páginas de widgets Highcharts de contenido.bce.fin.ec) — incluye Riesgo País (EMBI) como serie genuinamente diaria desde 2004, que BCEData solo expone como agregado mensual de fin de período. |
| `search_bce_iem` | Busca tablas individuales de Excel en el último boletín IEM del BCE. |
| `search_bce_remesas` | Lista los enlaces directos a archivos de Remesas de Trabajadores del BCE. |
| `search_bce_publicaciones` | Publicaciones recientes del BCE (boletines, reportes, avisos). |
| `search_bce_indices` | Catálogo de páginas "índice" del BCE con archivo histórico por serie. |
| `get_bce_indice_archivo` | Archivo de archivos de una página "índice" del BCE. |
| `search_bce_precios_comex` | Índices de precios de comercio exterior del BCE, desagregados. |
| `search_bce_calendario` | Calendario de publicaciones estadísticas programadas del BCE. |
| `search_bce_cuentas_nacionales` | Páginas de publicación de Cuentas Nacionales del BCE. |
| `get_bce_cuentas_nacionales_archivo` | Listado de archivos de una página de Cuentas Nacionales del BCE. |

## INEC: estadísticas, BIINEC y censo

| Tool | Descripción |
|------|-------------|
| `get_inec_estadistica_files` | Lista los enlaces directos a archivos publicados en una página de tema estadístico del INEC. |
| `get_inec_publicacion_archivos` | Lista los enlaces directos a archivos (PDF/XLSX/CSV/ZIP) incrustados en una publicación del INEC encontrada vía search_inec_publicaciones. |
| `search_biinec_extras` | Revisa el BIINEC ("Banco de Datos Abiertos") del INEC en busca de datos que no aparecen en search_anda ni en search_inec_estadisticas. |
| `search_censo_recursos` | Busca en el micrositio dedicado del Censo 2022 del INEC (censoecuador.gob.ec) enlaces directos a archivos de microdatos/metodología. |
| `search_inec_estadisticas` | Busca en las páginas de temas estadísticos del INEC (ecuadorencifras.gob.ec). |
| `search_inec_publicaciones` | Busca en todas las publicaciones del INEC en Ecuador en Cifras, vía su API REST pública de WordPress -- siempre actualizada, más recientes primero. |

## SRI: RUC y recaudación

| Tool | Descripción |
|------|-------------|
| `get_sri_ruc_info` | Consultar la información pública de un contribuyente por RUC en el SRI. |
| `search_sri_estadisticas_recaudacion` | Busca en la página "Estadísticas de Recaudación" del SRI enlaces directos a archivos. |
| `search_sri_ruc` | Buscar contribuyentes en el RUC del SRI por razón social o nombre comercial (texto parcial), sin necesitar el RUC exacto de antemano. |

## SIPA, Contraloría y Superbancos

| Tool | Descripción |
|------|-------------|
| `get_contraloria_informe` | Descarga y previsualiza un documento de la Contraloría (Datos Abiertos o Plan Anual de Control). |
| `get_sipa_modulo_archivos` | Lista los enlaces de descarga directa publicados en un módulo de estadísticas de SIPA. |
| `get_superbancos_seccion_archivos` | Lista los enlaces de descarga directa publicados en una sección de estadísticas de Superbancos. |
| `list_contraloria_informes` | Lista los documentos "Datos Abiertos" y "Plan Anual de Control" de la Contraloría General del Estado. |
| `list_sipa_modulos` | Lista los módulos de descarga de estadísticas de SIPA (sipa.agricultura.gob.ec). |
| `list_superbancos_secciones` | Lista las secciones de estadísticas de la Superintendencia de Bancos (superbancos.gob.ec/estadisticas/portalestudios/). |
| `get_sipa_resumen_indicadores` | PDF mensuales del "Resumen de Indicadores" de SIPA (Ministerio de Agricultura), por año. |
| `search_sipa_geoportal_capas` | Catálogo de capas del geoportal del Ministerio de Agricultura (SIPA). |
| `get_sipa_geoportal_capa_datos` | Muestra de atributos reales de una capa del geoportal de SIPA. |

## CENACE, SUT e IG-EPN

| Tool | Descripción |
|------|-------------|
| `get_cenace_tablero` | Obtiene un tablero del snapshot en vivo de la operación de la red eléctrica de CENACE (el operador nacional de Ecuador) — mezcla de generación y demanda, siempre al instante. |
| `get_informe_igepn` | Descarga y extrae el texto de un informe del IG-EPN encontrado vía search_informes_igepn. |
| `get_sut_indicador_schema` | Lista las columnas/medidas/niveles de fecha consultables de un tablero Power BI del SUT, descubiertos desde la definición propia del reporte (la consulta subyacente de cada visual), no por adivinanza. |
| `list_sut_indicadores` | Lista los tableros públicos de Power BI "Indicadores" del Ministerio del Trabajo/SUT (sut.trabajo.gob.ec/mrl/contenido/indicadores/*.xhtml). |
| `query_sut_indicador` | Ejecuta una consulta en vivo contra el modelo de datos subyacente de un tablero Power BI del SUT — cualquier combinación de sus campos, ej. mes y provincia juntos. |
| `search_informes_igepn` | Busca en el archivo de informes PDF del IG-EPN (Instituto Geofísico): boletines sísmicos diarios/semanales/mensuales/especiales, alertas volcánicas "IG Al Instante", informes de campo/anuales, etc. |

## Utilidades de investigación

| Tool | Descripción |
|------|-------------|
| `investigate_dataset` | Atajo de investigación en un solo paso: busca un dataset, lista sus recursos, y previsualiza los datos reales del más prometedor -- el flujo search_datasets -> list_dataset_resources -> preview_resource_data en una sola llamada, para el caso común de "encuéntrame datos sobre X y muéstrame qué hay dentro" |
| `list_zip_contents` | Lista los archivos miembro (nombre, tamaño) de un .zip desde una URL directa, sin descargar el archivo completo. |
| `read_pdf` | Extrae texto de un documento PDF en una URL directa. |

## SEPS y economía popular

| Tool | Descripción |
|------|-------------|
| `list_seps_secciones` | Secciones de estadísticas de la SEPS (sector financiero popular y solidario). |
| `get_seps_seccion_archivos` | Documentos de una sección de estadísticas de la SEPS. |

## IESS: documentos institucionales

| Tool | Descripción |
|------|-------------|
| `list_iess_colecciones` | Colecciones documentales del IESS (boletines, estudios actuariales, auditorías). |
| `get_iess_archivos` | Documentos de una colección del IESS. |

## INEVAL: evaluación educativa

| Tool | Descripción |
|------|-------------|
| `list_ineval_familias` | Familias de evaluación del INEVAL con página de bases de datos. |
| `get_ineval_familia_archivos` | Enlaces de descarga de una familia de evaluación del INEVAL. |

## Aviación civil (DGAC)

| Tool | Descripción |
|------|-------------|
| `get_metar` | Reportes METAR/SPECI recientes de un aeródromo ecuatoriano. |
| `get_notam` | NOTAMs activos para un aeródromo ecuatoriano. |
| `get_sigmet` | SIGMET activos para el espacio aéreo ecuatoriano (FIR único). |
| `list_aip_aerodromos` | Lista de aeródromos/helipuertos con ficha AIP publicada. |
| `get_aip_aerodromo` | Ficha AIP AD 2.x completa de un aeródromo ecuatoriano. |

## ARCOTEL: telecomunicaciones

| Tool | Descripción |
|------|-------------|
| `search_arcotel_reportes_mensuales` | Reportes estadísticos mensuales de ARCOTEL sobre telecomunicaciones. |
| `search_arcotel_boletines` | Boletines estadísticos anuales/temáticos de ARCOTEL sobre telecomunicaciones. |

## ARCSA: registro sanitario

| Tool | Descripción |
|------|-------------|
| `list_arcsa_categorias` | Categorías del registro sanitario de ARCSA (Base de Registros Emitidos). |
| `get_arcsa_categoria_archivos` | Documentos de una categoría del registro sanitario de ARCSA. |

## Fuentes sectoriales adicionales

| Tool | Descripción |
|------|-------------|
| `search_cnig_femicidios` | Estadísticas de violencia de género del CNIG, incluyendo femicidios. |
| `search_minedec_matricula` | Registro histórico de matrícula de educación básica y bachillerato. |
| `search_mef_fiscal` | Cifras fiscales de Ecuador (MEF/MDEP o SENAE), incluyendo ingresos arancelarios. |
| `search_infomies_bases_mensuales` | Bases de datos mensuales de infoMIES (inclusión económica y social). |
| `search_infomies_boletines_zonales` | Boletines zonales de infoMIES, por zona o consolidados por año. |
| `search_trabajo_boletin_anual` | Boletín estadístico anual del mercado laboral ecuatoriano. |
| `search_salarios_sectoriales` | Tablas de salarios mínimos sectoriales de Ecuador. |
| `search_senescyt_estadisticas` | Reportes del SIAU de SENESCYT: estadísticas de educación superior y CTI. |
| `list_senescyt_biblioteca_categorias` | Categorías de la Biblioteca de Educación Superior (MINEDEC/SENESCYT). |
| `get_senescyt_biblioteca_categoria_archivos` | Documentos de una categoría de la Biblioteca de Educación Superior. |
| `search_gacetas_inmunoprevenibles` | Gacetas epidemiológicas semanales de enfermedades prevenibles por vacunación (MSP). |

## Fuentes internacionales

| Tool | Descripción |
|------|-------------|
| `search_cepalstat_indicadores` | Busca un indicador en el catálogo regional de CEPALSTAT (CEPAL). |
| `get_cepalstat_indicador` | Observaciones de un indicador de CEPALSTAT, filtradas a un país (Ecuador por defecto). |

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
