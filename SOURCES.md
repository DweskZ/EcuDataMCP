# Fuentes completadas

Catálogo de fuentes de datos ya integradas al 100% (herramienta MCP
construida y verificada en vivo), sacadas de [ROADMAP.md](ROADMAP.md) para
mantenerlo enfocado en lo pendiente. Para el detalle de cada hallazgo —
cifras exactas, bugs encontrados, pasos de verificación — ver
[RESEARCH.md](RESEARCH.md).

## SRI

- `search_sri_datasets` — página de datasets.
- `search_sri_estadisticas_recaudacion` — reportes XLSX mensuales de
  recaudación por provincia/cantón/sector, complementario a `/datasets`.
  → RESEARCH.md § Séptima pasada

## BCE

- `search_bce_remesas` (`helpers/bce_remesas_client.py`) — Remesas de
  trabajadores: resultados agregados, serie histórica y bases mensuales,
  incluida la desagregación por entidad desde julio de 2025. "Histórica"
  (pre-cambio) y "BDD" (post-cambio) son series metodológicamente
  distintas. → https://contenido.bce.fin.ec/series-de-datos-remesas-de-trabajadores/
- `list_bce_indicadores_diarios`/`get_bce_indicador_diario`
  (`helpers/bce_indicadores_diarios_client.py`) — familia de "indicadores en
  línea": widgets Highcharts en varias páginas de `contenido.bce.fin.ec`,
  cada uno apuntando a un JSON plano sin auth. Catálogo descubierto en vivo
  desde los datos mismos: 49 series en 13 archivos, incluidas Riesgo País
  (D, 2004→hoy), Producción Petrolera Nacional (D, 2018→hoy) y
  SPI/SCI/SPL/CCC (M, 2010→hoy). Nunca devuelve la serie completa — solo una
  ventana acotada (tope 366) más el rango como metadata.
  → RESEARCH.md § Décima pasada, § Decimotercera pasada
- `search_bce_indices`/`get_bce_indice_archivo` (`helpers/bce_indices_client.py`)
  — sistema genérico de páginas "índice" (gestor editorial del propio BCE):
  ~35 páginas cuyo slug termina en "-indice(s)", cada una un archivo
  histórico completo (año por año o semanal) para una publicación con
  nombre propio (boletines sectoriales, índices de precios/confianza,
  divisas, balanza de pagos, remesas). 30/36 páginas candidatas exponen
  realmente el widget. → RESEARCH.md § Duodécima pasada
- Paquetes sectoriales — resuelto vía el sistema de índices para 4 de 5:
  petróleo, minería, cemento y compra/venta de divisas. Sigue sin
  encontrarse una página BCE dedicada a agricultura (probablemente vive en
  MAG/INEC). → RESEARCH.md § Duodécima pasada
- `search_bce_precios_comex` (`helpers/bce_precios_comex_client.py`) —
  índices de precios de comercio exterior: BCEData (`id_grupo=134`) ya
  cubre IPX/IPM/ITI agregados; este tool añade el detalle ausente en
  BCEData — precios/valor/volumen desagregados por categoría de uso
  económico y por producto individual de exportación.
  → RESEARCH.md § Decimotercera pasada

## SIPA (Ministerio de Agricultura)

- `list_sipa_modulos`/`get_sipa_modulo_archivos` — 30 archivos Excel reales
  en 4 módulos (económico/productivo/social/censos).
  → RESEARCH.md § Sitios de ministerios individuales
- `search_sipa_geoportal_capas`/`get_sipa_geoportal_capa_datos`
  (`helpers/sipa_geoportal_client.py`) — geoportal GeoServer: 24 endpoints
  "virtuales" por workspace, 277 capas WMS, 257 con WFS `GetFeature` real.
  `sigtierras/catastro_rural` (la capa más valiosa) es solo-WMS, WFS
  deshabilitado explícitamente en el servidor. `https://` sigue fallando el
  handshake TLS. → RESEARCH.md § Séptima pasada, § Decimocuarta pasada
- `get_sipa_resumen_indicadores` (`helpers/sipa_resumen_indicadores_client.py`)
  — de los 7 ítems del tablero "Indicadores Sectoriales", 6 son callejones
  sin salida (Tableau Server o flipbook JS); solo "Resumen de Indicadores"
  es real — PDFs mensuales Joomla, 2018-2026. → RESEARCH.md § Decimocuarta pasada

## Contraloría General del Estado

- `list_contraloria_informes`/`get_contraloria_informe` — CSV trimestrales
  reales de informes de auditoría aprobados a cualquier institución
  pública. De paso corrigió un bug real en el sniffing de delimitador CSV
  compartido (`helpers/csv_reader.py`). → RESEARCH.md § Sitios de ministerios individuales
- "Plan anual de control" — mismo patrón `WFDescarga.aspx` ya implementado
  en `helpers/contraloria_client.py` (solo cambia `tipo`, más un segundo
  seed page `Portal/Sistema/PlanAnualControl`). `get_contraloria_informe`
  distingue el `tipo` no-CSV y devuelve metadata + puntero a `read_pdf` en
  vez de intentar `preview_csv`. → RESEARCH.md § Séptima pasada

## gob.ec

- `get_tramite_estadisticas` — serie mensual real de atenciones/quejas por
  trámite desde 2021 (confirmado en vivo: 63 meses para Cédula de
  Identidad, may-2021→jul-2026), sin auth. Sin endpoint masivo — se pide
  trámite por trámite, igual que `get_tramite_info`. → RESEARCH.md § Séptima pasada

## Sector eléctrico

- `get_cenace_tablero` (`helpers/cenace_client.py`) — CENACE Información
  Operativa: 5 tableros server-rendered, cada uno un snapshot "a este
  instante" sin serie histórica real detrás — extrae los 6 números de
  resumen más el desglose por distribuidora; deliberadamente no extrae el
  desglose por planta (solo vive en blobs Plotly). TTL de caché corto
  (180s). → RESEARCH.md § Décima pasada

### Descartadas

- `sisdatbi.arconel.gob.ec` — confirmado con VPN que es bloqueo geográfico,
  no caída; sirve una app PHP con login obligatorio, sin contenido
  accesible sin credenciales. → RESEARCH.md § Decimoquinta pasada
- CELEC EP (transparencia/rendición de cuentas) — contenido real solo en
  LOTAIP por unidad de negocio, cumplimiento administrativo genérico, no
  dato sectorial; no se recomienda construir. → RESEARCH.md § Decimoquinta pasada

## CNT/ARCOTEL (telecomunicaciones)

- `search_arcotel_reportes_mensuales`/`search_arcotel_boletines`
  (`helpers/arcotel_client.py`) — Reportes Estadísticos Mensuales
  (ene-2017→jun-2026, ~2 meses de rezago) y Boletín Estadístico
  (anual/temático 2015-2024). Solo PDF, sin CSV/API.
  → RESEARCH.md § Octava pasada, § Decimocuarta pasada

## IG-EPN

- `search_sismos` — catálogo sísmico.
- `search_informes_igepn`/`get_informe_igepn`
  (`helpers/igepn_informes_client.py`) — app JSF/PrimeFaces separada en
  `informes.igepn.edu.ec`, sin URL estable por documento (sesión +
  ViewState + POST de descarga). Solo "Tipo" y "Año" filtran de verdad en
  el servidor — el resto se filtra client-side (mismo patrón "reciente y
  no exhaustivo" de `search_sismos`). → RESEARCH.md § Undécima pasada

## SGR

- `search_sgr_sitreps`/`get_sgr_sitrep_archivos`/
  `list_sgr_biblioteca_categorias`/`get_sgr_biblioteca_categoria_archivos`
  (`helpers/sgr_publicaciones_client.py`) — 54 eventos adversos 2016-2026
  con sus PDFs SITREP, y Biblioteca (19 categorías, ~1660 documentos de
  mapas de amenaza/rutas de evacuación) — una parte de los enlaces de
  Biblioteca da 404 en vivo, sin patrón claro.
  → RESEARCH.md § Séptima pasada, § Decimocuarta pasada

## INEVAL

- `list_ineval_familias`/`get_ineval_familia_archivos`
  (`helpers/ineval_client.py`) — 9 familias de exámenes nacionales (Ser
  Bachiller, Ser Estudiante, Ser Maestro, Ser Profesional, Llece), 557
  enlaces de descarga, sin login/CAPTCHA. → RESEARCH.md § INEVAL

## Superbancos

- `list_superbancos_secciones`/`get_superbancos_seccion_archivos`
  (`helpers/superbancos_client.py`) — cubre Boletines Financieros
  Mensuales, Servicios Financieros, Información Histórica y Calendario
  Estadístico.
- Widget OneDrive de Boletines Financieros descifrado — 224 archivos
  verificados en vivo (1997-2026). → RESEARCH.md § Duodécima pasada
- `servicios_financieros`, 3 widgets OneDrive conectados — 312 archivos
  (antes ~68 solo estático), incluye "Estadísticas Generales" (9
  categorías) y "Resoluciones de Servicios Financieros".
  → RESEARCH.md § Décima pasada

## MEF/SENAE

- `search_mef_fiscal(fuente="mef"|"senae")` (`helpers/mef_fiscal_client.py`)
  — archivo corriente de 76 XLSX del MEF (Ingresos/Gastos/Activos/BLL/
  Financiamiento SPNF, metodología GFSM, 2025-01→2026-09) y 60 archivos de
  SENAE (recaudación aduanera por tipo de gravamen, 2012-2021).
  "Arancelarios" es solo el arancel, más chico que la "recaudación
  aduanera" total de prensa. → RESEARCH.md § Recaudación arancelaria,
  § Decimocuarta pasada

## MINEDEC

- `search_minedec_matricula` (`helpers/minedec_client.py`) — registro
  histórico de matrícula básica 2009-2025, 5 archivos reales
  (`educacion.gob.ec/datos-abiertos-minedec/`, WordPress, no CKAN).
  → RESEARCH.md § Decimocuarta pasada

## SEPS

- `list_seps_secciones`/`get_seps_seccion_archivos`
  (`helpers/seps_client.py`) — 26 secciones reales entre
  `estadisticas-sfps/` (22) y `estadisticas-eps/` (4), incluida
  `sfps_reportes_calificacion_de_riesgos` (boletines PDF anuales
  2020-2025, 112 entidades). → RESEARCH.md § Decimotercera pasada

## CNIG

- `search_cnig_femicidios` (`helpers/cnig_client.py`) — 20 tablas PDF en
  `igualdadgenero.gob.ec/violencia/`, incluida "Femicidios y Homicidios
  Intencionales de Mujeres" — el archivo publicado hoy tiene corte real a
  abr-2023 pese a que la fuente se declara "semanal".
  → RESEARCH.md § Decimotercera pasada

## INAMHI

- `search_inamhi_capas`/`get_inamhi_capa_datos` (`helpers/inamhi_client.py`)
  — WMS GetCapabilities expone 222 capas (precipitación, WRF, límites
  administrativos), 199 con WFS `GetFeature` real; sin organización CKAN
  propia, este cliente es la única cobertura automatizable. Sin capa de
  estaciones con observaciones puntuales — todo vía WFS son productos
  agregados por polígono. → RESEARCH.md § Decimotercera pasada

## Aviación civil

- `get_metar`/`get_notam`/`get_sigmet` (`helpers/aviacion_client.py`) —
  `/metar/{icao}`, `/notam` y `/sigmet` de `ais.aviacioncivil.gob.ec` son
  públicos sin sesión (solo `/fpl/*` exige login); METAR se actualiza cada
  30-60 min. SIGMET es a nivel de FIR completo (un solo FIR en Ecuador,
  SEFG), sin parámetro de aeródromo. → RESEARCH.md § Decimotercera pasada

## INEC / Ecuador en Cifras

- `search_inec_estadisticas`/`get_inec_estadistica_files` (~75 temas:
  boletines + series históricas agregadas) + `search_biinec_extras` (lista
  curada de los 2-3 registros de BIINEC que sí son exclusivos — desechos
  peligrosos en salud, módulos ambientales ENEMDU/ECV; no un cliente
  genérico). → RESEARCH.md § Ecuador en Cifras
- `search_inec_publicaciones`/`get_inec_publicacion_archivos` — API REST
  pública de WordPress (`/wp-json/wp/v2/posts`), en vez de depender solo
  del scraping de páginas de tema: el menú mega-menu no es el mismo en
  cada página del sitio, así que `search_inec_estadisticas` sola se perdía
  páginas como `enemdu-anual/`. Búsqueda de texto completo real, 1,707
  posts. → RESEARCH.md § Novena pasada
- Las 4 categorías "macro" del menú de INEC (Cuentas económicas, balanza de
  pagos, finanzas públicas) confirmadas vacías por diseño: esa
  responsabilidad es del BCE, INEC nunca publicó nada propio ahí.
  → RESEARCH.md § Novena pasada
- Micrositio de Geografía Estadística con el Clasificador Geográfico
  oficial, descubrible vía `search_inec_estadisticas`/
  `get_inec_estadistica_files`. Drift real corregido en
  `helpers/data/{cantones,parroquias}.json` contra
  `CLASIFICADOR_GEOGRAFICO_2026.zip` (reasignación de La Concordia, cantón
  nuevo Sevilla Don Bosco, disputas de "zona 90") — total de cantones ahora
  225. → RESEARCH.md § Novena pasada
- `search_censo_recursos` (`helpers/censo_client.py`), solo metadata + URL
  — 36 archivos reales de `censoecuador.gob.ec`. → RESEARCH.md § Novena pasada

## Cuenca en Datos

- CKAN municipal vía `source="cuenca"` en los tools genéricos.

## Ministerio del Trabajo

- `list_sut_indicadores`/`get_sut_indicador_schema`/`query_sut_indicador`
  (`helpers/sut_powerbi_client.py`) — Power BI "Indicadores" de SUT
  descifrado: protocolo AJAX público sin sesión, generaliza a los 8
  dashboards de SUT sin código por-dashboard. → RESEARCH.md § Décima pasada
- `search_trabajo_boletin_anual` (`helpers/trabajo_boletin_anual_client.py`,
  lista fija) — Boletín Estadístico Anual "El Mercado Laboral en el
  Ecuador": tres ediciones confirmadas (2020/2021/2022, vía Wayback Machine
  para 2021); ninguna edición 2023-2025 encontrada — cobertura marcada
  explícitamente como incompleta. → RESEARCH.md § Décima pasada, § Decimocuarta pasada
- Salarios mínimos sectoriales — `search_salarios_sectoriales`
  (`helpers/salarios_sectoriales_client.py`): `trabajo.gob.ec/biblioteca/`
  tiene un enlace estable por documento, una entrada por año 2020-2025, sin
  tabla 2026 (vigente la de 2025 por inacción). Revierte el veredicto
  "débil" de la Octava pasada. → RESEARCH.md § Octava pasada, § Decimocuarta pasada

## MIES / Ministerio de Desarrollo Humano

- `search_infomies_bases_mensuales`/`search_infomies_boletines_zonales`
  (`helpers/infomies_client.py`) — portal `info.desarrollohumano.gob.ec`
  ("infoMIES"). Bases mensuales solo para el año en curso (años cerrados =
  1 archivo/diciembre); "Reporte Boletines Zonales" consolidado 2021-2026
  aún actualizándose. → RESEARCH.md § Décima pasada, § Decimocuarta pasada
