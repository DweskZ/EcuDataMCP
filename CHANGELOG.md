# Changelog

## Unreleased

### Added

- **`get_tramite_estadisticas`** — monthly atenciones/quejas transparency
  series for one trámite (`gob.ec/api/v1/tramites-transparencia/{id}`),
  since mid-2021. No bulk endpoint; fetches one trámite's series at a time.

## 0.8.5 — 2026-08-31

### Added

- **BCEData revision observability** — catalog audits now report whether the
  API exposes an explicit revision marker (`revision`, `version`, `updated`,
  `modified`, `ETag`, or `Last-Modified`) and compare it when available;
  current live responses expose no such marker, so content comparison remains
  the available fallback.
- **Broader IEM reading and archive checks** — matrix-shaped tables and
  quarterly periods are normalized, and the audit script can opt in to bounded
  full-XLSX SHA-256 hashing without changing the default download behavior.
- **BCEData/IEM comparison** — `compare_bce_sources` produces cautious label-
  based candidate matches and source-only entries, clearly separating
  discovery from methodological equivalence.
- **Remote deployment safeguards** — per-client/IP rate limits, required
  Bearer authentication, direct Uvicorn TLS configuration, and deployment
  guidance are now available through environment variables and
  `docs/DEPLOYMENT.md`.

### Changed

- Project positioning now consistently describes EcuDataMCP as open
  public-data infrastructure for Ecuador, and the README keeps the detailed
  tool reference in `docs/TOOLS.md`.

### Added

- **BCEData value audit and IEM period normalization** — `audit_bce_catalog`
  can optionally probe one current `/grid` period for every advertised
  frequency/unit pair and persist that bounded report separately. IEM table
  readers now filter annual, numeric month/year, and Spanish month labels,
  including tables without an explicit unit block.
- **BCEData audit snapshots** — `audit_bce_catalog` can now persist every
  audit attempt, preserve the last complete catalog when a request fails, and
  compare groups, metadata, and series changes with the previous valid
  snapshot. `scripts/audit_bce_catalog.py` provides the same flow for a
  scheduler or operator.
- **More complete IEM discovery** — bulletin discovery reconciles the long
  historical index with the latest-publications page, reports detected archive
  gaps, catalogs complete PDF/ZIP downloads, and returns an SHA-256 hash when
  an individual XLSX table is read.
- **SRI Saiku read-only tools** — discover public cubes, inspect cube metadata,
  and run bounded one-dimension/one-measure aggregates without arbitrary MDX,
  drill-through, exports, or writes. Live SRI connectivity remains an
  environment-dependent verification step.

- **`investigate_dataset`** — one-shot research shortcut chaining
  `search_datasets` → `list_dataset_resources` → `preview_resource_data`
  into a single call: search a query, take the top-ranked dataset, and
  preview the first resource in a format this server can actually parse
  (skipping `.rar`/unrecognized ones instead of blindly previewing
  whatever is listed first). Flags when the dataset looks like it
  publishes a periodic series (reusing `list_dataset_resources`'s
  `detect_periodic_series`) and points at `detect_series_pattern` instead
  of re-implementing that heuristic.
- **Smoke test coverage widened from 13 to ~39 of 68 tools**
  (`scripts/smoke_e2e.py`), plus 3 new end-to-end chains (list → get) for
  the trickiest integrations — SUT Power BI, Superbancos OneDrive, and
  IG-EPN informes — that discover a real live ID first instead of
  hardcoding one that could go stale. Fixed a real pre-existing bug found
  in the process: any non-ASCII character (routine in this project's
  output — accents, →, ⚠) in a failure message crashed the whole script
  on Windows (`cp1252` console encoding), silently hiding every check
  after the one that happened to fail first.
- **`.github/workflows/smoke.yml`** — runs the smoke test daily against a
  freshly started server (separate from `ci.yml`, which only runs mocked
  unit tests on every push). A failure here means a live government site
  changed/broke, not that a code change is bad; GitHub emails the repo's
  watchers by default on a failed scheduled run, so no extra alerting
  setup was needed.

- **`search_informes_igepn`/`get_informe_igepn`** — the IG-EPN PDF report
  archive (`https://www.igepn.edu.ec/servicios/busqueda-informes`, backed
  by a separate JSF/PrimeFaces app at `informes.igepn.edu.ec`), distinct
  from `search_sismos` (raw earthquake catalog feed): daily/weekly/special
  seismic bulletins, volcanic "IG Al Instante" alerts, annual/field
  reports. Unlike every other integration in this project, IG-EPN has no
  stable per-document URL — each report only downloads via a session-bound
  PrimeFaces AJAX flow (GET for a `javax.faces.ViewState` token tied to the
  session cookie, an AJAX POST of the "Buscar" button that re-renders the
  result list with a fresh ViewState, then a plain POST of that row's own
  "Descargar Informe" submit button reusing the same session). Confirmed
  live end-to-end, including a real PDF download and text extraction.
  `helpers/pdf_reader.py` gained `extract_text_from_bytes()`, splitting the
  page-extraction logic out of `read_pdf()` so `get_informe_igepn` reuses
  it instead of duplicating pypdf handling for a byte stream that (unlike
  every other PDF this project reads) never had a URL to begin with.
  Two of the site's own filters ("Tipo de informe", "Volcán") were
  confirmed live to not narrow results server-side even replaying a real
  browser's exact AJAX payload byte-for-byte — only "Tipo"
  (Sísmico/Volcánico) and "Año" do. `search_informes_igepn` only sends
  those two and does the rest of the filtering client-side against the
  newest page of results (same recency-biased, non-exhaustive approach
  `search_sismos` already uses), and documents the limitation in its own
  response rather than silently under-filtering.

- **`list_bce_indicadores_diarios`/`get_bce_indicador_diario`** —
  BCE's family of daily/monthly "indicador" widgets living outside both
  BCEData and IEM (`helpers/bce_indicadores_diarios_client.py`). Built to
  cover Riesgo País (EMBI) specifically — BCEData only had it as a
  monthly end-of-period aggregate, for something BCE republishes daily.
  9 plain JSON files behind Highcharts widgets on `contenido.bce.fin.ec`,
  no auth: 29 series total, several genuinely daily back decades (Riesgo
  País since 2004, Precio del Oro since 1999, Petróleo WTI, Dow Jones,
  SOFR/LIBOR, Ecuador sovereign bonds 2030/2034/2035/2039/2040,
  Producción Petrolera Nacional since 2018), plus monthly/annual series
  (sistemas de pago interbancarios, inflación, desempleo, PIB) that
  likely duplicate BCEData but come from one clean file. The catalog is
  discovered live from each file's own rows rather than hardcoded — a
  "código" only means one thing within its own file, confirmed by two
  sovereign-bond series (2034, 2039) turning up that weren't in the
  original investigation. `get_indicador_diario` never returns a full
  series (Riesgo País alone is 7,369+ rows) — only a bounded window
  (most recent N or an explicit date range, capped at 366) plus the
  series' true full range as metadata. One file (`datos_ipc.json`,
  Inflación) doesn't have a "Valor" field at all -- three parallel series
  ("Mensual"/"Anual"/"Acumulada" instead, confirmed against the
  indicator's own widget, which charts all three) -- caught before this
  shipped by re-inspecting every file's actual fields rather than
  trusting the 8-file pattern to hold universally; a naive `row["Valor"]`
  would have silently returned `None` for every inflation observation.
  `get_indicador_diario` now returns `{"fecha", "valor"}` for the common
  single-value case and `{"fecha", "valores": {...}}` when a file has no
  single value field.
- **`list_sut_indicadores`/`get_sut_indicador_schema`/`query_sut_indicador`** —
  Ministerio del Trabajo/SUT's public Power BI "Indicadores" dashboards
  (`helpers/sut_powerbi_client.py`). These are live semantic models, not
  static files: `public/reports/{resource_key}/modelsAndExploration`
  (public, no session — the resource_key comes straight from the
  dashboard's own embed URL) returns each report's full field catalog by
  reading every visual's own query definition, and
  `public/reports/querydata` runs an arbitrary query against the model —
  any combination of fields, not just what one chart already shows. Proved
  this by pulling a genuine monthly contracts-by-industry panel back to
  2015 (`contratos` dashboard) that has no equivalent anywhere in CKAN
  (whose one resource for this topic is a single current-snapshot count,
  no time dimension). The response format (Power BI's "DSR" delta
  encoding — a repeat/null bitmask per row referencing a per-column value
  dictionary) was reverse-engineered and validated against a number read
  directly off the live dashboard (enero 2015 = 92,306) before being
  trusted. Same mechanism generalizes to all 8 known dashboards without
  per-dashboard code — 6 of 8 exposed a full field catalog automatically;
  the last 2 (`denuncias_publico`, `encuentra_empleo`) use an older report
  layout with no visual config exposed via `modelsAndExploration` at all,
  so their fields were recovered by driving each dashboard in a browser
  and capturing the queries it actually sent, then merged in as a small
  manual override (`_MANUAL_CAMPOS`). That pass also surfaced a field kind
  not seen elsewhere in SUT: a plain column aggregated with `SUM()` at
  query time (`encuentra_empleo`'s "Número de Personas") rather than a
  pre-built DAX measure, now supported as `kind="aggregated_sum"`. All 8
  dashboards are fully covered.
- **`list_superbancos_secciones`/`get_superbancos_seccion_archivos`** —
  Superintendencia de Bancos' statistics portal (`helpers/superbancos_client.py`),
  which has no CKAN organization. Four sections: Boletines Financieros
  Mensuales, Servicios Financieros (tarjetas/oficinas/cajeros/corresponsales),
  Información Histórica (comportamiento financiero anual banca pública/CFN/
  BanEcuador/Banco de Desarrollo + Reporte de Estabilidad Financiera), and
  Calendario Estadístico — 148 archivos found live across the four. A generic
  TablePress-table parser handles two header styles (`<thead><th colspan>`
  and a plain `<td colspan>` row with no `<thead>` at all) and separates a
  row's "Año NNNN" label from its linked months when the table splits them
  into different cells. Every parsed link is checked against the
  `superbancos.gob.ec` domain before being surfaced — caught and dropped a
  real mistyped link on the live Servicios Financieros page
  (`httpas://w-group.tech/...` instead of the real host). Added
  `superbancos.gob.ec` to `helpers/tls.py`'s OS-trust-store host list (same
  missing-intermediate-CA failure mode already handled for
  `censoecuador.gob.ec` — full verification, just a different CA bundle).
  **`boletines_financieros`'s OneDrive widget reverse-engineered.** Each
  section page also embeds a client-side "WP Cloud Plugin — Share-one-Drive"
  widget that lazy-loads recent years from a OneDrive folder. Its AJAX
  protocol was captured live (POST `wp-admin/admin-ajax.php`,
  `action=shareonedrive-get-filelist`, with `listtoken`/`account_id`/
  `drive_id`/`_ajax_nonce` all present in the page's own static HTML — no
  session or cookies needed) and its download URLs turned out to be a
  stable same-site proxy, not short-lived Graph tokens as first assumed.
  `boletines_financieros` now returns 224 archivos, 1997-2026, merging the
  static "OTROS AÑOS" table with every OneDrive year folder found live.
  `servicios_financieros`'s three OneDrive widgets (distinct token each)
  are now wired up too: a generalized crawler (`_wpcp_crawl_tree`) walks a
  tree of arbitrary depth instead of assuming boletines' flat "Año NNNN"
  folders — the root call returns the whole tree with parent pointers in
  one response, confirmed live, so no extra round trip is needed to learn
  the structure, only to list each folder's files (~40 requests total,
  run concurrently). One widget turned out to be the "Estadísticas
  Generales" consolidation (9 categories organized by year); another is
  "Resoluciones de Servicios Financieros, Tarjetas y Canales", closing a
  long-standing roadmap item ("Resoluciones y Circulares, AJAX-blocked").
  Along the way, a regex anchored to one file-preview-link class variant
  was silently dropping ~35% of real entries (most of this section's
  files are XLSX, previewable, and use a different class than the ZIPs
  boletines is mostly made of) — caught by the warning-to-result ratio
  looking wrong, not by an exception. Fixed by targeting a different,
  type-invariant anchor (the dedicated download button) instead of
  chasing every preview-class variant. `servicios_financieros` now
  returns 312 archivos, up from ~68 static-only.
- **`list_zip_contents`** — lists a .zip archive's members (name, size,
  compression) from a direct URL via HTTP Range requests, without
  downloading the archive. Reads only the End Of Central Directory record
  and the central directory itself (`helpers/csv_reader.list_zip_contents`,
  `_fetch_range`), both tiny relative to the archive regardless of its
  total size — works for INEC/censo-style multi-hundred-MB ZIPs that
  MAX_DOWNLOAD_BYTES would otherwise truncate outright. Requires the host to
  honor Range requests (HTTP 206); fails with an explicit message otherwise.
  Does not support ZIP64. Reuses `download_bytes`'s TLS-retry ladder
  (OS-trust-store, then insecure) since this hits the same portal hosts.
  Listing names this way is cheap; previewing a member's *rows* still needs
  a full download (`preview_zip`) — noted explicitly in both docstrings so
  it isn't mistaken for a general large-file preview solution.
- **Contraloría — "Plan Anual de Control"** added to the existing
  `list_contraloria_informes`/`get_contraloria_informe` tools
  (`helpers/contraloria_client.py`), reusing the same
  `WFDescarga.aspx?id={id}&tipo={tipo}&op=d` pattern already implemented
  for "Datos Abiertos" (`tipo=pesdoc`) with a second seed page
  (`Portal/Sistema/PlanAnualControl`, `tipo=doc`). Unlike the quarterly CSV
  exports, these are one PDF per year (the approved annual control plan) —
  `get_contraloria_informe` now detects the non-CSV `tipo` and returns
  metadata plus a `read_pdf` pointer instead of attempting `preview_csv`.
- **`search_sri_estadisticas_recaudacion`** — SRI's "Estadísticas de
  Recaudación" page (`helpers/sri_client.py`), a real gap beyond the
  existing `/datasets` scraper: monthly XLSX reports pre-aggregated by
  impuesto/provincia/cantón and by actividad económica (a different
  aggregation level than `/datasets`' raw yearly exports, not a duplicate),
  plus a historical-indicators ZIP, an annual PDF boletín técnico, and
  infografías. The page's links live in a Liferay "Biblioteca Alfresco"
  document library with generic anchor text ("Ver estadísticas de
  recaudación"), so labels are derived from the URL's filename instead —
  which already carries the real report name and month/year.
- **`search_bce_remesas`** — BCE's dedicated Remesas de Trabajadores
  (worker remittances) page (`helpers/bce_remesas_client.py`), separate
  from BCEData/IEM: the aggregate flow series, the full historical series,
  a methodology user note, and — since a July 2025 change to microdata-based
  collection — monthly aggregate and entity-level databases (BDD). The tool
  docstring flags explicitly that "histórica" (pre-change) and "BDD"
  (post-change) files are methodologically distinct series, per the page's
  own comparability note, rather than one continuous one.
- **`get_cenace_tablero`** — CENACE's live grid-operations snapshot
  (`helpers/cenace_client.py`), Ecuador's national electricity operator:
  generation mix and demand, no CKAN organization equivalent exists.
  Confirmed live in-browser (network tab empty across all 5 tab switches)
  that the whole page is server-rendered in one load with no AJAX behind
  it — 5 fixed tableros (produccion_tiempo_real, demanda_tiempo_real,
  operativa_diaria, acumulada_mensual, acumulada_anual), each an as-of-now
  snapshot (this instant/yesterday/month-to-date/year-to-date) with no
  date picker and no historical series behind any of them. Parses the 6
  headline resumen numbers per tablero plus, for demanda_tiempo_real, a
  19-distributor MW breakdown read from the SVG map's `<title>` tags
  (simpler than decoding the equivalent Plotly bar chart's base64-packed
  float64 array). Per-plant/fuel-type detail and the 24h generation curve
  are deliberately not scraped — both live only inside `Plotly.newPlot`
  blobs wrapped in a large shared theme template, and the resumen numbers
  already cover the dashboard's real value. `www.cenace.gob.ec` needed the
  same OS-trust-store TLS fallback as `censoecuador.gob.ec`/
  `superbancos.gob.ec` (missing intermediate CA in certifi, not a broken
  cert). Short (180s) cache TTL since the tiempo-real tablero changes
  continuously.

- **`get_sri_ruc_info`/`search_sri_ruc`** — SRI's public Registro Único de
  Contribuyentes lookup (`helpers/sri_ruc_client.py`). `get_sri_ruc_info`
  covers the exact-RUC case (registry record + registered establishments,
  scraped from the legacy `/facturacion-internet/consultas/publico/`
  pages — no auth, no CAPTCHA). `search_sri_ruc` adds the "I know the
  company name, not its RUC" case, using a separate and more modern
  unauthenticated JSON REST API
  (`sri-catastro-sujeto-servicio-internet/rest/ConsolidadoContribuyente`)
  found by driving srienlinea.sri.gob.ec's current Angular RUC app in a
  browser and watching its network calls — the *legacy* name-search form
  (`ruc_consulta.jsp`) is CAPTCHA-gated (a visualcaptcha widget) and was
  deliberately left alone; the modern flow has no CAPTCHA at all,
  confirmed with a bare `curl`. Three chained calls
  (`cantidadObtenidaPorRazonSocial` → `numerosRucPorRazonSocialToken` →
  `obtenerPorNumerosRuc`, the last batching a whole page of RUCs into one
  request) also return richer fields than the HTML scrape — régimen,
  representantes legales, agente de retención, contribuyente
  especial/fantasma/con transacciones inexistentes. The SRI caps matches
  at 100 server-side (confirmed live with both "BANCO" and "SA"); a
  `total_reportado` of 100 is flagged as "at least 100, not necessarily
  exactly 100" rather than presented as an exact count. Both tools state
  explicitly that this is a registry lookup, not a way to retrieve an
  individual's tax returns, sales, withholdings, or payments.

### Fixed

- **Locked CI installation** — synchronized the editable package version in
  `uv.lock` with the release version so `uv sync --locked` can install the
  project in GitHub Actions.

## 0.8.3 — 2026-08-30

### Added

- **`search_censo_recursos`** — INEC's dedicated Census 2022 microsite
  (censoecuador.gob.ec): full microdata at sector/cantón/city-block level
  in CSV/SPSS/REDATAM, plus the 2010 and 2001 censuses recoded onto 2022
  geography. Metadata and direct URLs only, same pattern as SIPA/Supercías
  financials — these are multi-hundred-MB archives. Needed two new,
  reusable host-quirk fixes rather than anything ad hoc in the client:
  `helpers/tls.py` gained a third TLS-retry tier
  (`should_retry_with_os_trust`/`os_trust_context`) for hosts whose cert
  chain verifies against the OS trust store but not httpx's bundled
  certifi CAs — unlike the existing insecure-retry fallback, this keeps
  full certificate verification on; and `download_bytes` gained an opt-in
  `raise_for_status=False` for a confirmed WordPress/Elementor bug where
  one page serves real content under an HTTP 404.
- The Geografia Estadistica geoportal (INEC's official yearly DPA
  classifier, 2001-2026) is now discoverable via the existing
  `search_inec_estadisticas`/`get_inec_estadistica_files` — no new client
  needed, just added to a small curated list of pages unreachable from
  either seed page's menu. Fixed a real regex bug in the process:
  `_FILE_LINK_RE` required a single slash after `.ec`, missing every real
  link on the site that has a doubled slash (`.ec//documentos/...`) —
  went from 19 to 115 files found on that one page alone, and the fix
  applies to every topic page, not just this one.
- **`search_inec_publicaciones`/`get_inec_publicacion_archivos`** —
  INEC/Ecuador en Cifras' publications, discovered via the site's public
  WordPress REST API (`/wp-json/wp/v2/posts`) instead of HTML scraping.
  Started from a report that ANDA lacked ENEMDU 2025; traced through ANDA,
  CKAN, and INEC's own "Empleo" topic page all capping around 2021-2023,
  then found the real cause: `search_inec_estadisticas`'s topic list is
  scraped from one seed page's nav menu, and the site's menu isn't the same
  on every page — `enemdu-anual/`/`enemdu-trimestral/` (which had the full
  2025 annual dataset the whole time) live in a submenu that page never
  exposes. The REST API sidesteps the whole problem: 1,707 posts, real
  full-text search (confirmed matching body content, not just titles),
  honest pagination via `X-WP-Total`, newest post within days of being
  checked. `/institucional/noticias/` and `/institucional/boletines/`
  turned out to be category-filtered views of this same collection, not a
  separate source — no HTML scraper needed for discovery at all. Verified
  end-to-end through the actual registered MCP tool, not just the client
  layer: `get_inec_publicacion_archivos` on the ENEMDU anual page returns
  the real 2025 dataset (11 files: BDD SPSS/CSV, boletín técnico,
  tabulados). See RESEARCH.md § Novena pasada.
- `search_inec_estadisticas`'s topic-page discovery now merges two seed
  pages instead of one, and also picks up dropdown submenu items (a
  different HTML shape than the top-level mega-menu links it already
  parsed) — topic count went from 74 to 89, including the ENEMDU pages
  above. Reduces the single-seed-page gap; doesn't eliminate it, which is
  why the REST API layer above exists as the authoritative fallback.

### Fixed

- **`helpers/data/{cantones,parroquias}.json` had real drift against INEC's
  official Clasificador Geográfico Estadístico**, found while integrating
  it above. La Concordia was coded as cantón `0808` of Esmeraldas; the
  official 2026 classifier has it as `2302` of Santo Domingo de los
  Tsáchilas (an already-resolved provincial reassignment our data hadn't
  picked up). Cantón `1413` Sevilla Don Bosco (Morona Santiago) was
  missing entirely — created 2024-11-05, Ecuador's newest cantón; it
  previously existed in our data only as a parroquia of Morona, which the
  official classifier no longer lists. Both corrected, including the
  affected parroquia records. `lookup_ubicacion` now returns the current,
  correct province/cantón assignments for both.
- **Follow-up on the "zona en disputa" cantones** flagged above but left
  unresolved: added cantón `9006` Juval (Cañar-Chimborazo, a genuinely
  active disputed zone with its own official code since a 2017 decree).
  After individually researching each mismatch, deliberately did *not*
  touch the other three: the official classifier's `9009` "Morona" row
  looks like a data-entry error in INEC's own spreadsheet (labeled
  province "MORONA SANTIAGO" despite its 90 code, no parroquias under it,
  and "Morona" already exists as a real, separate cantón); Las Golondrinas
  was resolved to Cantón Cotacachi/Imbabura by a 2026 popular vote, but
  INEC's own classifier hasn't assigned it a parroquia code yet, so there
  was nothing correct to substitute; Manga del Cura and El Piedrero remain
  genuinely disputed/unresolved as of 2024 sources -- their absence from
  the classifier reflects never having gotten a formal cantón code, not a
  resolved dispute. A newer "official" source doesn't always mean an
  existing data point is wrong.
- **`get_organization`/`get_organization_info` silently truncated large
  organizations' dataset lists.** `organization_show?include_datasets=true`
  caps its own `packages` field at the portal's per-page default —
  confirmed live returning only 10 of 94 real datasets for
  `instituto-nacional-de-estadisticas-y-censos`, with the tool printing a
  self-contradictory "Total de datasets: 94" next to "Datasets publicados
  (10)". Now fetches the true package list via
  `package_search?fq=organization:{id}` instead; verified live returning
  94/94. Found during the ENEMDU investigation above.

## 0.8.2 — 2026-08-29

### Added

- **SIPA (Sistema de Información Pública Agropecuaria) integration** —
  `list_sipa_modulos`/`get_sipa_modulo_archivos` (`helpers/sipa_client.py`).
  Ministry of Agriculture, Livestock and Fisheries statistics portal,
  distinct from MPCEIP: 30 real Excel files across four modules (económico,
  productivo, social, censos y registros administrativos) — prices, trade,
  credit, production, and census series back to the early 2000s. Replaces
  the old cacao/MPCEIP-only coverage `detect_series_pattern` relied on.
  Tools return metadata + direct URL only, never the file bytes (some
  exceed 41 MB, well over the 5 MB download/preview cap).
- **Contraloría General del Estado integration** —
  `list_contraloria_informes`/`get_contraloria_informe`
  (`helpers/contraloria_client.py`). Quarterly CSV exports of audit reports
  approved for any public institution in the country, scraped live from
  `contraloria.gob.ec/Portal/24287` (id/tipo pairs aren't hardcoded — a new
  quarter is published roughly every 3 months). Reuses
  `helpers/csv_reader.preview_csv` for the actual download+parse.
- **BCE IEM (Información Estadística Mensual) integration** —
  `search_bce_iem`/`get_bce_iem_table` (`helpers/bce_iem_client.py`). Indexes
  the BCE's monthly bulletin live: current-bulletin table search, plus
  `historico=true`/`desde_anio`/`hasta_anio` to merge table versions across
  bulletins. `get_bce_iem_table` returns structured, date-filterable series
  for the common wide (periods-across-columns) and long (one-row-per-period)
  table layouts, falling back to a layout-preserving raw preview otherwise
  rather than guessing columns.
- **`audit_bce_catalog`** (`helpers/bce_client.py`, `tools/audit_bce_catalog.py`)
  — reports live coverage of the BCEData catalog: tree nodes, leaf groups,
  per-group bundle fetch success/failure, series discovered per section.
  Verified live: 78/78 leaf groups fetch successfully today (2,360 series
  across the 4 BCEData sections) — see the caveat in ROADMAP.md that this
  covers BCEData's own catalog, not the Central Bank's full publication set
  (IEM alone is documented as richer than all of BCEData combined).

### Fixed

- **CSV delimiter sniffing picked the wrong delimiter on comma-heavy prose
  fields.** `helpers/csv_reader.py`'s `_parse_csv_bytes` guessed the
  delimiter by counting raw character occurrences across a 2000-char
  sample — found for real against Contraloría's audit-report CSVs, whose
  free-text `Diligencia` column (Spanish prose full of commas) made `,`
  narrowly outnumber the file's actual `;` delimiter in a 5-row sample (30
  vs 29), splitting every row into one unparsed field instead of 9 real
  columns. Replaced with `csv.Sniffer` (weighs consistency across rows,
  not raw counts), falling back to counting within just the header line
  when Sniffer can't decide. Affects `preview_csv`/`preview_resource_data`
  generally, not just Contraloría.
- **26 correctness bugs from an adversarial review of the BCE IEM/audit
  work above and a full-repo pass**, including: a global lock that
  serialized "concurrent" IEM bulletin downloads; an unbounded
  `historico=true` fetch with no year range; audit-only metadata leaking
  into `search_indicadores` results; a wide-format table raising instead
  of falling back on a date-range miss; a unit-header misclassification
  when a series has no data in the requested range; case-sensitive
  `frecuencia`/`unidad` matching; a case-sensitive Bearer-auth scheme
  check; unescaped CSV headers interpolated into `CREATE TABLE` DDL in the
  Supercías financials build script; the 20MB gzip-decompression cap only
  being checked between chunks instead of within one `zlib` call;
  `search_ranking` having no descending-sort option; short (<2 char)
  queries silently bypassing filtering in `search_anda`/`search_tramites`;
  unclamped `page_size`/`limit` in `search_datasets`/`search_anda`; and
  several smaller issues (see git log for the full list). Full test suite
  (276 tests) and lint pass.
- **`bce_iem_client` tests rewritten to mock via `pytest-httpx`** instead of
  monkeypatching `download_bytes` directly, matching every other client's
  test convention.

## 0.8.1 — 2026-08-29

### Security

- **`inec_client.py` now goes through the shared SSRF guard.** Its two page
  fetches used a raw `httpx.AsyncClient().get()` with `follow_redirects=True`
  and no per-hop validation — harmless for the hardcoded seed-page constant,
  but `get_topic_files(topic_url)` takes a URL that ultimately traces back to
  the calling model (via `search_topics`'s scraped results), which is exactly
  the class of input `helpers/safe_download.py`'s `assert_public_url`/
  `safe_stream` guard exists for (blocks non-http(s) schemes, private/
  loopback/link-local IPs, and unvalidated redirect hops). Switched both
  fetches to `helpers.csv_reader.download_bytes`, which already wraps that
  guard (and the shared TLS-fallback retry) — removed ~15 lines of duplicate
  TLS-retry logic in the process. Verified live: real INEC pages still
  fetch correctly, and a crafted `169.254.169.254`/`localhost` URL is now
  rejected before any request leaves the process.

### Changed

- **Consolidated 13 copy-pasted accent-stripping functions into
  `helpers/text_utils.strip_accents`.** Every one of `bce_client`,
  `biinec_extras`, `geo_data`, `gobec_client` (a nested local def inside
  `find_regulaciones`), `igepn_client`, `inec_client`, `sgr_client`,
  `sri_client`, `supercias_client`, `search_anda`, `search_ecuador`,
  `search_tramites`, and `detect_series_pattern` had their own inline
  NFKD-normalize implementation — three subtly different variants (some
  lowercase, some not; `search_tramites`'s lacked the `text or ""` guard the
  others have, so it would crash on `None`). One shared function now, with a
  `lower` kwarg for the two behaviors; existing call sites unchanged via
  `from helpers.text_utils import strip_accents as _strip_accents` (or
  `functools.partial(strip_accents, lower=False)` where case was preserved).
- **Non-root Docker user.** The image ran as root with no `USER` directive;
  added a dedicated `appuser` and switched to it after `uv sync`. Caught a
  real regression while doing this: `docker-compose.yml` mounts a named
  volume at `/app/data` (used by `scripts/build_supercias_financials_db.py`
  via `docker compose exec`), which doesn't exist in the image at build
  time — a fresh named volume takes its initial ownership from whatever's
  already at that path in the image, so without `mkdir -p /app/data &&
  chown` *before* dropping to `appuser`, that volume would come up
  root-owned and the build script would fail to write to it as a non-root
  user on first run.
- **Dependabot enabled** (`.github/dependabot.yml`): weekly PRs for `uv`
  (pyproject.toml/uv.lock), GitHub Actions, and the Dockerfile's base image.
  Previously a `pypdf`/`httpx`/`uvicorn`/`mcp` CVE had no automated path to
  surface — CI runs tests on push but nothing flagged an outdated or
  vulnerable pin.

## 0.8.0 — 2026-08-29

### Added
- **Nuevo tool `search_biinec_extras`** (`helpers/biinec_extras.py` +
  `helpers/data/biinec_extras.json`): la versión "targeted" de BIINEC que sí
  se justificaba construir. En vez de automatizar el flujo JSF completo
  (5 postbacks con ViewState por archivo, sin URLs estáticas — ver análisis
  de costo/beneficio abajo), es una lista pequeña y verificada a mano de los
  3 registros confirmados como exclusivos de BIINEC (módulo de desechos
  peligrosos en establecimientos de salud, módulos ambientales de
  ENEMDU/ECV). Si la búsqueda no encuentra nada en esa lista, el tool lo dice
  explícitamente y no lo confunde con "BIINEC no tiene el dato" — instruye
  buscar directamente en el sitio. Mismo patrón que `lookup_ubicacion` /
  `helpers/geo_data.py` (referencia offline, sin llamada HTTP). `buscar_inec`
  actualizado para llamar a este tool en su paso 3 en vez de solo mencionar
  BIINEC en prosa.
- **Nuevo prompt `buscar_inec`** (`prompts/workflows.py`): guía al agente para
  recorrer las tres fuentes del INEC en el orden correcto — ANDA primero (el
  catálogo más amplio, y te dice si una operación es "solo agregados"),
  Ecuador en Cifras segundo (donde vive el archivo real para ese caso), y
  BIINEC solo como mención manual de último recurso (sin tool propio, cubre
  un puñado de registros ambientales exclusivos). `search_anda` ahora
  también referencia `search_inec_estadisticas` directamente en su docstring
  para el caso "solo agregados", sin depender de que se invoque el prompt.
- **Nueva fuente: Ecuador en Cifras / INEC** (`helpers/inec_client.py` +
  `search_inec_estadisticas` / `get_inec_estadistica_files`). Cubre las ~75
  páginas de tema de `ecuadorencifras.gob.ec` (IPC, ENEMDU, ENSANUT,
  pobreza, comercio exterior, censos...): boletín técnico, metodología y
  series históricas completas en PDF/XLSX/CSV/ZIP, todo con links planos
  sin JS. Complementa (no duplica) a `search_anda`: ANDA cataloga estas
  mismas operaciones con metadata pero sin microdatos para el tipo
  índice/agregado (el IPC, por ejemplo, aparece en ANDA como "solo
  agregados" sin nada descargable) — este es el tool que sí tiene el
  contenido real para ese caso. El listado de temas se obtiene del menú de
  navegación embebido en cualquier página de tema (`mega-menu-link`); el
  dominio raíz (`/`) y `/estadisticas/` no sirven como fuente — el primero
  es un shell de redirección cacheado desde 2021, el segundo una vista
  Liferay vieja no relacionada. **Verificado en vivo:** búsqueda por
  "precios" y descarga de la página del IPC, con boletín técnico de julio
  2026 y tabulados históricos en CSV/Excel reales. Ver RESEARCH.md §
  Ecuador en Cifras. BIINEC (`aplicaciones3.../BIINEC-war`), la otra app
  del INEC investigada en paralelo, se descartó como fuente separada por
  solaparse con ANDA en microdatos y requerir sesión JSF más cara de
  scrapear.
- **Nuevo tool `read_pdf(url, pages)`**: extrae texto de un PDF en una URL
  directa, vía `pypdf` (pura Python). `pages` acepta un rango 1-indexado
  ("3", "1-5", "1,4,9"); vacío significa todo el documento, tope de 20
  páginas por llamada en ambos casos (llamar de nuevo con otro rango para el
  resto). Sin OCR: un PDF escaneado sin capa de texto vuelve vacío, con un
  mensaje explícito en vez de fallar en silencio. Maneja PDFs corruptos,
  protegidos con contraseña vacía (los descifra igual que la mayoría de
  visores) y con contraseña real (error explícito, no se puede leer sin
  ella). Descubre/desbloquea PDFs ya alcanzables desde otros tools —
  `get_regulacion_info` siempre linkeó al PDF del Registro Oficial sin que
  nada pudiera leerlo. **Verificado en vivo contra dos fuentes reales:**
  un reglamento de `get_regulacion_info` (77 páginas, Registro Oficial) y
  un boletín estadístico del IESS (142 páginas, `iess.gob.ec/es/estadisticas`
  — antes marcado como "sin confirmar" en el roadmap porque los links a
  PDF no aparecían en el HTML plano; resultaron estar detrás de una vista
  Liferay `document_library_display`, el PDF real vive en
  `iess.gob.ec/documents/...`). Ambos con texto genuinamente extraíble y
  bien por encima del tope de 20 páginas, confirmando que el parámetro
  `pages` es necesario, no especulativo. **Corregido 2026-08-28,**
  investigando más PDFs reales de IESS: un PDF real de 14.6 MB (estudio
  actuarial 2020, ver ROADMAP) expuso que una descarga truncada al tope de
  5 MB daba un mensaje engañoso ("está corrupto") en vez de explicar que
  se cortó a la mitad — un PDF, como un `.zip`, tiene su tabla de
  referencias al final del archivo, así que no hay lectura parcial
  posible. `read_pdf` ahora detecta la descarga truncada antes de
  intentar parsear y da un mensaje accionable, mismo patrón ya usado para
  `.zip`/`.tar.gz` truncados.
- **Soporte `.ods` (OpenDocument Spreadsheet)** en `preview_resource_data`:
  nueva `helpers/csv_reader.preview_ods` (vía `odfpy`, pura Python, sin
  dependencia externa), mismo patrón que `preview_xls`/`preview_xlsx`.
  Descarta el padding de columnas/filas vacías repetidas que ODS usa para
  rellenar la grilla fija de la hoja (`numbercolumnsrepeated`/
  `numberrowsrepeated`, a veces con conteos de 1000+), en vez de mostrarlas
  como columnas vacías o filas de datos en blanco. Verificado en vivo contra
  un recurso real de Cuenca en Datos
  (`gadcuenca_actas_pm_2026julio.ods`, actas del Concejo Cantonal): headers y
  filas correctos, incluyendo tildes (confirmado a nivel de code point — lo
  que se ve como `�` en la consola de Windows es el mismo falso positivo ya
  documentado para `.xls`, no un bug de decodificación real). Cierra el gap
  que dejó pendiente la integración de Cuenca en Datos.
- **Integración de Cuenca en Datos** (`cuencaendatos.cuenca.gob.ec`), el
  portal municipal CKAN de Cuenca (92 datasets, verificado en vivo).
  Mismo shape de API que el portal nacional, así que en vez de un cliente y
  tools nuevos y paralelos, los ~10 tools CKAN genéricos (`search_datasets`,
  `list_recent_datasets`, `get_dataset_info`, `list_dataset_resources`,
  `get_resource_info`, `preview_resource_data`, `download_resource`,
  `query_resource_data`, `search_organizations`, `get_organization_info`,
  `list_categories`, `get_category_info`, `detect_series_pattern`) ganaron
  un parámetro `source="nacional"|"cuenca"`. `helpers/ckan_client.py`
  resuelve la URL base según `source` (`_ckan_url`/`site_url` nuevos), con
  caché de categorías separada por fuente para no mezclar ambos portales.
  Nuevas variables de entorno opcionales `CUENCA_API_URL`/`CUENCA_SITE_URL`.
  Verificado en vivo end-to-end (search, categorías, organizaciones,
  metadata de dataset/recurso, y preview de un CSV real). Varios recursos
  de Cuenca son `.ods` — ver soporte `.ods` más abajo.
- **Nuevo tool `detect_series_pattern`**: dado un dataset con un grupo de
  recursos de nombre periódico (el mismo que ya detecta
  `list_dataset_resources` como `possible_periodic_series`), descarga los
  dos recursos más recientes, ubica una columna de fecha/período por nombre
  de encabezado, y clasifica el par como `acumulado` (el archivo nuevo
  incluye los períodos del viejo), `incremental` (períodos disjuntos, hay
  que combinar todos los archivos) o `indeterminado` (sin columna de
  período reconocible o solapamiento ambiguo) según cuánto se solapan sus
  valores de período. `tools/list_dataset_resources._detect_periodic_series`
  se volvió pública (`detect_periodic_series`) para poder reutilizarse
  desde este tool.

### Fixed
- **Dos bugs reales encontrados verificando `detect_series_pattern` contra
  `base-de-datos-seguro-desempleo` (IESS) en el portal real**, no solo con
  datos sintéticos:
  1. Varios CSV de IESS traen 1-3 filas de título/banner antes del
     encabezado real (`preview_csv` siempre asume que la fila 0 es el
     encabezado), así que la columna de período quedaba invisible. Nueva
     función `_locate_header_row` escanea las primeras filas después del
     encabezado declarado buscando una que luzca a encabezado real
     (2+ celdas no vacías) y contenga una palabra clave de período.
  2. Recursos con nombre casi idéntico (`Pagos Desempleo Marzo/Abril/Mayo/
     Junio 2026`) cambian de formato interno entre meses sin aviso —
     mismo problema de fondo que motivó este pendiente, pero peor de lo
     documentado: no solo hay ambigüedad acumulado-vs-incremental, el
     *esquema de columnas en sí* cambia. Comparar períodos entre dos
     archivos con esquemas distintos daba 0% de solapamiento, que la
     heurística original reportaba como `incremental` con confianza — una
     conclusión calculada correctamente pero engañosa. Nueva función
     `_schema_mismatch` compara los encabezados de ambos archivos antes de
     confiar en el solapamiento de períodos; con menos de 50% de columnas
     en común, la clasificación se fuerza a `indeterminado`
     (`esquema_distinto_entre_archivos`) en vez de adivinar.
- **`detect_periodic_series` no agrupaba resúmenes que difieren en el
  nombre de mes en español** (`..._2023_AGOSTO.csv` vs
  `..._2023_SEPTIEMBRE.csv`) — encontrado verificando `detect_series_pattern`
  contra MPCEIP cacao, mismo tipo de bug que motivó este pendiente pero en
  el auto-detect del par a comparar, no en la clasificación en sí. Los
  nombres de mes ahora se normalizan al mismo placeholder que los dígitos
  antes de agrupar por plantilla (con lookaround sobre letras, no `\b`, ya
  que `_` cuenta como carácter de palabra y estos nombres suelen venir
  separados por guion bajo).
- **`_pick_pair` elegía "el más reciente" por `last_modified` de CKAN,
  que resultó no ser confiable** — mismo dataset MPCEIP: el recurso de
  enero 2023 tenía `last_modified` posterior al de septiembre 2023
  (probable corrección/re-subida), así que el auto-pick invertía el orden
  cronológico real por 8 meses. Nueva función pública `period_sort_key`
  (`list_dataset_resources.py`) extrae año/mes del propio nombre del
  recurso y ordena por eso primero, usando el timestamp de CKAN solo como
  desempate.

### Confirmed
- **`detect_series_pattern` verificado de punta a punta, sin argumentos
  adicionales, contra los dos datasets reales que motivaron este
  pendiente:**
  - **MPCEIP cacao** (dataset `96f97d5c-394f-4be6-8046-3266d0cd5711`):
    auto-detectó el par AGOSTO→SEPTIEMBRE 2023 y clasificó correctamente
    `acumulado` (34/34 períodos = 100%), coincidiendo con la cifra de
    verificación e2e ya documentada más abajo. (Nota de corrección: se
    afirmó por error durante esta verificación que `search_datasets` no
    encontraba este dataset — era un bug en el script de diagnóstico
    usado, no un problema real; `search_datasets(query="cacao"/"MPCEIP")`
    sí lo encuentra. Ver ROADMAP.md, sección "Calidad de búsqueda".)
  - **IESS desempleo** (`base-de-datos-seguro-desempleo`): auto-detectó el
    par Junio→Julio 2026 y clasificó correctamente `acumulado` (13/13
    períodos = 100%).
  Primera confirmación de que la clasificación en sí acierta contra el
  portal real —y ahora también el auto-detect del par, sin pasar
  `resource_id_new`/`resource_id_old` a mano— no solo que el tool se
  abstiene con seguridad en datos ambiguos.

## 0.7.0 — 2026-08-26

Soporte de preview para tres formatos que antes solo se podían descargar
crudos (Excel legacy `.xls`, `.tar.gz` y `.zip` que envuelven un
CSV/TSV/TXT), expansión de siglas y sniffing de Content-Type en la
búsqueda/previsualización, y varios fixes de confiabilidad encontrados
verificando contra el portal real. Confirmación de renovación del
certificado TLS del portal.

### Added
- **Soporte `.xls` legacy en `preview_resource_data`**: previsualiza el
  archivo como tabla vía `xlrd` (pura Python, sin binario externo) en vez de
  solo señalar `xls_no_soportado` y apuntar a `download_resource`. Nueva
  función `helpers/csv_reader.preview_xls`, misma forma que `preview_xlsx`.
- **Previsualización de `.tar.gz` en `preview_resource_data`**: descomprime
  el archivo (`tarfile` + `zlib`, stdlib, sin dependencia nueva) y muestra el
  CSV/TSV/TXT interno como tabla. Si el archivo contiene varios miembros,
  prioriza `.csv` > `.tsv` > `.txt` en vez de tomar el primero del archivo
  (evita que un `readme.txt` empaquetado gane sobre el dato real — bug real
  encontrado escribiendo el test de esta función). La descompresión tiene un
  tope de 20 MB para acotar el impacto de un archivo diseñado para expandirse
  desproporcionadamente al descomprimirlo. Nueva función
  `helpers/csv_reader.preview_targz`.
- **Soporte `.zip` en `preview_resource_data`**: descomprime el archivo
  (`zipfile`, stdlib, sin dependencia nueva) y muestra el CSV/TSV/TXT interno
  como tabla, con la misma prioridad `.csv` > `.tsv` > `.txt` que `.tar.gz`
  al elegir el miembro. A diferencia de `.tar.gz`, el directorio central de
  un `.zip` no requiere descomprimir nada para listar los miembros, así que
  basta con acotar la lectura del miembro elegido (sin el paso de
  descompresión con tope que sí hace falta para `.tar.gz`). Lógica de
  selección de miembro extraída a `helpers/csv_reader._pick_member`,
  compartida entre `preview_targz` y el nuevo `preview_zip`.
- **Expansión de siglas/acrónimos en `search_datasets`**: `helpers/acronyms.expand_acronyms`
  agrega el nombre completo de ~13 siglas comunes (ENEMDU, ENSANUT, ENIGHUR,
  ECV, RUC, IESS, SRI, INEC, BCE, SERCOP, SENESCYT, SUPERCIAS, SGR) a la
  consulta antes de mandarla a CKAN. El operador default de Solr en CKAN es
  OR entre términos, así que esto amplía el recall sin restringir el match
  original.
- **Sniffing de Content-Type para recursos sin extensión**: cuando ni la
  extensión de la URL ni el `format` declarado por CKAN son reconocibles,
  `preview_resource_data` hace un sniff best-effort del header HTTP
  `Content-Type` (`helpers/csv_reader.sniff_content_type`, solo lee headers,
  no descarga el body) antes de rendirse. Marca `sniffed_content_type: true`
  en la respuesta cuando esto se activó.

### Fixed
- Refactor interno: la lógica de parseo de CSV se extrajo a
  `helpers/csv_reader._parse_csv_bytes`, compartida entre `preview_csv` y
  `preview_targz`, sin cambios de comportamiento en `preview_csv`.
- `preview_targz` no marcaba `truncated=True` cuando el CSV/TSV/TXT interno
  superaba los 5 MB por sí solo (solo consideraba la descarga y la
  descompresión externas) — el contenido se cortaba igual, pero el preview
  no avisaba. Corregido leyendo un byte de más para detectar el corte, igual
  que ya hacía la descarga original.
- `tools/download_resource.py`: el docstring seguía listando `.tar.gz` y
  `.xls` legacy como formatos que hay que descargar crudos, desactualizado
  desde que `preview_resource_data` empezó a previsualizarlos.
- **`helpers/ckan_client._fetch_json` no nombraba el host en fallas de
  conexión.** Un `httpx.ConnectTimeout`/`ConnectError` real se puede
  stringificar como `""` o `"timed out"` sin mencionar qué host falló.
  Ahora `HTTPStatusError` (ya trae URL+status) y `RequestError` (timeouts,
  conexión rechazada) se distinguen; el segundo caso levanta un
  `RuntimeError` explícito con el host y el tipo de fallo.
- **Tres bugs reales encontrados verificando `.xls`/`.zip` contra el portal
  en vivo** (no solo con archivos sintéticos):
  1. Un `.zip`/`.tar.gz` real más grande que el límite de 5 MB de descarga
     se corta antes de llegar al directorio central (que vive al final del
     archivo en `.zip`), así que `zipfile`/`tarfile` fallan por completo, no
     de forma parcial. Antes esto daba el genérico "está corrupto o
     incompleto"; ahora se detecta la truncación *antes* de intentar
     parsear y se da un mensaje específico apuntando a `download_resource`.
  2. Un `.zip` real sin ningún archivo tabular (paquete GIS raster:
     `.lyr`/`.tif`/`.tif.aux.xml`) hacía que la selección de miembro cayera
     al primer archivo del `.zip` y lo forzara al parser de CSV, crasheando
     con un `csv.Error` sin capturar. `_pick_member` ya no cae a "el primero
     que sea": devuelve `None` cuando ningún miembro parece tabular, y
     ambos previews (`.tar.gz`/`.zip`) dan un mensaje claro listando los
     archivos reales encontrados.
  3. `_parse_csv_bytes` no capturaba `csv.Error` en absoluto (repro real: un
     `\r` suelto sin comillas dentro de un campo) — ahora se traduce a un
     `ValueError` accionable.

### Confirmed
- **Certificado TLS de `www.datosabiertos.gob.ec` renovado** (Let's Encrypt,
  válido 2026-08-07 a 2026-11-05) — verificado contra el portal real.
  `CKAN_INSECURE_TLS` ya estaba en su default seguro (`0`) desde antes; no
  se requirió ningún cambio de código.

## 0.6.0 — 2026-08-18

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
