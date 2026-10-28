# Catálogo de fuentes y tools

Generado por `scripts/generate_catalog.py` desde `resources/catalog.py` y las
descripciones de `tools/*.py`; no editar a mano.

54 fuentes, 84 tools públicas.

## Datos Abiertos CKAN

- Id: `ckan`
- Base: https://www.datosabiertos.gob.ec/

- `search_datasets`: Search CKAN open-data datasets (national portal by default; see source). Use sort="recent" without a query to browse new or updated datasets. Next: list_dataset_resources. For trámites, regulations or contracts use search_ecuador.
- `get_dataset_info`: Metadata for one CKAN dataset: description, organization, tags, dates, license, update frequency and the publisher's source URL. Take dataset_id from search_datasets; next list_dataset_resources for its files.
- `list_dataset_resources`: Files (resources) in a CKAN dataset with format, size, URL and dates, flagging name groups that look like periodic series. Next: preview_resource_data or query_resource_data.
- `get_resource_info`: Metadata for one CKAN resource (file): format, size, MIME type, download URL and parent dataset. Take resource_id from list_dataset_resources; then preview_resource_data or query_resource_data for its contents.
- `preview_resource_data`: First rows of a CKAN resource as a table: CSV/TSV, JSON/GeoJSON, XLS/XLSX/XLSB, ODS, and ZIP/tar.gz wrapping a CSV. Max 5 MB; for DataStore resources prefer query_resource_data.
- `download_resource`: Raw bytes of a CKAN resource, base64-encoded, for formats the preview can't parse. Max 5 MB. Use format="json"; text only confirms the download.
- `query_resource_data`: Query a tabular CKAN resource through the DataStore without downloading it: full-text query, exact filters (filters_json), sort and pagination.
- `detect_series_pattern`: Tell whether a dataset's periodic files are cumulative (newest file suffices) or incremental (combine all) by comparing period values in the two newest files. Heuristic over up to 500 rows each.
- `read_pdf`: Extract text from a PDF at a direct URL (max 5 MB, 20 pages per call; pages selects a range). No OCR: scanned PDFs come back empty.
- `search_organizations`: Search the institutions publishing on a CKAN portal (98+ on the national one: INEC, SRI, MSP, BCE...). Returns the slugs get_organization_info takes; to find datasets by topic use search_datasets.
- `get_organization_info`: One CKAN organization and its datasets, the way to browse a large publisher (e.g. sri-servicio-de-rentas-internas). Take the slug from search_organizations; query filters dataset titles. To search by topic across publishers use search_datasets.
- `list_categories`: Thematic categories of a CKAN portal with dataset counts; pass a name as search_datasets' category.
- `get_category_info`: Details and sample datasets for one CKAN thematic category (name from list_categories).

## Cuenca en Datos (portal municipal CKAN, independiente del nacional)

- Id: `cuenca`
- Base: https://cuencaendatos.cuenca.gob.ec/

- `search_datasets`: Search CKAN open-data datasets (national portal by default; see source). Use sort="recent" without a query to browse new or updated datasets. Next: list_dataset_resources. For trámites, regulations or contracts use search_ecuador.
- `get_dataset_info`: Metadata for one CKAN dataset: description, organization, tags, dates, license, update frequency and the publisher's source URL. Take dataset_id from search_datasets; next list_dataset_resources for its files.
- `list_dataset_resources`: Files (resources) in a CKAN dataset with format, size, URL and dates, flagging name groups that look like periodic series. Next: preview_resource_data or query_resource_data.
- `get_resource_info`: Metadata for one CKAN resource (file): format, size, MIME type, download URL and parent dataset. Take resource_id from list_dataset_resources; then preview_resource_data or query_resource_data for its contents.
- `preview_resource_data`: First rows of a CKAN resource as a table: CSV/TSV, JSON/GeoJSON, XLS/XLSX/XLSB, ODS, and ZIP/tar.gz wrapping a CSV. Max 5 MB; for DataStore resources prefer query_resource_data.
- `download_resource`: Raw bytes of a CKAN resource, base64-encoded, for formats the preview can't parse. Max 5 MB. Use format="json"; text only confirms the download.
- `query_resource_data`: Query a tabular CKAN resource through the DataStore without downloading it: full-text query, exact filters (filters_json), sort and pagination.
- `detect_series_pattern`: Tell whether a dataset's periodic files are cumulative (newest file suffices) or incremental (combine all) by comparing period values in the two newest files. Heuristic over up to 500 rows each.
- `read_pdf`: Extract text from a PDF at a direct URL (max 5 MB, 20 pages per call; pages selects a range). No OCR: scanned PDFs come back empty.
- `search_organizations`: Search the institutions publishing on a CKAN portal (98+ on the national one: INEC, SRI, MSP, BCE...). Returns the slugs get_organization_info takes; to find datasets by topic use search_datasets.
- `get_organization_info`: One CKAN organization and its datasets, the way to browse a large publisher (e.g. sri-servicio-de-rentas-internas). Take the slug from search_organizations; query filters dataset titles. To search by topic across publishers use search_datasets.
- `list_categories`: Thematic categories of a CKAN portal with dataset counts; pass a name as search_datasets' category.
- `get_category_info`: Details and sample datasets for one CKAN thematic category (name from list_categories).

## Data Mashca (portal municipal CKAN de Latacunga, independiente del nacional)

- Id: `latacunga`
- Base: https://datosabiertos.latacunga.gob.ec/

- `search_datasets`: Search CKAN open-data datasets (national portal by default; see source). Use sort="recent" without a query to browse new or updated datasets. Next: list_dataset_resources. For trámites, regulations or contracts use search_ecuador.
- `get_dataset_info`: Metadata for one CKAN dataset: description, organization, tags, dates, license, update frequency and the publisher's source URL. Take dataset_id from search_datasets; next list_dataset_resources for its files.
- `list_dataset_resources`: Files (resources) in a CKAN dataset with format, size, URL and dates, flagging name groups that look like periodic series. Next: preview_resource_data or query_resource_data.
- `get_resource_info`: Metadata for one CKAN resource (file): format, size, MIME type, download URL and parent dataset. Take resource_id from list_dataset_resources; then preview_resource_data or query_resource_data for its contents.
- `preview_resource_data`: First rows of a CKAN resource as a table: CSV/TSV, JSON/GeoJSON, XLS/XLSX/XLSB, ODS, and ZIP/tar.gz wrapping a CSV. Max 5 MB; for DataStore resources prefer query_resource_data.
- `download_resource`: Raw bytes of a CKAN resource, base64-encoded, for formats the preview can't parse. Max 5 MB. Use format="json"; text only confirms the download.
- `query_resource_data`: Query a tabular CKAN resource through the DataStore without downloading it: full-text query, exact filters (filters_json), sort and pagination.
- `detect_series_pattern`: Tell whether a dataset's periodic files are cumulative (newest file suffices) or incremental (combine all) by comparing period values in the two newest files. Heuristic over up to 500 rows each.
- `read_pdf`: Extract text from a PDF at a direct URL (max 5 MB, 20 pages per call; pages selects a range). No OCR: scanned PDFs come back empty.
- `search_organizations`: Search the institutions publishing on a CKAN portal (98+ on the national one: INEC, SRI, MSP, BCE...). Returns the slugs get_organization_info takes; to find datasets by topic use search_datasets.
- `get_organization_info`: One CKAN organization and its datasets, the way to browse a large publisher (e.g. sri-servicio-de-rentas-internas). Take the slug from search_organizations; query filters dataset titles. To search by topic across publishers use search_datasets.
- `list_categories`: Thematic categories of a CKAN portal with dataset counts; pass a name as search_datasets' category.
- `get_category_info`: Details and sample datasets for one CKAN thematic category (name from list_categories).

## SRI: datasets fuera de CKAN, RUC y estadísticas de recaudación

- Id: `sri`
- Base: https://www.sri.gob.ec/datasets

- `search_archivos`: File links from one institution's catalog, filtered by text: SRI, MEF, SENAE, Census 2022, MINEDEC, SENESCYT, MSP, CNIG, Trabajo, ARCOTEL and BCE (remesas, comex prices, latest publications). Links, not contents.
- `get_sri_ruc_info`: Public SRI record for one 13-digit RUC: name, status, type, activity, dates and registered establishments. No tax amounts.
- `search_sri_ruc`: Find SRI taxpayers by partial razón social or trade name (min 4 characters) when the RUC is unknown. SRI caps results at 100.

## ARCSA Base de Registros Emitidos (registro sanitario vigente)

- Id: `arcsa`
- Base: https://www.controlsanitario.gob.ec/base-de-datos/

- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).

## gob.ec trámites / instituciones / regulaciones

- Id: `gobec`
- Base: https://www.gob.ec/api/v1/

- `search_tramites`: Search gob.ec government procedures (trámites). Pass institution_id (SRI=8, IESS=163, Registro Civil=23, ANT=48, Cancillería=6; others via list_instituciones) for relevant results.
- `get_tramite_info`: One gob.ec trámite's requirements, beneficiaries, cost and responsible institution (tramite_id from search_tramites).
- `get_tramite_estadisticas`: Monthly attentions (people served) and complaints for one gob.ec trámite since mid-2021, one trámite at a time. Take tramite_id from search_tramites; for requirements and cost use get_tramite_info.
- `search_regulaciones`: Search or list regulations published on gob.ec, with Registro Oficial references when available.
- `get_regulacion_info`: One gob.ec regulation's type, Registro Oficial reference, description and PDF link. Take regulacion_id from search_regulaciones; read the PDF's text with read_pdf.
- `list_instituciones`: List or search public institutions registered on gob.ec, with their IDs.
- `get_institucion_info`: One gob.ec institution's acronym, sector, description and websites. Take institucion_id from list_instituciones (SRI=8, IESS=163, Registro Civil=23); for its procedures use search_tramites.

## SERCOP Contrataciones Abiertas OCDS

- Id: `sercop`
- Base: https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/

- `search_contratos`: Search SERCOP public procurement (OCDS) by keyword (min 3 characters), year, buyer or supplier.
- `get_contrato_info`: Full OCDS record of one SERCOP procurement process (ocid from search_contratos): buyer, tender, awards, contracts.

## SGR Gestión de Riesgos (COE + SAT)

- Id: `sgr`
- Base: https://sgrportal.gestionderiesgos.gob.ec/server/rest/services

- `search_eventos_riesgo`: Current and recent SGR (Gestión de Riesgos) risk events from the live COE feed: landslides, floods, structural damage, with location, status and impacts. No history; for past event dossiers use search_sgr_sitreps.
- `list_sat_tsunami`: SGR tsunami early-warning (SAT) stations with codes and coordinates: a static station list, not alerts. For recent seismic events use search_sismos.

## SGR Gestión de Riesgos (SITREP de eventos adversos y Biblioteca)

- Id: `sgr-publicaciones`
- Base: https://www.gestionderiesgos.gob.ec/

- `search_sgr_sitreps`: SGR's archive of ~54 adverse-event dossiers 2016-2026 (earthquakes, rainy and fire seasons, volcanic activity) with status. Next: get_sgr_sitrep_archivos(evento_url) for the SITREP PDFs.
- `get_sgr_sitrep_archivos`: SITREP PDF links (national, provincial, cantonal) for one SGR event page from search_sgr_sitreps. Returns links, not contents.
- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).

## INAMHI (geoportal hidrometeorológico, capas WMS/WFS)

- Id: `inamhi`
- Base: https://geoservicios.inamhi.gob.ec/geoserver

- `search_capas_geo`: Search layers of a geoportal: inamhi (rainfall normals and anomalies, WRF grids, watersheds), mag (agro zoning, land cover, agricultural censuses, rural cadastre), arconel (distributor energy balance and billing 1999-2025, power plants, grid) or celec (CELEC plants, transmission network).
- `get_capa_geo_datos`: Attributes of a layer from search_capas_geo, geometry dropped. GeoServer (inamhi, mag): a sample of up to 20 features. ArcGIS (arconel, celec): up to 500 rows with a SQL filtro and offset.

## DGAC / AIS Ecuador (AIP de aeródromos, METAR, NOTAM, SIGMET)

- Id: `aviacion`
- Base: https://www.ais.aviacioncivil.gob.ec/

- `list_aip_aerodromos`: ICAO codes and names of aerodromes/helipads with a published AIP AD 2 page (DGAC eAIP). Next: get_aip_aerodromo.
- `get_aip_aerodromo`: Full published AIP AD 2 data sheet for one aerodrome (ICAO code): coordinates, runways, hours, services, frequencies, procedures.
- `get_aviso_aeronautico`: Live aeronautical notices from DGAC/AIS: metar (latest weather reports) or notam (active notices) for an aerodrome ICAO code, e.g. SEQM; sigmet (active SIGMETs for the whole FIR, no code needed). Raw ICAO text.

## Instituto Geofísico EPN (catálogo sísmico + informes sísmicos/volcánicos)

- Id: `igepn`
- Base: https://www.igepn.edu.ec/portal/eventos/www/

- `search_sismos`: Recent earthquakes from the IG-EPN catalog feed: magnitude, depth, coordinates, time and place. Filter by text, minimum magnitude and days.
- `search_informes_igepn`: Search IG-EPN's PDF report archive: seismic bulletins and volcanic alerts/reports, by year and group. Next: get_informe_igepn to read one. For raw earthquake data use search_sismos.
- `get_informe_igepn`: Download and extract the text of one IG-EPN report from search_informes_igepn, re-located by exact nombre, grupo and anio (plus volcan when names repeat). pages limits the range (max 20/call).

## DPA provincias, cantones y parroquias (referencia offline INEC)

- Id: `geo`

- `lookup_ubicacion`: Look up Ecuador's provinces, cantons and parroquias (rural and urban) with INEC codes, region and population. For parroquias, filter by canton and/or provincia.

## ANDA / INEC (encuestas, censos y microdatos)

- Id: `anda`
- Base: https://anda.inec.gob.ec/anda5/

- `search_anda`: Search INEC's ANDA catalog of 437+ surveys and censuses; the broadest INEC index. Entries without microdata point to search_inec_estadisticas. Next: get_anda_survey_info.
- `get_anda_survey_info`: Full metadata for one ANDA survey (string idno from search_anda): scope, variables, microdata availability and access terms.
- `download_anda_microdata`: Direct links to an ANDA survey's microdata files (accepts ANDA's research-use terms). Check get_anda_survey_info first; returns links to multi-MB ZIPs.

## Ecuador en Cifras / INEC (estadísticas publicadas)

- Id: `inec-estadisticas`
- Base: https://www.ecuadorencifras.gob.ec/

- `search_inec_estadisticas`: INEC's ~75 statistical topic pages on ecuadorencifras.gob.ec (IPC, ENEMDU, pobreza, cuentas nacionales...), where published aggregate series live. Next: get_inec_estadistica_files.
- `get_inec_estadistica_files`: File links (bulletins, methodology, historical series) on one INEC topic page from search_inec_estadisticas.
- `search_inec_publicaciones`: Every INEC post on Ecuador en Cifras, newest first; use for the latest release of an operation (topic pages can go stale). Next: get_inec_publicacion_archivos.
- `get_inec_publicacion_archivos`: File links (PDF/XLSX/CSV/ZIP) in one INEC publication (id or URL from search_inec_publicaciones).

## Siniestros de tránsito (registros de la ANT, vía INEC y CKAN)

- Id: `ant-siniestros`
- Base: https://www.ecuadorencifras.gob.ec/

- `search_siniestros_ant`: Find Ecuador road-crash (siniestros de tránsito) data from ANT records: INEC quarterly/annual releases with XLSX/CSV microdata plus CKAN datasets (SPPAT deaths, ANT). ant.gob.ec is unreachable.

## BIINEC / INEC (registros exclusivos curados)

- Id: `inec-biinec`
- Base: https://aplicaciones3.ecuadorencifras.gob.ec/BIINEC-war/

- `search_biinec_extras`: Small curated list of INEC BIINEC registries found nowhere else (e.g. environmental modules). A last resort; not a live BIINEC search.

## Censo Ecuador 2022 / INEC (microdatos completos del censo)

- Id: `inec-censo`
- Base: https://www.censoecuador.gob.ec/

- `search_archivos`: File links from one institution's catalog, filtered by text: SRI, MEF, SENAE, Census 2022, MINEDEC, SENESCYT, MSP, CNIG, Trabajo, ARCOTEL and BCE (remesas, comex prices, latest publications). Links, not contents.

## Banco Central del Ecuador (BCEData, Información Estadística Mensual, indicadores diarios en línea y remesas de trabajadores)

- Id: `bce`
- Base: https://contenido.bce.fin.ec/

- `search_indicadores_bce`: Search BCEData indicator groups (monetary, fiscal, external, real sector), matching series names too. Not CPI or poverty (INEC). First call after 24h can take 10-15 s. Next: get_indicador_bce.
- `get_indicador_bce`: Time series of one BCEData group (id_grupo from search_indicadores_bce), with optional YYYY-MM range, frequency and unit.
- `audit_bce_catalog`: Operator tool: audit BCEData catalog coverage (groups, series, failures); optionally save a snapshot, compare with the last one or probe values. Writes local files.
- `compare_bce_sources`: Operator tool: candidate equivalences between BCEData series and IEM tables by label. Candidates only; confirm definitions before combining. Can save a review file.
- `search_bce_iem`: Search the Excel tables of BCE's monthly IEM bulletin (trade by country, debt, fiscal, oil, GDP detail). historico=true searches past bulletins. Next: get_bce_iem_table.
- `get_bce_iem_table`: One IEM XLSX table (table_id from search_bce_iem): date-filterable series for the standard layout, a faithful preview otherwise. boletin_numero selects a past bulletin.
- `search_bce_paginas`: BCE publication pages with file archives: indices (sector bulletins, price and confidence indices, FX, balance of payments; some back to 2004) or cuentas_nacionales (annual, quarterly, regional accounts, input-output, IMAEC). Next: get_bce_pagina_archivos(pagina_id).
- `get_bce_pagina_archivos`: Files of one BCE publication page (pagina_id from search_bce_paginas): title, URL and format, most recent first. anio filters the indices catalog by year.
- `list_catalogo`: List one source's catalog, the step before its get tool: arconel (get_arconel_reporte), bce_diarios (get_bce_indicador_diario), contraloria (get_contraloria_informe), iess (get_iess_archivos), sut and judicatura (get_sut_indicador_schema, query_sut_indicador with the same fuente).
- `get_bce_indicador_diario`: One BCE daily/monthly indicator (archivo and codigo from list_catalogo(fuente='bce_diarios')): the last ultimos_n points or a date range, capped at 366 rows.
- `search_bce_calendario`: BCE's forward-looking statistical release calendar: dates, category, periodicity and reference period. solo_proximas=true keeps upcoming releases. Says when data will be published, not the data itself; for values use get_indicador_bce.

## SIPA / Ministerio de Agricultura (estadísticas agropecuarias)

- Id: `sipa`
- Base: https://sipa.agricultura.gob.ec/

- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).
- `get_sipa_resumen_indicadores`: Monthly PDF links of SIPA's (MAG) "Resumen de Indicadores" for one year, 2018 onward.
- `search_capas_geo`: Search layers of a geoportal: inamhi (rainfall normals and anomalies, WRF grids, watersheds), mag (agro zoning, land cover, agricultural censuses, rural cadastre), arconel (distributor energy balance and billing 1999-2025, power plants, grid) or celec (CELEC plants, transmission network).
- `get_capa_geo_datos`: Attributes of a layer from search_capas_geo, geometry dropped. GeoServer (inamhi, mag): a sample of up to 20 features. ArcGIS (arconel, celec): up to 500 rows with a SQL filtro and offset.

## EP Petroecuador (Cifras Institucionales)

- Id: `petroecuador`
- Base: https://www.eppetroecuador.ec/

- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).
- `read_pdf`: Extract text from a PDF at a direct URL (max 5 MB, 20 pages per call; pages selects a range). No OCR: scanned PDFs come back empty.

## Ministerio de Ambiente y Energía (estadística de hidrocarburos, minería y Balance Energético Nacional)

- Id: `energia`
- Base: https://www.ambienteyenergia.gob.ec/

- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).
- `read_pdf`: Extract text from a PDF at a direct URL (max 5 MB, 20 pages per call; pages selects a range). No OCR: scanned PDFs come back empty.

## Bolsa de Valores de Guayaquil (estadísticas históricas)

- Id: `bvg`
- Base: https://www.bolsadevaloresguayaquil.com/

- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).

## Bolsa de Valores de Quito (estadísticas)

- Id: `bvq`
- Base: https://www.bolsadequito.com/index.php/estadisticas

- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).

## Contraloría General del Estado (informes de auditoría)

- Id: `contraloria`
- Base: https://www.contraloria.gob.ec/Portal/24287

- `list_catalogo`: List one source's catalog, the step before its get tool: arconel (get_arconel_reporte), bce_diarios (get_bce_indicador_diario), contraloria (get_contraloria_informe), iess (get_iess_archivos), sut and judicatura (get_sut_indicador_schema, query_sut_indicador with the same fuente).
- `get_contraloria_informe`: Rows of one Contraloría audit-reports CSV (one row per approved report), or metadata and a read_pdf pointer for an annual plan.

## Superintendencia de Compañías (directorio de compañías, auditores externos)

- Id: `supercias`
- Base: https://mercadodevalores.supercias.gob.ec/reportes/

- `search_companias`: Search Supercías' registry of 226k+ companies by name or RUC: legal status, incorporation, representative, capital, CIIU, address. The first call may ask you to retry in 1-2 min while the export downloads.
- `get_compania_info`: Supercías registry record for one company by RUC: status, incorporation, representative, capital, CIIU, address. No financials.
- `search_auditores`: Search Supercías' registry of 1,447 authorized external auditors by name or ID.
- `get_auditor_info`: One external auditor's authorization, nationality and contact details by RUC or cédula.

## Superintendencia de Compañías (ranking financiero, 2008 en adelante)

- Id: `supercias-financials`
- Base: https://appscvsmovil.supercias.gob.ec/ranking/

- `search_ranking`: Rank Supercías companies by financial indicators for one fiscal year (2008 to the latest year), optionally by CIIU letter. descending=true for top-N by a column.
- `get_financials`: One company's Supercías financial history (fiscal years 2008 to the latest): revenue, assets, equity, profit, employees and ratios. Takes expediente or RUC; anio or desde/hasta narrow the years.

## Superintendencia de Bancos (boletines financieros, servicios financieros, información histórica)

- Id: `superbancos`
- Base: https://www.superbancos.gob.ec/estadisticas/portalestudios

- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).

## CENACE (snapshot en vivo de generación y demanda eléctrica, boletín mensual de transacciones y Biblioteca)

- Id: `cenace`
- Base: https://www.cenace.gob.ec/

- `get_cenace_tablero`: CENACE live grid snapshot: generation mix and demand now, yesterday, month or year to date. No historical queries.
- `get_cenace_boletin`: CENACE monthly electricity-market bulletin (2019 onward): production by resource, demand by distributor, average prices, trade with Colombia and Peru. Empty mes lists the issues; mes=YYYY-MM returns its text by page.
- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).

## ARCONEL (reportes estadísticos, capas ArcGIS de balance y facturación, estadística anual, tarifas y regulaciones)

- Id: `arconel`
- Base: https://arconel.gob.ec/

- `list_catalogo`: List one source's catalog, the step before its get tool: arconel (get_arconel_reporte), bce_diarios (get_bce_indicador_diario), contraloria (get_contraloria_informe), iess (get_iess_archivos), sut and judicatura (get_sut_indicador_schema, query_sut_indicador with the same fuente).
- `get_arconel_reporte`: Run one ARCONEL report (e.g. "Balance Energía" for a year) and return its rows. Slow, ~50 rows per page; max_paginas caps work and completo says if everything was read.
- `search_capas_geo`: Search layers of a geoportal: inamhi (rainfall normals and anomalies, WRF grids, watersheds), mag (agro zoning, land cover, agricultural censuses, rural cadastre), arconel (distributor energy balance and billing 1999-2025, power plants, grid) or celec (CELEC plants, transmission network).
- `get_capa_geo_datos`: Attributes of a layer from search_capas_geo, geometry dropped. GeoServer (inamhi, mag): a sample of up to 20 features. ArcGIS (arconel, celec): up to 500 rows with a SQL filtro and offset.
- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).

## CELEC EP (centrales de generación y red de transmisión, ArcGIS)

- Id: `celec`
- Base: https://portalarcgis.celec.gob.ec/server/rest/services/Hosted

- `search_capas_geo`: Search layers of a geoportal: inamhi (rainfall normals and anomalies, WRF grids, watersheds), mag (agro zoning, land cover, agricultural censuses, rural cadastre), arconel (distributor energy balance and billing 1999-2025, power plants, grid) or celec (CELEC plants, transmission network).
- `get_capa_geo_datos`: Attributes of a layer from search_capas_geo, geometry dropped. GeoServer (inamhi, mag): a sample of up to 20 features. ArcGIS (arconel, celec): up to 500 rows with a SQL filtro and offset.

## Empresa Eléctrica Quito (cronogramas de cortes de luz en PDF)

- Id: `eeq`
- Base: https://www.eeq.com.ec/

- `search_cortes`: Scheduled power cuts of one utility: crisis schedule PDFs from eeq (Quito, 2023-2024) and centrosur (2023 on), or current maintenance notices from emelnorte, elecgalapagos and eeasa. Next: get_cortes_horarios with an archivo.
- `get_cortes_horarios`: Parse one power-cut schedule or notice (archivo from search_cortes) into rows: date, time blocks without power, location and sectors, plus the motive for maintenance notices. query filters by place.

## Centrosur (cronogramas de cortes de luz en Azuay, Cañar y Morona Santiago)

- Id: `centrosur`
- Base: https://www.centrosur.gob.ec/

- `search_cortes`: Scheduled power cuts of one utility: crisis schedule PDFs from eeq (Quito, 2023-2024) and centrosur (2023 on), or current maintenance notices from emelnorte, elecgalapagos and eeasa. Next: get_cortes_horarios with an archivo.
- `get_cortes_horarios`: Parse one power-cut schedule or notice (archivo from search_cortes) into rows: date, time blocks without power, location and sectors, plus the motive for maintenance notices. query filters by place.

## Emelnorte (avisos de cortes por mantenimiento en Imbabura, Carchi y norte de Pichincha)

- Id: `emelnorte`
- Base: https://www.emelnorte.com/

- `search_cortes`: Scheduled power cuts of one utility: crisis schedule PDFs from eeq (Quito, 2023-2024) and centrosur (2023 on), or current maintenance notices from emelnorte, elecgalapagos and eeasa. Next: get_cortes_horarios with an archivo.
- `get_cortes_horarios`: Parse one power-cut schedule or notice (archivo from search_cortes) into rows: date, time blocks without power, location and sectors, plus the motive for maintenance notices. query filters by place.

## ElecGalápagos (avisos de mantenimientos programados por isla)

- Id: `elecgalapagos`
- Base: https://www.elecgalapagos.com.ec/

- `search_cortes`: Scheduled power cuts of one utility: crisis schedule PDFs from eeq (Quito, 2023-2024) and centrosur (2023 on), or current maintenance notices from emelnorte, elecgalapagos and eeasa. Next: get_cortes_horarios with an archivo.
- `get_cortes_horarios`: Parse one power-cut schedule or notice (archivo from search_cortes) into rows: date, time blocks without power, location and sectors, plus the motive for maintenance notices. query filters by place.

## EEASA (trabajos programados en Tungurahua y Pastaza)

- Id: `eeasa`
- Base: https://www.eeasa.com.ec/

- `search_cortes`: Scheduled power cuts of one utility: crisis schedule PDFs from eeq (Quito, 2023-2024) and centrosur (2023 on), or current maintenance notices from emelnorte, elecgalapagos and eeasa. Next: get_cortes_horarios with an archivo.
- `get_cortes_horarios`: Parse one power-cut schedule or notice (archivo from search_cortes) into rows: date, time blocks without power, location and sectors, plus the motive for maintenance notices. query filters by place.

## energia-ecuador.com vía Wayback Machine (horarios históricos de apagones)

- Id: `energia-ecuador`
- Base: https://web.archive.org/

- `get_energia_ecuador_snapshot`: Frozen Wayback Machine copy (2024-04-24) of the defunct national blackout-schedule portal energia-ecuador.com; only EEQ's Pichincha rotation survived. For current schedules use search_cortes and get_cortes_horarios.

## Ministerio del Trabajo / SUT (tableros Power BI en vivo: contratos, brechas de empleo, políticas de género)

- Id: `sut`
- Base: https://sut.trabajo.gob.ec/

- `list_catalogo`: List one source's catalog, the step before its get tool: arconel (get_arconel_reporte), bce_diarios (get_bce_indicador_diario), contraloria (get_contraloria_informe), iess (get_iess_archivos), sut and judicatura (get_sut_indicador_schema, query_sut_indicador with the same fuente).
- `get_sut_indicador_schema`: Queryable fields of one SUT or Judicatura dashboard (fuente): columns, measures ([medida]/[suma]/[promedio]) and date levels, for query_sut_indicador.
- `query_sut_indicador`: Live query of one SUT or Consejo de la Judicatura dashboard's data model (fuente): choose campos, optional equality filtros (plain columns only) and a row limite. Take the indicador from list_catalogo(fuente) and its valid campos from get_sut_indicador_schema.

## Consejo de la Judicatura (Portal de Estadística Judicial: tableros Power BI en vivo de audiencias, mediación, notarial, productividad de jueces, SUPA)

- Id: `judicatura`
- Base: https://fsweb.funcionjudicial.gob.ec/estadisticas/

- `list_catalogo`: List one source's catalog, the step before its get tool: arconel (get_arconel_reporte), bce_diarios (get_bce_indicador_diario), contraloria (get_contraloria_informe), iess (get_iess_archivos), sut and judicatura (get_sut_indicador_schema, query_sut_indicador with the same fuente).
- `get_sut_indicador_schema`: Queryable fields of one SUT or Judicatura dashboard (fuente): columns, measures ([medida]/[suma]/[promedio]) and date levels, for query_sut_indicador.
- `query_sut_indicador`: Live query of one SUT or Consejo de la Judicatura dashboard's data model (fuente): choose campos, optional equality filtros (plain columns only) and a row limite. Take the indicador from list_catalogo(fuente) and its valid campos from get_sut_indicador_schema.

## ARCOTEL (estadísticas del sector de telecomunicaciones: reportes mensuales y boletines anuales/temáticos)

- Id: `arcotel`
- Base: https://www.arcotel.gob.ec/

- `search_archivos`: File links from one institution's catalog, filtered by text: SRI, MEF, SENAE, Census 2022, MINEDEC, SENESCYT, MSP, CNIG, Trabajo, ARCOTEL and BCE (remesas, comex prices, latest publications). Links, not contents.

## Ministerio del Trabajo (salarios sectoriales y boletín estadístico anual)

- Id: `trabajo`
- Base: https://www.trabajo.gob.ec/

- `search_archivos`: File links from one institution's catalog, filtered by text: SRI, MEF, SENAE, Census 2022, MINEDEC, SENESCYT, MSP, CNIG, Trabajo, ARCOTEL and BCE (remesas, comex prices, latest publications). Links, not contents.

## IESS (boletines y documentos estadísticos, certificado de cumplimiento patronal)

- Id: `iess`
- Base: https://www.iess.gob.ec/

- `list_catalogo`: List one source's catalog, the step before its get tool: arconel (get_arconel_reporte), bce_diarios (get_bce_indicador_diario), contraloria (get_contraloria_informe), iess (get_iess_archivos), sut and judicatura (get_sut_indicador_schema, query_sut_indicador with the same fuente).
- `get_iess_archivos`: Documents in one IESS collection with direct links. anio is required for informes_auditoria.
- `get_certificado_cumplimiento_patronal`: Whether an employer (RUC) or person (cédula) is current on IESS contributions. A compliance check, not a headcount; for employees use get_financials' n_empleados.

## SEPS (estadísticas de la economía popular y solidaria)

- Id: `seps`
- Base: https://estadisticas.seps.gob.ec/

- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).

## MEF / SENAE (operaciones fiscales y tributos recaudados)

- Id: `mef`
- Base: https://www.economicoproductivo.gob.ec/

- `search_archivos`: File links from one institution's catalog, filtered by text: SRI, MEF, SENAE, Census 2022, MINEDEC, SENESCYT, MSP, CNIG, Trabajo, ARCOTEL and BCE (remesas, comex prices, latest publications). Links, not contents.

## SENESCYT / Educación Superior (estadísticas SIAU y Biblioteca)

- Id: `senescyt`
- Base: https://siau.senescyt.gob.ec/

- `search_archivos`: File links from one institution's catalog, filtered by text: SRI, MEF, SENAE, Census 2022, MINEDEC, SENESCYT, MSP, CNIG, Trabajo, ARCOTEL and BCE (remesas, comex prices, latest publications). Links, not contents.
- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).

## MINEDEC (matrícula escolar histórica, datos abiertos)

- Id: `minedec`
- Base: https://educacion.gob.ec/datos-abiertos-minedec/

- `search_archivos`: File links from one institution's catalog, filtered by text: SRI, MEF, SENAE, Census 2022, MINEDEC, SENESCYT, MSP, CNIG, Trabajo, ARCOTEL and BCE (remesas, comex prices, latest publications). Links, not contents.

## INEVAL (resultados de evaluaciones educativas)

- Id: `ineval`
- Base: https://evaluaciones.evaluacion.gob.ec/BI

- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).

## CNE (resultados y registro electoral por proceso, 2002-2025)

- Id: `cne`
- Base: https://www.cne.gob.ec/estadisticas/bases-de-datos/

- `list_archivo_secciones`: List the sections of one institution's document archive (ARCSA, Superbancos, SEPS, INEVAL, SGR, Educación Superior, SIPA, Petroecuador, Energy Ministry, CNE, BVG, BVQ, CENACE, ARCONEL). Next: get_archivo_seccion(fuente, seccion).
- `get_archivo_seccion`: List the downloadable files (title, URL, format) in one section from list_archivo_secciones. Returns links, not file contents; download large files directly (preview/download tools cap at 5 MB).

## infoMIES (bases mensuales y boletines zonales del MIES)

- Id: `infomies`
- Base: https://info.desarrollohumano.gob.ec/

- `search_infomies_bases_mensuales`: infoMIES monthly program databases, serie "anc" (economic inclusion) or "is" (social inclusion). Closed years have one year-end file. .rar files: links only.
- `search_infomies_boletines_zonales`: infoMIES zonal bulletins: modo="zonal" (per-zone .rar, 2017-2021, needs zona) or "consolidado" (yearly XLSX 2021-2026, still updated). Returns links.

## MSP (gacetas semanales de enfermedades inmunoprevenibles)

- Id: `msp`
- Base: https://www.salud.gob.ec/

- `search_archivos`: File links from one institution's catalog, filtered by text: SRI, MEF, SENAE, Census 2022, MINEDEC, SENESCYT, MSP, CNIG, Trabajo, ARCOTEL and BCE (remesas, comex prices, latest publications). Links, not contents.

## CNIG (estadísticas de violencia de género y femicidios)

- Id: `cnig`
- Base: https://www.igualdadgenero.gob.ec/violencia/

- `search_archivos`: File links from one institution's catalog, filtered by text: SRI, MEF, SENAE, Census 2022, MINEDEC, SENESCYT, MSP, CNIG, Trabajo, ARCOTEL and BCE (remesas, comex prices, latest publications). Links, not contents.

## CEPALSTAT (indicadores de CEPAL filtrados a Ecuador)

- Id: `cepalstat`
- Base: https://api-cepalstat.cepal.org/cepalstat/api/v1

- `search_cepalstat_indicadores`: Search CEPALSTAT's 2,059 regional indicators (demographic, economic, environmental, SDG). Next: get_cepalstat_indicador for Ecuador's values.
- `get_cepalstat_indicador`: Observations of one CEPALSTAT indicator for one country (Ecuador by default), with dimension ids decoded to labels. Take indicator_id from search_cepalstat_indicadores.

## Series internacionales con Ecuador: Banco Mundial WDI, IRENA, XM Colombia, UN Comtrade, FMI, OMS, OIT, ACNUR

- Id: `series_internacionales`
- Base: https://api.worldbank.org/v2

- `get_serie_internacional`: International series for Ecuador via `fuente`: wdi (World Bank), irena (electricity), xm (Colombia-Ecuador power flows), comtrade (UN bilateral trade), imf (IMF SDMX), who (health), ilo (ILOSTAT labour), unhcr (refugees/asylum). Without indicador/flow, wdi/who/imf/ilo list their catalog (set query).

## Utilidades transversales (búsqueda global, archivos, orientación)

- Id: `utilidades`

- `search_ecuador`: Unified first-step search across CKAN datasets, organizations, gob.ec trámites and regulations, SERCOP contracts and SGR risk events, a few hits per source. Drill down with the source-specific get_* tools; for CKAN datasets alone use search_datasets.
- `investigate_dataset`: One-step shortcut: search CKAN, pick the top dataset and preview its first readable resource. Use the individual tools when the top hit isn't the right one.
- `list_zip_contents`: List a remote ZIP's members (name, size) via HTTP Range requests, without downloading it; works for archives far beyond 5 MB. No ZIP64.
