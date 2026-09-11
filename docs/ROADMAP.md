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
| Información Estadística Mensual (IEM/IEEM) | `search_bce_iem`, `get_bce_iem_table` | Archivo completo 1996-2026 (367 boletines, 3 eras de formato: XLSX individual, ZIP `.xls` legado, HTML de frameset), lectura semántica de tablas; los 127 boletines de la era frameset verificados en vivo (122/127 con la misma forma) → RESEARCH.md § Decimotercera pasada, § Vigésimo segunda pasada |
| BCEData ↔ IEM | `compare_bce_sources` | Mapa de coincidencias candidatas por etiqueta/confianza; 2 de 77 confirmadas manualmente, el resto queda como candidato sin revisar (ver Descartado) → RESEARCH.md § Decimotercera pasada |
| Indicadores diarios/mensuales | `list_bce_indicadores_diarios`, `get_bce_indicador_diario` | 49 series en 13 archivos JSON: Riesgo País (D), Producción Petrolera (D), oro/WTI/Dow Jones/SOFR, bonos soberanos, reservas, deuda pública, balanza comercial... → RESEARCH.md § Décima pasada, § Decimotercera pasada |
| Sistema de páginas índice editoriales | `search_bce_indices`, `get_bce_indice_archivo` | 34 páginas con archivo histórico completo por publicación con nombre propio (boletines sectoriales, precios/confianza, divisas, balanza de pagos, mercado interbancario, entorno macroeconómico, Cifras Económicas del Ecuador, tasas máximas y referenciales) → RESEARCH.md § Duodécima pasada, § Vigésimo segunda pasada |
| Cuentas Nacionales completas | `search_bce_cuentas_nacionales`, `get_bce_cuentas_nacionales_archivo` | 18 páginas / 244 archivos: anuales, trimestrales, regionales, retropolación desde 1965, TOU, CEI, MEI, matrices insumo-producto y de contabilidad social (base fija y móvil), cuenta temática de bioeconomía, IMAEC (solo mes vigente) → RESEARCH.md § Vigésimo segunda pasada |
| Remesas de trabajadores | `search_bce_remesas` | Agregados, serie histórica y bases mensuales, desagregación por entidad desde jul-2025 → RESEARCH.md § Banco Central del Ecuador (BCE) |
| Precios de comercio exterior | `search_bce_precios_comex` | IPX/IPM/ITI desagregados por categoría de uso económico y producto individual → RESEARCH.md § Decimotercera pasada |
| Últimas publicaciones | `search_bce_publicaciones` | Ventana rodante (~30 más recientes) → RESEARCH.md § Duodécima pasada |
| Calendario de publicaciones | `search_bce_calendario` | Calendario anual completo (523 entradas, 2026-01-05 a 2026-12-31, 162 fechas futuras al momento de construirlo): fecha, tipo, nombre, periodicidad, categoría, período de referencia y enlace por cada publicación programada del año → RESEARCH.md § Vigésimo segunda pasada |

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
| CENACE, CNEL EP, ARCONEL/ARCERNNR, IIGE (datasets CKAN) | Tools CKAN genéricos (`source="nacional"`, orgs `cenace`, `cnel-ep`, `agencia-de-regulacion-y-control-de-energia-y-recursos-naturales-no-renovables`, `instituto-de-investigacion-geologico-y-energetico-iige`) | 45 + 40 + 54 recursos (BNEE) + 19 datasets ya alcanzables sin código nuevo — producción del parque generador, potencia efectiva, facturación/venta de energía, Balance Nacional de Energía Eléctrica, investigación geológica/energética → RESEARCH.md § Sector eléctrico (segunda pasada) |

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

### SENESCYT / Educación Superior

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| SIAU — Estadísticas de Educación Superior, CTI | `search_senescyt_estadisticas` | 12 archivos reales (fichas metodológicas, reportes de indicadores 2021/2022/2024, índice de competitividad, inventario CTI/saberes ancestrales, demanda laboral, impacto COVID-19), acordeón WPBakery mezclando paquetes WordPress Download Manager y links directos/Nextcloud → RESEARCH.md § SENESCYT / Educación Superior / MINEDEC |
| Biblioteca de Educación Superior | `list_senescyt_biblioteca_categorias`, `get_senescyt_biblioteca_categoria_archivos` | 1.259 documentos reales en 17 categorías de primer nivel (PAC por año, Normativa, LOES, SNNA, Acuerdos —694 por sí sola—, Indicadores ACTI, exámenes especiales), mismo patrón download-monitor que SGR/ARCSA; nesting hasta 3 niveles de profundidad (más que SGR/ARCSA) → RESEARCH.md § SENESCYT / Educación Superior / MINEDEC |

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
| IFIS3 — AIP Ecuador (eAIP) | `list_aip_aerodromos`, `get_aip_aerodromo` | Ficha AD 2.x completa por aeródromo (~22 aeródromos/helipuertos): coordenadas ARP, elevación, variación magnética, horas de operación, contactos, tipos de tránsito, y el resto de subsecciones OACI Anexo 15; sin login/JS/WAF → RESEARCH.md § Vigésimo primera pasada |

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

### Fuentes internacionales con foco Ecuador

No son fuentes exclusivas de Ecuador — Ecuador es una entrada consultable
dentro de un catálogo regional/global, no un dataset propio.

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| IADB Latin Macro Watch + World Bank/IADB DPI | Tools CKAN genéricos con `source="iadb"` | 692+ datasets en `data.iadb.org` (portal CKAN estándar); Latin Macro Watch: 665 recursos CSV (desempleo, IPC, tipo de cambio, fiscal) para 26 países incluido Ecuador; DPI: ~180 países, 1975-2023. Títulos/notas multilingües (`{"es":..., "en":...}`) normalizados a un solo idioma en `helpers/ckan_client.py` para que el renderizado de texto existente siga funcionando → RESEARCH.md § Vigésimo quinta pasada |
| CEPALSTAT (CEPAL/ECLAC) | `search_cepalstat_indicadores`, `get_cepalstat_indicador` | 2.059 indicadores regionales (Demográficos y sociales, Económicos, Ambientales, Temas transversales/ODS); filtrado a un país por defecto (Ecuador) para acotar el payload (~2.5 MB sin filtro → ~85 KB filtrado a un país); decodifica las dimensiones crudas (`dim_N`) a etiquetas legibles → RESEARCH.md § Vigésimo quinta pasada |

### CKAN nacional — organizaciones ya alcanzables sin código nuevo

Confirmadas en vivo, reachable con los tools CKAN genéricos existentes
(`search_datasets`, `search_organizations`, etc.) — documentadas aquí como
fuente conocida, sin cliente dedicado. `get_organization_info` ganó un
parámetro `query` (2026-09-10) para filtrar los paquetes de una
organización grande por texto, y ya no trunca a 25 en `format=json` —
necesario para que SRI genérico (127)/MEF genérico (97)/IEPS (106) sean
realmente navegables sin adivinar el slug exacto cada vez.

| Fuente | Qué cubre |
|---|---|
| Homicidios Intencionales (Ministerio del Interior) | `ministerio-del-interior`: 6 paquetes confirmados en vivo (Homicidios Intencionales —4 XLSX: mensual 2026, histórico 2014-2025, microdatos 2014-2024 de 93 MB—, Trata de Personas, Personas Desaparecidas, Armas Ilícitas, Personas Detenidas, Sustancias Catalogadas), actualizado 2026-08-19. Complementario, no duplicado, de `search_cnig_femicidios`: CNIG publica un PDF-snapshot (abril 2023) del subconjunto "Femicidios y Homicidios Intencionales **de Mujeres**" citando datos de Interior entre sus fuentes — este dataset es el total nacional por todas las víctimas, en XLSX nativo y actualizado, no un derivado parcial en PDF → RESEARCH.md § Vigésimo tercera pasada |
| Autoridades portuarias (APPB, APG, APM) | Tres organizaciones CKAN reales confirmadas en vivo, no solo Puerto Bolívar: `autoridad-portuaria-de-puerto-bolivar-appb` (246 paquetes — el conteo más alto de cualquier organización del portal: tráfico de buques, carga import/export por producto con tonelaje y país de origen/destino, obras de inversión, mensual desde nov-2021, actualizado hasta agosto 2026), `autoridad-portuaria-de-guayaquil-apg` (6 paquetes: distributivo de personal, remuneración mensual, buques por muelle, tonelaje y contenedores de importación/exportación — **última actualización oct-2025**, posiblemente sin mantenimiento activo), `apm` = Autoridad Portuaria de **Manta**, no APM Terminals (11 paquetes: buques arribados, TEUs, carga, vehículos, turistas, actualizado jul-2026). **APPB confirmado desordenado, decisión explícita de no construir cliente dedicado (2026-09-10):** los 246 paquetes son solo ~6 tipos de reporte reales con ~50 variantes de título (capitalización, acentos, orden de palabras inconsistentes — ej. "Reporte Movimiento Carga Exportación" vs "Reporte de Movimiento de Carga de Exportación"); la búsqueda de texto completo sigue funcionando porque CKAN indexa contenido, no el título exacto. APM tiene un error real de `format` declarado ("cvs" en vez de "CSV" en un recurso real) — mismo patrón de "no confiar en el formato declarado de CKAN" ya documentado en CLAUDE.md → RESEARCH.md § Vigésimo tercera pasada, § Vigésimo sexta pasada |
| Cancillería (Ministerio de Relaciones Exteriores y Movilidad Humana) | `ministerio-de-relaciones-exteriores-y-movilidad-humana`: 13 paquetes confirmados en vivo, más ricos de lo documentado antes — Registro Movilidad Humana desagregado en 9 paquetes (Visas, Apostillas y Legalizaciones, Órdenes de Cedulación, Actos Notariales, Pasaportes de Emergencia, Certificado de Migrante Retornado, Naturalizaciones, Solicitantes de Refugio, Histórico Refugiados Anuales), más Autorización de salida de menores, Presupuesto de Misiones Diplomáticas, Ayuda y financiamiento internacional. Complementario, no duplicado, de `search_tramites`/`get_tramite_estadisticas` (institución "16"): esas tools dan tiempos de atención/quejas por trámite individual (métricas de servicio), estos paquetes CKAN son los registros administrativos reales → RESEARCH.md § Vigésimo cuarta pasada, § Vigésimo sexta pasada |
| SRI genérico | `sri-servicio-de-rentas-internas`: 127 paquetes confirmados en vivo, separado de `search_sri_datasets`/`search_sri_estadisticas_recaudacion` (que scrapean la página `/datasets` y los reportes de recaudación por provincia/cantón). Este catálogo CKAN cubre RUC desagregado por las 23 provincias, Catastro de Contribuyentes (inscripciones/suspensiones/activos por año 2017-2026), comprobantes electrónicos (emisores/comprobantes CEL), estadísticas de vehículos, índice de actividad empresarial no petrolera, ventas_compras, presión fiscal, catastro de agregadores de pago/empresas fantasmas/servicios digitales/mercados en línea. Actualizado hasta agosto 2026. **Posible solape parcial, no confirmado:** sus paquetes anuales "Recaudación de Impuestos - YYYY" podrían ser una versión más agregada (anual) de lo que `search_sri_estadisticas_recaudacion` ya da mensual por provincia/cantón/sector — el resto del catálogo es claramente no duplicado → RESEARCH.md § Vigésimo sexta pasada |
| MEF genérico | `ministerio-de-economia-y-finanzas`: 97 paquetes confirmados en vivo, separado de `search_mef_fiscal` (metodología GFSM). Este catálogo CKAN cubre ejecución mensual del Presupuesto General del Estado por ingreso/gasto (2021-2025), ejecución de nóminas y distributivo de remuneraciones mensual (nómina de personal del sector público), y un Boletín de Deuda Pública (22 recursos). No duplicado — ángulo de nómina/ejecución presupuestaria, no macro fiscal GFSM. **Aparenta estar desactualizado:** la mayoría de series mensuales se detienen a mediados de 2025, y el Boletín de Deuda Pública no se actualiza desde agosto 2021 → RESEARCH.md § Vigésimo sexta pasada |
| IEPS (Instituto Nacional de Economía Popular y Solidaria) | `ieps`: 106 paquetes confirmados en vivo, actualizado hasta septiembre 2026. Institución distinta de SEPS (ya cubierta): SEPS es el regulador/calificador de riesgo, IEPS es el instituto de fomento — proyectos de inversión para actores EPS, ferias inclusivas, fortalecimiento de capacidades organizativas, espacios de comercialización, registro de organizaciones EPS por sector productivo. No duplicado. Mismo patrón de deriva en los títulos año a año que APPB/COSEDE; varios paquetes de 2024 traen solo 1 recurso frente a 9-13 en 2025/2026 → RESEARCH.md § Vigésimo sexta pasada |
| COSEDE (Corporación del Seguro de Depósitos) | `cosede`: 88 paquetes confirmados en vivo, mensual desde nov-2021, actualizado el mismo día de esta verificación (2026-09-10). Dos series paralelas ("Entidades Contribuyentes", "Pago del Seguro de Depósitos") más diccionarios/metadatos de datos. Seguro de depósitos — distinto de Superbancos (solvencia bancaria) y SEPS (calificación de riesgo EPS), no duplicado → RESEARCH.md § Vigésimo sexta pasada |
| IPAIP (Instituto Público de Investigación de Acuicultura y Pesca) | `ipaip`: 70 paquetes confirmados en vivo, trimestral, actualizado hasta julio 2026. Registro de publicaciones científicas por especie/tema (Pesca Demersal, Recursos Pelágicos, Acuacultura, Camarón, Merluza, Oceanografía y Cambio Climático) — un índice de publicaciones de investigación, no estadísticas de captura crudas. Territorio nuevo: ninguna otra fuente del proyecto cubre pesca/acuicultura → RESEARCH.md § Vigésimo sexta pasada |
| MAG genérico (parcial — mitad reachable, mitad confirmado duplicado) | `mag`: 69 paquetes confirmados en vivo. **Series de precios de agroindustrias** (aceite, cacao, café, granos, azúcar — 16-22 recursos por paquete, historia real desde 2012) — no duplicadas: distinto del "precios mayoristas" ya descartado (ver Descartado), que evaluaba precio minorista/mayorista en 3 mercados, no precio pagado por plantas procesadoras a productores. Reachable sin código nuevo. **Los 54 paquetes de mapas geoespaciales SÍ están confirmados duplicados** del geoportal SIPA ya construido (`search_sipa_geoportal_capas`): coincidencias de título exactas confirmadas ("Mapa de Susceptibilidad a Inundaciones Ecuador Continental, escala 1:25.000, 2024" es idéntico palabra por palabra en ambos catálogos; toda la familia "Zonificación agroecológica del [cultivo]" existe en ambos, cultivo por cultivo) — no construir ningún cliente para estos, usar `search_sipa_geoportal_capas`/`get_sipa_geoportal_capa_datos` en su lugar → RESEARCH.md § Vigésimo tercera pasada, § Vigésimo sexta pasada |

### Ministerio de Salud Pública

| Fuente | Herramientas | Qué cubre |
|---|---|---|
| Gacetas de Inmunoprevenibles | `search_gacetas_inmunoprevenibles` | Boletines semanales de vigilancia epidemiológica de enfermedades prevenibles por vacunación (Semana Epidemiológica), 2019-presente, 362 PDFs confirmados en vivo en 9 páginas. Descubrimiento de páginas dinámico vía la API REST de WordPress (`/wp-json/wp/v2/posts`), no una lista de años hardcodeada — se adapta solo a años futuros. Desde 2024 algunas semanas incluyen un reporte complementario por enfermedad específica (tosferina). Una de varias series de gacetas paralelas del MSP (vectoriales, enfermedades de la piel/reemergentes, indicadores) — solo esta está construida → RESEARCH.md § Ministerio de Salud Pública, § Vigésimo sexta pasada |

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
| EMOE y coyuntura | Parcial | Expectativas económicas, confianza del consumidor, inflación y ciclo económico resueltos vía sistema de índices; mercado laboral (BCEData id_grupo 64/65/68/102) y pobreza/desigualdad (`search_inec_publicaciones`) confirmados ya cubiertos por tools existentes, sin código nuevo → RESEARCH.md § Vigésimo segunda pasada |
| Catálogo de publicaciones | Parcial | `search_bce_publicaciones` solo expone ventana rodante (~30 recientes), sin fecha ni paginación; Cifras Económicas del Ecuador ya cubierta vía `search_bce_indices` (243 archivos, 2005-2025) y el calendario de publicaciones futuras vía `search_bce_calendario` (523 entradas) → RESEARCH.md § Vigésimo segunda pasada |
| Búsqueda ampliada del sitio BCE | No iniciado | Mapear publicaciones temáticas, catálogos y archivos históricos más allá de BCEData/IEM; priorizar solo lo que añada detalle verificable, no duplicados |

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
| IFIS3 — AIP Ecuador (GEN/ENR + AMDT/SUP/AIC) | Parcial | Ficha AD 2.x por aeródromo ya cubierta (ver Hecho); falta GEN (regulaciones/servicios nacionales) y ENR (espacio aéreo, rutas ATS, radioayudas) del mismo eAIP, y las pestañas AMDT/SUP/AIC (enmiendas/suplementos/circulares, probablemente PDFs por edición) sin explorar → RESEARCH.md § Vigésimo primera pasada |
| Sector eléctrico — dominio profundo (CENACE/ARCONEL/CNEL) | No iniciado, protocolo mapeado a fondo | Datasets CKAN de CENACE/CNEL EP/ARCONEL/IIGE ya cubiertos (ver Hecho); falta `reportes.arconel.gob.ec` (ASP.NET ReportViewer, sin login, 1998-2026), mapeado byte a byte en la Vigésima pasada (2026-09-06) — secuencia exacta de postbacks, formato delta de MS AJAX, y algoritmo para ubicar la grilla real bajo envoltorios anidados, todo sin `BeautifulSoup`/`lxml`; **falta confirmar el criterio de fin de paginación (SSRS reporta "de N ?" páginas) antes de escribir el cliente** — decisión explícita de Daniel de documentar primero, construir después; CENACE Biblioteca (documentos de planificación) sin tocar; EEQ/Centrosur/EERSA/EEASA sin organización CKAN propia → RESEARCH.md § Vigésima pasada |
| Archivo histórico de cortes de luz (crisis sep-dic 2024) | No iniciado | EEQ sigue sirviendo los PDFs originales en vivo (solo falta enumerar slugs); CNEL probablemente perdió el archivo de su sitio, reintentar con Wayback Machine → RESEARCH.md § Octava pasada |
| Ministerio de Salud Pública — familia de gacetas semanales | Parcial, resto mapeado y listo para construir | Gacetas de Inmunoprevenibles ya cubiertas (ver Hecho). Confirmado en vivo (2026-09-10) que el MSP corre **toda una familia** de series semanales bajo el mismo patrón WordPress (tabla Gutenberg plana, descubrimiento vía `/wp-json/wp/v2/posts`): Vectoriales (dengue/malaria/chikungunya, 2017-2026 — la más larga), Enfermedades de la Piel o Reemergentes (2025-2026), Gaceta Indicadores (2012, 2024-2026), Gaceta General (2019-2025), ETAS (enfermedades transmitidas por alimentos/agua, 2024-2026), IRAG (infecciones respiratorias agudas graves, 2024-2026), Brotes (2021, 2023). Decisión explícita de Daniel (2026-09-10): no construir todavía — si se retoma, generalizar `helpers/msp_gacetas_inmunoprevenibles_client.py` en un cliente parametrizado por serie en vez de duplicar el módulo 6 veces, no construir cada serie por separado. Sin explorar además: plataforma de datos COVID-19, GeoSalud en Cifras, solo 8 paquetes en la organización CKAN del MSP → RESEARCH.md § Séptima pasada, § Vigésimo tercera pasada, § Vigésimo sexta pasada |
| Consejo de la Judicatura — Portal de Estadística Judicial | No iniciado | Solo 1 paquete en CKAN; dashboard propio en `fsweb.funcionjudicial.gob.ec/estadisticas/` con causas, audiencias, productividad de jueces, violencia/femicidio, mediación, remates judiciales — sin login, actualización mensual, mecanismo de exportación real (¿Power BI?) sin confirmar, necesita pasada con browser real → RESEARCH.md § Vigésimo tercera pasada |
| Ministerio de Turismo — Turismo en Cifras | No iniciado | Solo 5 paquetes en CKAN (catastro turístico); portal propio `servicios.turismo.gob.ec/turismo-en-cifras/` con entradas/salidas de turistas por nacionalidad, oferta turística, boletines estadísticos, actualización mensual → RESEARCH.md § Vigésimo tercera pasada |
| Registro Oficial (gaceta oficial) | No iniciado | Candidato de alta prioridad para búsqueda por fecha (leyes/decretos/resoluciones/circulares, gratis, sin paywall, archivo desde 2001); estructura del sitio confirmada (`registroficial.gob.ec`: ediciones ordinarias, suplementos, ediciones especiales, edición constitucional, edición jurídica, índice mensual, buscador visible) pero mecanismo exacto de descarga por fecha sin confirmar — necesita pasada con browser real; posible fuera de alcance, ver nota de alcance → RESEARCH.md § Datos legislativos, § Vigésimo cuarta pasada |
| Superbancos — Balances/Patrimonio Técnico/indicadores | No iniciado, área ya ubicada | Morosidad/liquidez/solvencia viven detrás de una herramienta de consulta propia; ubicada la URL real (`superbancos.gob.ec/estadisticas/portalestudios/`, sección "Indicadores de Solidez Financiera", series desde enero 2003) — falta confirmar si es lista de archivos estáticos o herramienta de consulta con parámetros, necesita pasada con browser real → RESEARCH.md § Séptima pasada, § Vigésimo cuarta pasada |
| Permisos y portales municipales | No iniciado | ~221 GADs sin investigar; `municipiosabiertos.gob.ec` confirma que Cuenca, Quito y Riobamba son los más avanzados (Cuenca ya cubierto) — empezar por Quito y Guayaquil si se persigue → RESEARCH.md § Permisos municipales, § Vigésimo cuarta pasada |
| IGM Geoportal | Reevaluado — acceso libre confirmado a escala país | La nota "gated tras registro/login" estaba desactualizada o era parcial: la Cartografía Base Continua 1:1.000.000 (2024) es de acceso libre y gratuito sin registro, en GPKG/SHP, más geoservicios WMS/WFS/WMTS (mismo patrón que INAMHI/SIPA). Falta confirmar el endpoint WMS/WFS real (GetCapabilities) y si la cartografía de mayor resolución (catastral) sigue gated → RESEARCH.md § Vigésimo cuarta pasada |
| Fuentes externas de sociedad civil (FCD, FARO) | Decisión de alcance pendiente | Datasets tabulares reales confirmados (votaciones de la Asamblea, declaraciones patrimoniales, ordenanzas municipales Quito/Guayaquil); FCD opera además `observatoriolegislativo.ec` (Asamblea) y `ojoalconcejo.org` (concejos municipales) como portales propios, no solo informes; `cuentasclaras.org` tiene spam inyectado — no tocar sin verificar que está limpio. Nuevo: el portal de declaraciones patrimoniales de Contraloría exige desde abril 2026 cédula/datos personales obligatorios para buscar — más restringido que antes → RESEARCH.md § Fuentes externas de sociedad civil, § Vigésimo cuarta pasada |
| Gremios privados (AEADE, ASOBANCA, FEDEXPOR) | Parcial | AEADE y FEDEXPOR confirmados y descargables; ASOBANCA Datalab ("Clicstat") confirmado como app **Qlik** embebida (`QlikTicket=` en la URL, no una SPA genérica) — extraerla exige la API del motor Qlik (WebSocket) o un endpoint de exportación, ninguno confirmado todavía → RESEARCH.md § Gremios/asociaciones privadas, § Vigésimo cuarta pasada |
| CORDES | No iniciado, bajo valor confirmado | Think tank privado (fundado 1984) que publica libros/PDFs; sin evidencia de una base de datos pública o API tras verificación en vivo — protección anti-bot no confirmada pero tampoco relevante si no hay dato estructurado que extraer → RESEARCH.md § Fuentes externas de sociedad civil, § Vigésimo cuarta pasada |
| Nowcast / Encuesta de Expertos | No iniciado, valor cuestionado | Confirmado que el BCE solo publica PIB trimestral con ~3 meses de rezago, sin producto de "nowcast" oficial y en vivo; el EMOE (`indice-de-expectativas-de-la-economia-indice`, ya cubierto vía `search_bce_indices`) es lo más cercano a una encuesta de expectativas real → RESEARCH.md § Vigésimo cuarta pasada |
| Calidad del aire de Quito | No iniciado, archivo histórico real encontrado y bloqueado por `.rar` | `datosambiente.quito.gob.ec` es un archivo histórico real de descarga directa (CO, NO2, O3, PM2.5, PM10, SO2, meteorología, 2004-2025) — pero en formato `.rar`, ya descartado explícitamente por este proyecto (ver Descartado). El dashboard en tiempo real (`aireambiente.quito.gob.ec`) sigue sin confirmar si necesita browser real → RESEARCH.md § Vigésimo cuarta pasada |
| CNE (Consejo Nacional Electoral) | Reevaluado, bloqueado — requiere decisión | Decimonovena pasada (2026-09-06): el bloqueo Incapsula cubre todo `cne.gob.ec`, incluyendo el enlace de descarga final, no solo el micrositio de resultados; `httpx` con headers de Chrome real sigue recibiendo el challenge JS. Navegador real sí pasa el challenge (de forma intermitente) y expone datasets reales por proceso electoral 2002-2025 (WP Download Manager) — estructura y endpoint AJAX ya mapeados. Construir un cliente requeriría Playwright (dependencia nueva para el proyecto); decisión pendiente de Daniel; sin evidencia de que el bloqueo haya cambiado (Vigésimo cuarta pasada) → RESEARCH.md § Decimonovena pasada |
| Geoportales municipales (Quito, Riobamba, Portoviejo/Fénix, Ambato) | No iniciado | Encontrados vía directorio de "Municipios Abiertos" (`municipiosabiertos.gob.ec`); patrón WMS/WFS como INAMHI/SIPA, no CKAN. URL exacta del GeoServer/ArcGIS sin confirmar para ninguno; Quito además tenía "la primera plataforma de datos abiertos del país" (2014) sin catálogo vivo encontrado en esta pasada → RESEARCH.md § Decimosexta pasada |
| Vivienda MIDUVI | No iniciado | El ministerio se renombró a "Hábitat y Vivienda" (`habitatyvivienda.gob.ec`) — verificado en vivo que también falla a nivel TLS: el certificado presentado cubre ~25 otros dominios `.gob.ec` pero no este, un problema de configuración TLS compartida del gobierno, no solo del dominio viejo; CKAN cubre parcialmente (5 datasets); entidad relacionada `viviendaydesarrollourbano.gob.ec` sin verificar en vivo → RESEARCH.md § Vivienda (MIDUVI), § Vigésimo cuarta pasada |
| Prensa | No iniciado, bajo valor confirmado | Fundamedios real y activo (informe semestral 2026: 100 agresiones enero-junio, histórico desde 2007) pero su contenido es informes narrativos en PDF, no datasets estructurados — encaja mejor con `read_pdf` puntual que con un tool dedicado; SECOM parece ser oficina de comunicación, no publicador de datos → RESEARCH.md § Vigésimo cuarta pasada |
| Datos legislativos/normativos | Investigado, alcance en duda | Jurisprudencia y proyectos de ley investigados a fondo; Daniel señaló que puede no ser relevante para el alcance del proyecto. FCD opera dos portales dedicados (`observatoriolegislativo.ec`, `ojoalconcejo.org`) que serían el punto de entrada si el alcance cambiara → RESEARCH.md § Datos legislativos, § Vigésimo cuarta pasada |
| Fuentes internacionales con foco Ecuador — FMI/IFS | No iniciado | El FMI tiene una API SDMX 2.1/3.0 (`data.imf.org`) cubriendo IFS (194 países), sin verificar en vivo todavía — CEPALSTAT y los dos datasets de IADB (Latin Macro Watch, DPI) ya están construidos (ver Hecho) → RESEARCH.md § Fuentes externas de sociedad civil, § Vigésimo cuarta pasada, § Vigésimo quinta pasada |

### Otros ítems parciales

| Fuente | Estado | Qué falta |
|---|---|---|
| SENESCYT/Educación Superior | Parcial | Biblioteca y SIAU CTI ya cubiertos (ver Hecho); registro de títulos sigue bloqueado por captcha (no automatizable, por política) → RESEARCH.md § SENESCYT, § Vigésimo cuarta pasada |
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
| BCEData — detección de cambios de revisión | El endpoint no expone ningún marcador explícito de revisión/versión (`ETag`/`Last-Modified` confirmado ausente, ver Duodécima pasada); solo quedaría comparación por contenido bajo demanda, ya cubierta por `audit_bce_catalog`. Fuera de alcance por decisión explícita de Daniel (2026-09-09) |
| BCEData ↔ IEM — revisar manualmente los ~75 candidatos restantes | De 77 candidatos que `compare_bce_sources` señala por similitud de etiqueta, solo 2 fueron confirmados con datos en vivo (Decimotercera pasada); los otros 75 exigirían comparar valores y metodología uno por uno, sin ninguna garantía de que la mayoría resulte en una equivalencia real (3 de los primeros 5 revisados ya resultaron falsos positivos). Daniel decidió no seguir revisando a mano (2026-09-09) — la cola de candidatos sin revisar queda expuesta tal cual en `compare_bce_sources`, sin tratarla como duplicado confirmado |
| IEM — hashing masivo del histórico completo | La infraestructura existe y quedó corregida (`hash_catalog_tables` deduplicaba mal — re-descargaba el mismo ZIP legado una vez por tabla miembro en vez de una vez por boletín — corregido 2026-09-09) y es accionable hoy vía `search_bce_iem(hash_archivos=true)`/`scripts/audit_bce_iem.py --hash-xlsx`. Correrla sobre las ~17.000-18.000 URLs únicas de los 367 boletines tomaría varias horas de carga sostenida contra el servidor del BCE sin que nada del proyecto dependa hoy de tener ese manifiesto; Daniel decidió no ejecutarla (2026-09-09) |
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
