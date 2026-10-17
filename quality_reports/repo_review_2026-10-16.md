# EcuDataMCP — full repository review (2026-10-16)

Branch `review-fixes` at `1a52da5`. Read-only review; no source files were edited.

## Baseline

| Check | Result |
|---|---|
| `uv run pytest` | 1008 passed (74 s) |
| `uv run ruff check .` | clean |
| `uv run ruff format --check .` | 199 of 317 files would be reformatted (not enforced in CI) |
| Versions (pyproject, server.json, manifest.json, CHANGELOG, web releases) | all 0.12.0, consistent |
| tools/list | 83 public tools, every parameter documented, 85,780 / 110,000 char budget |

Method: six parallel reviewers (download/parse pipeline; BCE + international clients;
clients A–I; clients M–X; tools/prompts/resources; CI/packaging/web/docs). Every finding
below was confirmed by reading the cited lines; items marked **[exec]** were also reproduced
by running code.

## Findings

### High

1. **helpers/csv_reader.py:43,105 — US-style thousands read as EU decimals [exec].**
   `_EU_DECIMAL_RE`'s second branch `\d+,\d+` matches `1,234`. Column `["1,234","12,500","987,000"]`
   is "converted" to `1.234, 12.500, 987.000` and reported as EU-normalised: values 1000x too small
   with a confident label. Fix: treat samples that are all `^\d{1,3},\d{3}$` as ambiguous and skip;
   require at least one unambiguous sample (`7.760,2` or a non-3-digit decimal part).

2. **helpers/bce_iem_client.py:803, 896-905 — IEM wide-series header picked by substring "ano" [exec].**
   `_period_key` accepts any bare 4-digit integer as a year, and the header row is the first row whose
   first cell contains `period`/`ano`/`fecha`/`mes`. A sheet whose real header has no such token and
   whose first data row is "Banano" makes Banano the header: periods become `['1500','2300']`, the
   Banano row vanishes, Cacao is keyed by Banano's values, returned as `formato: series_ancho` with
   no warning. Fix: constrain years to 1900..current+1 and require header cells to be str/datetime.

3. **helpers/csv_reader.py:657 — `.xlsb` preview skips the zip-bomb guard.**
   `preview_xlsx` (l.546) and `preview_ods` (l.730) call `_check_zip_container_size`; `preview_xlsb`
   does not, and pyxlsb reads `sharedStrings.bin` whole. A 20 MB .xlsb with a 1000:1 shared-strings
   member allocates gigabytes. Fix: `_check_zip_container_size(raw, ".xlsb")` before `open_workbook`.

4. **helpers/aviacion_client.py:447 (also :152, :263) — ICAO designator unvalidated in URL path.**
   `f"{_AIP_BASE}/aip/AD%202%20{icao}"` has no quoting; METAR/NOTAM use `quote()` which keeps `/`.
   `get_metar("../notam?designador=SEQM")` fetches another path on the DGAC host and caches the HTML
   under the attacker's key. Fix: `re.fullmatch(r"[A-Z0-9]{4}", icao)` before building any URL.

5. **helpers/supercias_financials_build.py:442 — `os.replace` fails on Windows while a reader has the DB open [exec].**
   The comment claims atomicity on Windows; with a `mode=ro` sqlite connection open, `os.replace`
   raises `PermissionError [WinError 5]`. A `get_financials` call or `/health` (`financials_status`)
   overlapping the final rename discards the 15-20 min, 356 MB build, increments the failure backoff,
   and leaves the `.building` file for the next attempt. Fix: retry the replace with short sleeps;
   keep reader connections short-lived.

6. **tools/download_resource.py:82-99 + helpers/format_out.py:50-51 — text mode ships the whole file.**
   The docstring (l.43) says `format="text"` "never includes content_base64", but `render_structured`
   attaches the full payload as `structured_content` regardless of format, so every text call puts up
   to ~6.7 MB of base64 into the client's context. Fix: drop `content_base64` from the structured dict
   when `format != "json"`.

7. **docker-compose.yml:19-20 + README.md:253 — documented default `docker compose up -d` crash-loops.**
   Compose defaults `MCP_REQUIRE_AUTH=1` with an empty `MCP_AUTH_TOKEN`; main.py:202 raises
   `RuntimeError`, and `restart: unless-stopped` restarts forever. Only docs/DEPLOYMENT.md explains it.
   Fix: README's Docker section must show `MCP_AUTH_TOKEN=... docker compose up -d`.

8. **.github/workflows/smoke.yml:43-48 — SSH tunnel trusts unknown host keys.**
   With `GEO_SSH_KNOWN_HOSTS` unset, `StrictHostKeyChecking=accept-new` accepts any key on first
   contact; a MITM gets the session and all smoke traffic through the SOCKS proxy. Fix: fail the step
   unless the known-hosts secret is set; always `StrictHostKeyChecking=yes`.

9. **helpers/centrosur_cortes_client.py:210, eeq_cortes_client.py:295 — pypdf on the event loop, no page cap.**
   `parse_pdf(raw)` runs synchronously for PDFs up to 25 MB / 15 MB; centrosur extracts every page
   twice (:381, :394). A pathological PDF stalls every concurrent request on the HTTP transport. Same
   pattern in csv_reader.py:547,595,657,731 and pdf_reader.py:272-301 (openpyxl/xlrd/pyxlsb/odfpy/pypdf
   all synchronous). Fix: `await asyncio.wait_for(asyncio.to_thread(parse, raw), timeout=…)` and cap pages.

### Medium

10. **helpers/csv_reader.py:104-120** — EU classification decided on 5 sample rows but applied per cell;
    `1,5 ×5, 2.5, 1.000` leaves `1.000` (=1000) reading as 1.0 [exec].
11. **tools/investigate_dataset.py:119, tools/detect_series_pattern.py:254** — bare `httpx.AsyncClient()`
    passed into `download_bytes`/`_fetch_json`, bypassing the User-Agent and `proxy_for` geo-proxy that
    the owned-session path applies. A geo-fenced file previews but fails via these two tools.
12. **helpers/sut_powerbi_client.py:764** — filter values interpolated raw into a Power BI string literal
    (`f"'{valor}'"`); an apostrophe (`O'Higgins`) breaks the query, arbitrary literal syntax injectable.
    Escape `'` as `''`.
13. **helpers/sut_powerbi_client.py:785,815-818 + tools/query_sut_indicador.py:25,63** — `limite` never
    clamped (default 20000, user can pass 10,000,000); no truncation flag; Power BI HTTP-200 error
    bodies are indistinguishable from "0 rows".
14. **helpers/bce_indices_client.py:337-348, bce_cuentas_nacionales_client.py:236-273,
    bce_precios_comex_client.py:164-196** — a failed page is swallowed and the *partial* catalog is cached
    6 h, so `get_archivo` says "no encontrada" for 6 hours. bce_client.py:353 deliberately refuses to
    cache partials; these three are inconsistent with it. Similar: bce_iem_client.py:276-298 caches a
    stale bulletin list 24 h when a source fails.
15. **helpers/bce_indicadores_diarios_client.py:263** — `desde`/`hasta` windows > 366 rows are cut to the
    last 366 with no `truncado` flag; and tools/get_bce_indicador_diario.py:58 compares dates as strings
    with no format validation (`01/01/2024` silently yields a wrong window).
16. **helpers/cepalstat_client.py:384** — `pais` falls back to the first substring match (`Guinea` →
    `Guinea Ecuatorial`) and labels the result with the user's string. irena_client.py:82 already does
    this right (raise listing candidates).
17. **helpers/gobec_client.py:194, 272** — pagination caps (3 pages / `max_pages`) return `[]` with no
    "more pages existed" signal.
18. **helpers/anda_client.py:172 + tools/download_anda_microdata.py:69** — missing CSRF token returns `[]`,
    rendered as "ANDA no tiene archivos"; an anti-bot or geoblock page becomes a confirmed "no microdata".
19. **Silent empty scrapes** — contraloria_client.py:107, arcsa_client.py:110, ineval_client.py:329,
    eeq_cortes_client.py:223, sri_client.py:131/203 (caches an empty parse 6 h), cenace_client.py:93
    (caches `{}`). censo_client.py:93 and cne_client.py:146 raise instead; make the rest match.
20. **helpers/data/parroquias_urbanas.json via geo_data.py:41** — two rows with `codigo == " "`,
    `nombre == ""` (Cayambe 170250, Sansahuari 210355) [exec]; and geo_data.py:100,128 substring-matches
    codes: `find_cantones(provincia="1")` returns 127 cantons vs 15 for `"01"` [exec].
21. **helpers/centrosur_cortes_pdf.py:399** — unlabelled pages take the *first* horario in the document,
    not the nearest preceding one; multi-block schedules get the wrong time.
22. **helpers/supercias_financials_build.py:100-127** — 356 MB download has no byte cap or free-space
    check; partial CSVs in `tmp_supercias_financials/` are not cleaned on failure.
23. **helpers/paths.py:28 + supercias_financials.py:199** — a relative `ECUADOR_MCP_DATA_DIR` resolves
    against cwd in the server but against `_PACKAGE_ROOT` in the build subprocess, so the DB is written
    where the server never reads it ("building in background" forever). `.resolve()` the override.
24. **helpers/smoke_status.py:123-136** — any 5xx from any host is "known degradation", and the
    cold-start marker also matches the schema-mismatch message; both can mask real regressions.
25. **tools/search_ecuador.py:103 / tools/investigate_dataset.py:157** — no per-source deadline in the
    fan-out (gob.ec can take 3×60 s), and resource classification is serial (one HEAD per unknown
    resource).
26. **CI/CD** — no `permissions:` block in ci.yml/smoke.yml/publish.yml `build` (default token scope);
    actions pinned by moving tags in jobs with `id-token: write`; `mcp-publisher` tarball executed
    without checksum (publish.yml:98); `workflow_dispatch` publishes to PyPI and the MCP Registry from any
    branch (only `mcpb` is gated, l.71); `ruff format --check` not run.
27. **web/build.py:317 + templates atlas.html:43** — `autoescape=False` with raw `{{ p.description }}`
    from tool docstrings; `tool_signatures.json` already contains `<fuente>`. Masked today only because
    every param is curated in tools.json.
28. **.mcpbignore** — `web/` (1.2 MB), `glama.json`, `server.json`, `.env.example` ship in every `.mcpb`.
29. **README.md:282-293** — env table omits `MCP_PROFILE`, `MCP_MAX_CONCURRENT_REQUESTS`,
    `FORWARDED_ALLOW_IPS`; `ANDA_*`, `LATACUNGA_*`, `IADB_*`, `BCE_EQUIVALENCE_REVIEW_DIR`,
    `CKAN_INSECURE_TLS`, `ECUADOR_MCP_GEO_*` are read in code but documented nowhere or only in one
    plan doc.

### Low

30. tools/preview_resource_data.py:37 classifies on the full URL incl. query string (`.zip?token=x` misses).
31. helpers/csv_reader.py:145 `int(content_length)` raises on a malformed header; download_resource.py:75
    refuses a fully received file when Content-Length overstated the size.
32. helpers/csv_reader.py:1091 `_parse_central_directory` has no bounds check before `unpack_from`.
33. tools/preview_resource_data.py:226 forwards `UnsafeUrlError` text including the resolved private IP.
34. Ten tools catch only `ValueError`, so httpx errors reach the client as raw English text:
    get_bce_indicador_diario, get_cenace_tablero, get_iess_archivos, get_informe_igepn,
    get_sut_indicador_schema, list_aip_aerodromos, lookup_ubicacion, query_sut_indicador,
    search_biinec_extras, search_sri_ruc.
35. All 85 tools annotate `-> dict[str, Any]` but return `CallToolResult`; outputSchema is the
    uninformative `{"type":"object"}`.
36. resources/catalog.py:206 `ecuador://fuentes` lists the two maintenance tools in the `public` profile.
37. helpers/intl_http.py:454 ignores HTTP-date `Retry-After`; sdmx_json.py:562,573 silently drops
    observations; wdi_client.py:255 never checks `meta.pages`.
38. helpers/igepn_informes_client.py:174 default year uses UTC, not Ecuador time (`igepn_client._ECUADOR_TZ`).
39. helpers/inec_client.py:435,504,548 sessions built without User-Agent.
40. HTML entities never unescaped: centrosur_cortes_client.py:94, cenace_client.py:97,
    energia_ecuador_snapshot_client.py:97.
41. helpers/sgr_publicaciones_client.py:288 `_event_locks` grows unbounded by user-supplied URL;
    bce_client.py:80 `_revision_observations` unbounded list; supercias_build.log never rotated.
42. helpers/supercias_financials.py:155-172 `_build_in_progress` mutates without the lock; `kill()` without
    `wait()` leaves a zombie; build.py:458 `except BaseException` records Ctrl-C as a failed build.
43. main.py:243 + logging.py:44 hard-code uvicorn at INFO, so `LOG_LEVEL` does not affect access logs.
44. Dockerfile: unpinned `python:3.14-slim` digest and `pip install uv` version.
45. helpers/env_config.py:57 `os.getenv(k, default)` returns `""` for a present-but-empty override.
46. scripts/smoke_e2e.py, scripts/audit_bce_*.py import `helpers` with no `sys.path` insert.
47. AGENTS.md is gitignored (.gitignore:25) but linked from docs/ROADMAP.md:398 and cited in RESEARCH.md;
    CONTRIBUTING.md has none of the commands/conventions that live only in that ignored file.
48. Test gaps: no test for `_check_zip_container_size`, IPv6 SSRF cases, `TtlCache` eviction, `os.replace`
    failure, DAX quoting, DSR truncation, US-thousands regression; PDF parsers tested only against
    fpdf fixtures synthesised to satisfy their own thresholds; a few `.*` URL mocks (test_ant_client.py:12,
    test_intl_series_clients.py:44,357).

## What is solid

- SSRF guard: every external-URL download goes through `safe_stream` (initial URL and each redirect hop
  validated, 5-hop cap); byte caps count real bytes, gzip budget enforced inside chunks, nothing
  extracted to disk. Checked for bypasses in the pipeline and all clients: none.
- TLS: `verify=False` appears in four places, each gated by `should_retry_insecure` (opt-in env +
  host allowlist + real `SSLCertVerificationError`); the bundled-intermediate path keeps full
  verification; `legacy_cipher_context` is scoped to one host.
- HTTP layer: the SDK mounts `/mcp` as an exact `Route`, so the `_MCP_PATHS` auth/rate-limit check
  cannot be bypassed with a sub-path; bearer compare is constant-time; rate table is swept.
- MCP layer: all 85 tools async, `@log_tool` inside `@mcp.tool`, `READ_ONLY` except the two
  maintenance tools, `format` is `Literal`, every param documented, prompts reference only real
  tools, no tool writes to disk, logging records parameter names only.
- SQL in supercias_financials is fully parameterised with whitelisted `order_by`; user input to
  SRI/SERCOP/SGR goes through `params=`.
- Packaging: versions consistent, package-data covers all runtime files, trusted publishing with
  scoped `id-token`, lockfiles tracked and `--locked` everywhere, repo hygiene clean, es/en web data
  in step and extractor output byte-identical to the tracked JSON.

## Resolution (same day)

All 48 findings were addressed in the working tree on `review-fixes` (uncommitted). After the
fixes: 1137 tests pass (baseline 1008), `ruff check .` clean. Details per item are in
CHANGELOG.md's Unreleased section. Two deliberate deviations: finding 44's base-image digest pin
is left to Dependabot's docker ecosystem (no network to fetch the digest here), and the EEQ
outage client still falls back to its documented seed list on a genuine "0 resultados" page
(finding 19) rather than raising. `ruff format` was not run on the tree (finding 26's last item);
that is a separate, whole-tree decision for the maintainer.

## Suggested order

1. Correctness of numbers: findings 1, 2, 10 (csv_reader + IEM parser) with regression tests.
2. Safety: 3 (xlsb guard), 4 (ICAO validation), 9 (parsers off the event loop), 12-13 (DAX quoting + limit clamp).
3. Operations: 5 (Windows replace retry), 7 (README compose), 8 (smoke known-hosts), 23 (data dir resolve), 26 (workflow permissions/pins/dispatch gating).
4. Honesty of results: 6, 14-19 (partial caches and silent empties), 20 (geo data rows + code matching).
5. Docs and hygiene: 27-29, 47, then `ruff format` sweep + CI step.
