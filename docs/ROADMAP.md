# Roadmap

Roadmap público de EcuDataMCP — servidor MCP de datos abiertos del gobierno
ecuatoriano (CKAN, BCE, SRI, INEC, Supercías, IESS/SENESCYT, SIPA, sector
eléctrico, y más). Para el porqué de cada fila — hallazgos, cifras
verificadas, dominios investigados, dead ends confirmados — ver
[RESEARCH.md](RESEARCH.md).

Leyenda de Estado (tablas de Pendiente): **No iniciado** · **Parcial — ...**

---

## Hecho

Fuentes de datos ya integradas (herramienta MCP construida y verificada en
vivo). Varias siguen ampliándose — ver la tabla de Pendiente para el detalle
de cobertura que falta en cada una.

### Banco Central del Ecuador (BCE)

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| BCEData (catálogo) | `search_indicadores_bce`, `get_indicador_bce`, `audit_bce_catalog` | 78 grupos / 2.360 series de la API pública sin auth; auditoría de cobertura en vivo (`guardar_snapshot`/`comparar_anterior`) → RESEARCH.md § Banco Central del Ecuador (BCE), § Duodécima pasada |
| Información Estadística Mensual (IEM/IEEM) | `search_bce_iem`, `get_bce_iem_table` | Archivo completo 1996-2026 (367 boletines, 3 eras de formato: XLSX individual, ZIP `.xls` legado, HTML de frameset), lectura semántica de tablas → RESEARCH.md § Decimotercera pasada |
| BCEData ↔ IEM | `compare_bce_sources` | Mapa de coincidencias candidatas por etiqueta/confianza, cola revisable → RESEARCH.md § Decimotercera pasada |
| Indicadores diarios/mensuales | `list_bce_indicadores_diarios`, `get_bce_indicador_diario` | 49 series en 13 archivos JSON: Riesgo País (D), Producción Petrolera (D), oro/WTI/Dow Jones/SOFR, bonos soberanos, reservas, deuda pública, balanza comercial... → RESEARCH.md § Décima pasada, § Decimotercera pasada |
| Sistema de páginas índice editoriales | `search_bce_indices`, `get_bce_indice_archivo` | ~35 páginas con archivo histórico completo por publicación con nombre propio (boletines sectoriales, precios/confianza, divisas, balanza de pagos) → RESEARCH.md § Duodécima pasada |
| Remesas de trabajadores | `search_bce_remesas` | Agregados, serie histórica y bases mensuales, desagregación por entidad desde jul-2025 → RESEARCH.md § Banco Central del Ecuador (BCE) |
| Precios de comercio exterior | `search_bce_precios_comex` | IPX/IPM/ITI desagregados por categoría de uso económico y producto individual → RESEARCH.md § Decimotercera pasada |
| Últimas publicaciones | `search_bce_publicaciones` | Ventana rodante (~30 más recientes) → RESEARCH.md § Duodécima pasada |

### SRI

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Página de datasets | `search_sri_datasets` | 130 enlaces directos (CSV/ZIP/XLSX) de un CMS Liferay sin API → RESEARCH.md § SRI — página de datasets |
| Estadísticas de recaudación | `search_sri_estadisticas_recaudacion` | Reportes XLSX mensuales por provincia/cantón/sector, complementario a `/datasets` → RESEARCH.md § Séptima pasada |

### ARCSA

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Base de Registros Emitidos | `list_arcsa_categorias`, `get_arcsa_categoria_archivos` | Registro sanitario vigente por categoría (alimentos, medicamentos, cosméticos, dispositivos médicos, plaguicidas, etc.), 27 categorías / 77 archivos; reutiliza el mismo parser de la Biblioteca de SGR (mismo plugin WordPress download-monitor) → RESEARCH.md § Decimoctava pasada |
| Datasets CKAN (registros suspendidos/cancelados) | tools CKAN genéricos | 4 datasets ya alcanzables sin código nuevo, complementarios al registro vigente de arriba → RESEARCH.md § Décima pasada |

### Superintendencia de Compañías (Supercías)

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Directorio de compañías | `search_companias`, `get_compania_info` | 226k+ compañías, actualizado a diario desde el export Excel estático del portal → RESEARCH.md § Superintendencia de Compañías (Supercías) |
| Ranking financiero | `search_ranking`, `get_financials` | ~38 ratios financieros por compañía/año fiscal, sobre SQLite local (`scripts/build_supercias_financials_db.py`) — ver Pendiente para portabilidad/actualización |
| Auditores externos | `search_auditores`, `get_auditor_info` | Registro de auditores externos |

### SIPA (Ministerio de Agricultura)

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Módulos económico/productivo/social/censos | `list_sipa_modulos`, `get_sipa_modulo_archivos` | 30 archivos Excel reales en 4 módulos → RESEARCH.md § Quinta pasada |
| Geoportal (GeoServer) | `search_sipa_geoportal_capas`, `get_sipa_geoportal_capa_datos` | 277 capas WMS, 257 con WFS real, en 24 endpoints por workspace → RESEARCH.md § Decimocuarta pasada |
| Resumen de Indicadores Sectoriales | `get_sipa_resumen_indicadores` | PDFs mensuales 2018-2026 (el único de 7 ítems del tablero que no es Tableau/flipbook) → RESEARCH.md § Decimocuarta pasada |

### Contraloría General del Estado

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Informes aprobados + Plan anual de control | `list_contraloria_informes`, `get_contraloria_informe` | CSV trimestrales de informes de auditoría a cualquier institución pública; mismo patrón `WFDescarga.aspx` para el plan anual → RESEARCH.md § Quinta y sexta pasada, § Séptima pasada |

### gob.ec

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Estadísticas de trámites | `get_tramite_estadisticas` | Serie mensual de atenciones/quejas por trámite desde 2021, sin auth, trámite por trámite (sin endpoint masivo) → RESEARCH.md § Séptima pasada |

### Sector eléctrico

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| CENACE — Información Operativa | `get_cenace_tablero` | 5 tableros server-rendered, snapshot "a este instante" (no serie histórica), TTL de caché 180s → RESEARCH.md § Décima pasada |

### CNT/ARCOTEL (telecomunicaciones)

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Reportes mensuales + Boletín Estadístico | `search_arcotel_reportes_mensuales`, `search_arcotel_boletines` | Serie mensual ene-2017→jun-2026 (~2 meses de rezago) y boletín anual/temático 2015-2024, solo PDF → RESEARCH.md § Octava pasada, § Decimocuarta pasada |

### IG-EPN (Instituto Geofísico)

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Catálogo sísmico | `search_sismos` | Feed CSV de sismos en casi tiempo real |
| Archivo de informes | `search_informes_igepn`, `get_informe_igepn` | App JSF/PrimeFaces separada, sesión+ViewState+POST; solo Tipo/Año filtran de verdad en servidor → RESEARCH.md § Undécima pasada |

### SGR (Secretaría de Gestión de Riesgos)

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| SITREP + Biblioteca | `search_sgr_sitreps`, `get_sgr_sitrep_archivos`, `list_sgr_biblioteca_categorias`, `get_sgr_biblioteca_categoria_archivos` | 54 eventos adversos 2016-2026 con PDFs; Biblioteca con 19 categorías, ~1660 documentos (mapas de amenaza, rutas de evacuación) → RESEARCH.md § Decimocuarta pasada |

### INEVAL

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Familias de exámenes nacionales | `list_ineval_familias`, `get_ineval_familia_archivos` | 9 familias (Ser Bachiller, Ser Estudiante, Ser Maestro, Ser Profesional, Llece), 557 enlaces, sin login/CAPTCHA → RESEARCH.md § INEVAL |

### Superbancos

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Secciones estadísticas + widgets OneDrive | `list_superbancos_secciones`, `get_superbancos_seccion_archivos` | Boletines Financieros Mensuales (224 archivos, 1997-2026), Servicios Financieros (312 archivos vía 3 widgets OneDrive descifrados), Información Histórica, Calendario Estadístico → RESEARCH.md § Séptima, Décima y Duodécima pasada |

### MEF/SENAE

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Fiscal (MEF) + recaudación aduanera (SENAE) | `search_mef_fiscal` (`fuente="mef"\|"senae"`) | 76 XLSX del MEF (metodología GFSM, 2025-01→2026-09) y 60 archivos de SENAE (recaudación aduanera por tipo de gravamen, 2012-2021) → RESEARCH.md § Recaudación arancelaria, § Decimocuarta pasada |

### MINEDEC

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Matrícula histórica | `search_minedec_matricula` | Registro 2009-2025, 5 archivos reales (WordPress, no CKAN) → RESEARCH.md § Decimocuarta pasada |

### SEPS (Economía Popular y Solidaria)

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Secciones SFPS/EPS | `list_seps_secciones`, `get_seps_seccion_archivos` | 26 secciones reales, incluida calificación de riesgo (112 entidades, 2020-2025) → RESEARCH.md § Decimotercera pasada |

### CNIG (Igualdad de Género)

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Violencia — femicidios | `search_cnig_femicidios` | 20 tablas PDF, incluida la matriz de femicidios/homicidios de mujeres → RESEARCH.md § Decimotercera pasada |

### INAMHI

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Geoservicios (WMS/WFS) | `search_inamhi_capas`, `get_inamhi_capa_datos` | 222 capas WMS, 199 con WFS real (precipitación, WRF, límites administrativos); sin capa de estaciones puntuales → RESEARCH.md § Decimotercera pasada |

### Aviación civil

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| IFIS — METAR/NOTAM/SIGMET | `get_metar`, `get_notam`, `get_sigmet` | Públicos sin sesión (solo `/fpl/*` exige login); SIGMET a nivel de FIR completo (SEFG) → RESEARCH.md § Decimotercera pasada |

### INEC / Ecuador en Cifras

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Páginas de tema + BIINEC exclusivos | `search_inec_estadisticas`, `get_inec_estadistica_files`, `search_biinec_extras` | ~91 temas (boletines + series históricas), incluyendo el Laboratorio de Dinámica Laboral y Empresarial (LDLE, añadido a `_EXTRA_TOPICS` por no estar linkeado en ningún menú); 3 registros BIINEC confirmados exclusivos (desechos peligrosos en salud, módulos ambientales ENEMDU/ECV) → RESEARCH.md § Ecuador en Cifras / portal BI del INEC |
| API REST de publicaciones (WordPress) | `search_inec_publicaciones`, `get_inec_publicacion_archivos` | Búsqueda de texto completo sobre 1.707 posts — cubre páginas que el menú mega-menu de una sola semilla no alcanza (ENEMDU anual, etc.) → RESEARCH.md § Novena pasada |
| Censo (censoecuador.gob.ec) | `search_censo_recursos` | 36 archivos reales, solo metadata + URL → RESEARCH.md § Novena pasada |

### CKAN municipales (Cuenca, Latacunga)

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Cuenca en Datos | Tools CKAN genéricos con `source="cuenca"` | 92 datasets, 13 categorías, mismo shape de API que el portal nacional → RESEARCH.md § Cuenca en Datos |
| Data Mashca (Latacunga) | Tools CKAN genéricos con `source="latacunga"` | 15 datasets (catastro predial, adopción/esterilización de mascotas, ordenanzas vigentes, rutas de recolección de desechos, sitios patrimoniales, puntos wifi) → RESEARCH.md § Decimosexta pasada |

### Ministerio del Trabajo

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| SUT — Power BI descifrado | `list_sut_indicadores`, `get_sut_indicador_schema`, `query_sut_indicador` | 8 dashboards (contratos mensual desde 2015, demanda laboral, sentencia/género, capacitación SETEC, PND, empleabilidad, denuncias, Encuentra Empleo) vía protocolo Power BI genérico → RESEARCH.md § Décima pasada |
| Boletín Estadístico Anual | `search_trabajo_boletin_anual` | 3 ediciones confirmadas (2020/2021/2022, lista fija); sin ediciones 2023-2025 encontradas → RESEARCH.md § Décima pasada, § Decimocuarta pasada |
| Salarios mínimos sectoriales | `search_salarios_sectoriales` | Una entrada por año 2020-2025, sin tabla 2026 (vigente 2025 por inacción) → RESEARCH.md § Octava pasada, § Decimocuarta pasada |

### MIES / Ministerio de Desarrollo Humano

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| infoMIES — bases mensuales + boletines zonales | `search_infomies_bases_mensuales`, `search_infomies_boletines_zonales` | Bases mensuales solo año en curso (años cerrados = 1 archivo/diciembre); Reporte Boletines Zonales consolidado 2021-2026 → RESEARCH.md § Décima pasada, § Decimocuarta pasada |

### IESS

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Boletines Estadísticos + Estudios Actuariales + Informes de Auditoría | `list_iess_colecciones`, `get_iess_archivos` | 3 archivos Liferay (`document_library_display`) resueltos a URL directa: 26 boletines anuales 1978-2024, 47 estudios actuariales en 4 años publicados (2010/2013/2018/2020), 325 informes de auditoría en 20 carpetas por año 2007-2026; detección de formato por el ícono de la página de detalle, no por la extensión de la URL (varios enlaces reales no tienen `.pdf`) → RESEARCH.md § IESS |

### Calidad, formatos y operación

Capacidades transversales, no atadas a una sola fuente de datos.

| Área | Qué cubre |
|---|---|
| Detección de patrón de serie | `detect_series_pattern` — clasifica acumulado/incremental/indeterminado, verificado contra IESS y MPCEIP → RESEARCH.md § `detect_series_pattern` — verificación end-to-end |
| Búsqueda por siglas/acrónimos | Expansión de siglas/acrónimos en `search_datasets` y afines |
| Formatos de archivo | `read_pdf` valida extensión/Content-Type antes de descargar; soporte para `.ods`, `.tar.gz`, `.xls` legado, `.xlsb`, `.zip` (truncado / sin miembro tabular / CSV malformado); `.rar` descartado explícitamente (ver Descartado). XLSX/XLSB/ODS (contenedores ZIP, fallan por completo si se truncan) usan un límite de descarga de 20 MB en vez del de 5 MB del resto → RESEARCH.md § Decimoséptima pasada |
| Verificación end-to-end de cifras | Cifras reales verificadas contra el portal para SRI, IESS, MPCEIP, `.xls`/`.zip`, degradación cuando el portal no responde → RESEARCH.md § Verificación end-to-end de cifras |
| Investigación "one-shot" | `investigate_dataset` — encadena `search_datasets` → `list_dataset_resources` → `preview_resource_data`, señala `detect_series_pattern` cuando aplica |
| Protección HTTP base | `/mcp` admite Bearer token opcional, bind local por defecto a loopback, límite global de concurrencia; `/health` libre para health checks |
| TLS | Renovación de certificado; CA intermedia Sectigo embebida en `helpers/tls.py` (reemplaza el fallback "OS trust store", que fallaba en runners Linux limpios) → RESEARCH.md § Infraestructura operativa |

---

## Pendiente

### Producto: portable y usable desde móvil

| Fuente | Estado | Qué falta |
|---|---|---|
| Separar cliente y despliegue | No iniciado | Imagen Docker multi-arquitectura (amd64/arm64) + configuración solo por variables de entorno; el cliente móvil solo debe consumir un endpoint MCP remoto por HTTPS |
| Endpoint remoto para agentes | Parcial — falta proxy HTTPS estable | Bearer/HTTPS directo/límites de concurrencia y por IP ya existen; falta publicar la instancia detrás de un proxy HTTPS con DNS, secretos y operación real (no depender de `localhost`) |
| Persistencia portable | No iniciado | Separar el proceso MCP del almacenamiento: volumen/objeto persistente, backups, restauración, ruta de actualización reproducible |
| Contrato de respuesta para agentes | Parcial — falta extender a otras fuentes | BCEData/IEM ya tienen bloque `metadatos` estable; falta migrar el resto de resultados de texto dual (`format=text\|json`) a schemas estructurados, y paginar/enlazar archivos grandes en vez de enviarlos completos |
| Operación 24/7 | Parcial — falta alertas de esquema | Smoke test diario (`scripts/smoke_e2e.py`, ~39/68 tools) corre en GitHub Actions, separado de CI; falta alertar sobre cambios de esquema específicos → RESEARCH.md § Infraestructura operativa |
| Rate limiting por usuario/IP y proxy HTTPS | Parcial — falta el proxy real | Cuotas por cliente/IP + límite global + Bearer opcional + TLS directo vía Uvicorn ya existen; falta proxy HTTPS/DNS/política operativa del endpoint remoto |

### BCE — cobertura completa de BCEData e IEM

| Fuente | Estado | Qué falta |
|---|---|---|
| BCEData — catálogo y series | Parcial | Descubrimiento y consulta completos; falta detectar cambios de revisión (el endpoint no expone marcador explícito, solo comparación por contenido) |
| IEM — archivo y archivos fuente | Parcial | 367 boletines legibles en 3 eras de formato; falta hashing masivo del histórico y confirmar que las 126 secciones más viejas siguen la misma forma (solo muestreado) |
| BCEData ↔ IEM — mapa de equivalencias | Parcial | 2 candidatos confirmados manualmente con datos en vivo; el resto no se trata como duplicado sin revisar valores y metodología |
| EMOE y coyuntura | Parcial | Expectativas económicas, confianza del consumidor, inflación y ciclo económico resueltos vía sistema de índices; falta mercado laboral y pobreza/desigualdad (sin página índice encontrada) |
| Catálogo de publicaciones y calendario | Parcial | `search_bce_publicaciones` solo expone ventana rodante (~30 recientes), sin fecha ni paginación; falta Cifras Económicas del Ecuador y el calendario de publicaciones futuras |
| Búsqueda ampliada del sitio BCE | No iniciado | Mapear publicaciones temáticas, catálogos y archivos históricos más allá de BCEData/IEM; priorizar solo lo que añada detalle verificable, no duplicados |
| Cuentas Nacionales completas | No iniciado | Paquetes anual/trimestral/regional, retropolación, Tabla Oferta-Utilización, Cuadro Económico Integrado, Matriz de Empleo e Ingresos — conservando metodología de base móvil y carácter provisional/definitivo |

### Supercías — pipeline financiero

| Fuente | Estado | Qué falta |
|---|---|---|
| Fuente masiva actualizable | No iniciado | Usar el Ranking de Compañías oficial (`bi_ranking.csv` + tablas auxiliares, actualización cada 24h) en vez del proceso manual actual |
| Refresh idempotente y automatización diaria | No iniciado | Comando que valide esquema/tamaño/filas/duplicados/nulos, construya índices y reemplace atómicamente solo tras pasar validación; ejecutarlo por cron/Actions, conservando la última base válida si falla |
| Conservar toda la historia disponible | No iniciado | Dejar de eliminar años anteriores al último bloque de cinco (la fuente documenta datos desde 2008); retención configurable (`all` o N años) |
| Consultas históricas sin respuestas gigantes | No iniciado | Filtros `desde`/`hasta`/`anio`, consultas resumidas por año/compañía/CIIU/métrica, paginación de rankings |
| Almacenamiento histórico por capas | No iniciado | SQLite indexado para búsquedas puntuales/rankings chicos, archivos fuente comprimidos por año como respaldo, Parquet/DuckDB solo para agregaciones grandes |
| Comparabilidad entre años | No iniciado | Conservar columnas desaparecidas como `null`, registrar cambios de esquema, documentar razones no comparables entre años |
| Distinguir diario de tiempo real | No iniciado | Etiquetar `search_ranking`/`get_financials` como `daily_bulk`; investigar aparte un `live_lookup` bajo demanda contra el Portal de Información oficial, con fallback explícito |

### Otras fuentes por explorar

| Fuente | Estado | Qué falta |
|---|---|---|
| Sector eléctrico — dominio profundo (CENACE/ARCONEL/CNEL) | No iniciado | CENACE (45 datasets), CNEL EP (40), ARCONEL/ARCERNNR (54 recursos BNEE) e IIGE (19) ya alcanzables vía CKAN genérico; `reportes.arconel.gob.ec` descifrado técnicamente (ASP.NET ReportViewer, replay de ViewState, sin login, 1998-2026) — falta construir el scraper stateful; CENACE Biblioteca (documentos de planificación) sin tocar; EEQ/Centrosur/EERSA/EEASA sin organización CKAN propia → RESEARCH.md § Octava pasada |
| Archivo histórico de cortes de luz (crisis sep-dic 2024) | No iniciado | EEQ sigue sirviendo los PDFs originales en vivo (solo falta enumerar slugs); CNEL probablemente perdió el archivo de su sitio, reintentar con Wayback Machine → RESEARCH.md § Octava pasada |
| DGAC/IFIS — movimientos/vuelos por aeropuerto | No iniciado | METAR/NOTAM/SIGMET ya cubiertos (ver Hecho); estadísticas de movimientos por aeropuerto puede ser una sección distinta del mismo sitio, sin explorar |
| Ministerio de Salud Pública | No iniciado | Dominio vivo con contenido real y sección LOTAIP; sin pasada de contenido completa más allá de confirmar que el sitio responde → RESEARCH.md § Séptima pasada |
| Registro Oficial (gaceta oficial) | No iniciado | Candidato de alta prioridad para búsqueda por fecha (leyes/decretos/resoluciones/circulares, gratis, sin paywall, archivo desde 2001); posible fuera de alcance, ver nota de alcance → RESEARCH.md § Datos legislativos |
| Superbancos — Balances/Patrimonio Técnico/indicadores | No iniciado | Morosidad/liquidez/solvencia viven detrás de una herramienta de consulta propia, no de un widget OneDrive; necesita pasada con browser real → RESEARCH.md § Séptima pasada |
| Permisos y portales municipales | No iniciado | ~221 GADs sin investigar; empezar por Quito y Guayaquil si se persigue → RESEARCH.md § Permisos municipales |
| IGM Geoportal | No iniciado | Cartografía gated tras registro/login, no automatizable tal cual → RESEARCH.md § Sitios de ministerios individuales |
| Fuentes externas de sociedad civil (FCD, FARO) | Decisión de alcance pendiente | Datasets tabulares reales confirmados (votaciones de la Asamblea, declaraciones patrimoniales, ordenanzas municipales Quito/Guayaquil); `cuentasclaras.org` tiene spam inyectado — no tocar sin verificar que está limpio → RESEARCH.md § Fuentes externas de sociedad civil |
| Gremios privados (AEADE, ASOBANCA, FEDEXPOR) | Parcial | AEADE y FEDEXPOR confirmados y descargables; ASOBANCA Datalab sin resolver extracción (SPA) → RESEARCH.md § Gremios/asociaciones privadas |
| CORDES | No iniciado | Base de variables macroeconómicas; sitio con protección anti-bot, confirmar primero qué parte es automatizable → RESEARCH.md § Fuentes externas de sociedad civil |
| Nowcast / Encuesta de Expertos | No iniciado | Previsiones de PIB/empleo/desempleo/inflación; separar estimación de dato observado, conservar metodología y revisiones |
| Calidad del aire de Quito | No iniciado | `aireambiente.quito.gob.ec` responde pero sin contenido en HTML crudo (SPA); necesita browser real o su API subyacente |
| Cancillería y embajadas | No iniciado | Dominio vivo (`cancilleria.gob.ec`), sin pasada de contenido dedicada — trámites consulares, apostillas, estadísticas migratorias sin confirmar |
| CNE (Consejo Nacional Electoral) | Potencial, revisar de nuevo | Marcado descartado en una pasada anterior por WAF Incapsula en el micrositio de resultados; pedido explícito de Daniel 2026-09-04 de reevaluar — confirmar si el bloqueo aplica a todo `cne.gob.ec` o solo a ese micrositio, y si hay datasets/API alcanzables (padrón, resultados históricos, financiamiento de campañas) fuera de la zona bloqueada |
| Geoportales municipales (Quito, Riobamba, Portoviejo/Fénix, Ambato) | No iniciado | Encontrados vía directorio de "Municipios Abiertos" (`municipiosabiertos.gob.ec`); patrón WMS/WFS como INAMHI/SIPA, no CKAN. URL exacta del GeoServer/ArcGIS sin confirmar para ninguno; Quito además tenía "la primera plataforma de datos abiertos del país" (2014) sin catálogo vivo encontrado en esta pasada → RESEARCH.md § Decimosexta pasada |
| Vivienda MIDUVI | No iniciado | Dominio caído a nivel TLS, sin reemplazo encontrado; CKAN cubre parcialmente (5 datasets) → RESEARCH.md § Vivienda (MIDUVI) |
| Prensa | No iniciado | SECOM/Presidencia (boletines) y Fundamedios (agresiones a prensa); sin confirmar si hay datasets descargables → RESEARCH.md § Prensa |
| Datos legislativos/normativos | Investigado, alcance en duda | Jurisprudencia y proyectos de ley investigados a fondo; Daniel señaló que puede no ser relevante para el alcance del proyecto → RESEARCH.md § Datos legislativos |
| Fuentes internacionales con foco Ecuador | No iniciado | CEPAL/CEPALSTAT, FMI (IFS/WEO/Article IV), ONU y agencias regionales; integrar solo lo que aporte frecuencia/corte que la fuente ecuatoriana no publique → RESEARCH.md § Fuentes externas de sociedad civil |

### Otros ítems parciales

| Fuente | Estado | Qué falta |
|---|---|---|
| SENESCYT/Educación Superior | Parcial | Cubierto vía CKAN + biblioteca de Educación Superior; registro de títulos bloqueado por captcha (no automatizable) → RESEARCH.md § SENESCYT |
| INEC — preview de archivos grandes | Parcial | `list_zip_contents` lista miembros de ZIP vía HTTP Range sin descargar todo; decidido en contra de un índice pre-construido por dataset y de cualquier transferencia completa de archivo |
| CEPAL — geoportal del Censo Ecuador | Parcial | 9 capas reales vía API, pero derivadas del Clasificador Geográfico de INEC (fuente primaria); bajo valor salvo interés específico en la geometría → RESEARCH.md § CEPAL |

### Calidad y arquitectura

| Fuente | Estado | Qué falta |
|---|---|---|
| Búsqueda semántica | No iniciado | `search_datasets` sigue siendo keyword puro de CKAN, sin comprensión semántica sobre el catálogo completo |
| Simplificar y armonizar la arquitectura MCP | No iniciado | Reducir duplicaciones en la superficie pública, separar tools de mantenimiento, migrar a schemas/resultados/errores estructurados — diagnóstico y diseño en [MCP_ARCHITECTURE.md](MCP_ARCHITECTURE.md) |
| `outputSchema` en los tools MCP | No iniciado | — |
| Manejo geoespacial | No iniciado | WKT/GeoJSON más allá del stripping actual |
| Type-checking en CI | No iniciado | ruff cubre estilo/imports pero no errores de tipo; riesgo de destapar errores preexistentes en 40+ archivos — evaluar alcance antes de activar el gate |

---

## Descartado

Bloqueos reales confirmados en vivo, o decisiones explícitas de no construir — no falta de esfuerzo.

| Fuente | Por qué |
|---|---|
| `sisdatbi.arconel.gob.ec` | Bloqueo geográfico confirmado con VPN; app PHP con login obligatorio, sin contenido de invitado → RESEARCH.md § Decimoquinta pasada |
| CELEC EP (transparencia/rendición de cuentas) | Contenido real solo LOTAIP genérico por unidad de negocio, no dato sectorial → RESEARCH.md § Decimoquinta pasada |
| `.rar` | Riesgo de subprocess/CVE — decidido explícitamente en contra |
| SIPA/MAG — precios mayoristas como fuente de alta frecuencia | Solo boletines PDF mensuales y un documento regulatorio de piso/techo sin historia; app móvil "cgsin.precios" sin explorar → RESEARCH.md § Duodécima pasada |
| BCE — prueba de completitud y frescura programada | Requiere scheduler con almacenamiento persistente de snapshots; Daniel decidió no construir esa infraestructura (la comparación bajo demanda ya existe vía `audit_bce_catalog`) |
| Micrositio de Interior (`cifras.ministeriodelinterior.gob.ec`) | WAF Incapsula |
| Aduana/SENAE — comercio exterior | No publicado en portal abierto, solo por oficio (FEDEXPOR cubre el hueco, ver gremios privados) |
| Fiscalía General del Estado | Sin dataset agregado propio; sus herramientas de consulta son caso-por-caso |
| Supercías — Valores y Seguros | Login-gated casi por completo; un solo PDF estático encontrado |
| SERCOP — catálogo/órdenes de compra | CAPTCHA |
| IG-EPN — `descarga-de-datos` | Cuenta obligatoria |
| Superbancos — Catastro de Compañías | Login obligatorio (app JSF aparte) |
| SRI Saiku (OLAP) | Tools removidas 2026-09-05 — `srienlinea.sri.gob.ec` confirmado inalcanzable en vivo desde tres entornos distintos (servidor MCP desplegado, `curl` local, navegador real): la conexión TLS se cierra abruptamente sin excepción, no es el gap de conectividad puntual que se sospechaba antes → RESEARCH.md § Décima pasada |

---

## Arquitectura

Cada fuente sigue el mismo patrón de 3 piezas, documentado en
[CLAUDE.md](../CLAUDE.md):

```
helpers/<source>_client.py   # cliente HTTP + parseo
tools/<name>.py               # tool(s) MCP, registrados en tools/__init__.py
tests/test_<name>_client.py   # mocks con pytest-httpx
```

Cacheo TTL por fuente vía `helpers/cache.py`; nunca confiar en el `format`
declarado por CKAN antes que la extensión de la URL (ver CLAUDE.md,
"Conventions"). El diagnóstico y diseño propuesto para simplificar la
superficie pública de tools vive en
[MCP_ARCHITECTURE.md](MCP_ARCHITECTURE.md).

## Agregar una fuente nueva

Seguir el patrón de arquitectura de arriba: un `helpers/<source>_client.py`
nuevo más su `tools/*.py`, registrados en `tools/__init__.py`. Antes de
construir, investigar en vivo (no solo leer el HTML) y dejar el hallazgo —
cifras verificadas, bugs encontrados, dead ends — documentado en
[RESEARCH.md](RESEARCH.md); la fila correspondiente en este roadmap se
agrega o mueve de Pendiente a Hecho una vez que el tool está construido y
verificado.
