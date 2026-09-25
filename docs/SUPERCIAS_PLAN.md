# Supercías financials — plan

Status as of 2026-09-25. Covers `search_ranking` / `get_financials`, backed by
the local SQLite DB built from the Supercías Ranking export (`bi_ranking.csv`).

## Phase 0 — resilience (done, branch `supercias-build-resilience`)

- Stale DB (> 7 days) is served, flagged, while a refresh runs.
- Failed builds back off 1h / 6h / 24h (`data/supercias_build.state.json`).
- Cross-process lock file; hung builds killed after 45 min; download deadline.
- Build rejected on > 0.1% malformed rows or a 20%+ row drop vs. the live DB.
- Build status in `metadatos.base_local` and `/health`.
- `search_ranking` defaults to the latest year; ambiguous RUCs (~156) list
  their candidate expedientes.

## Phase 1 — decouple building from serving (not started, undecided)

Problem: every server instance downloads 356 MB and builds for ~15-20 min, and
the build only works from a repo checkout (breaks a PyPI install: the build
script isn't packaged and the DB path points into `site-packages`).

Required regardless of where the build runs:

- Move the build code into the package (e.g. `helpers/supercias_build.py`),
  keeping `scripts/` as a thin wrapper.
- Data directory from `ECUADOR_MCP_DATA_DIR` (default `data/` in a checkout,
  a user data dir when installed, `/app/data` in Docker).

Open decision — where the prebuilt DB comes from:

| Option | Pros | Cons |
|---|---|---|
| A. Keep building locally in each server (status quo) | No new infrastructure | Slow first start; every host hits Supercías |
| B. Scheduled GitHub Actions build, publish DB as a Release asset | Seconds to install; Supercías outages invisible to users | Depends on Actions runners reaching Supercías (legacy TLS, 13-min download); CI maintenance; not yet validated |
| C. Build on the hosted server only, expose the DB file for download | No Actions; one build for all clients | Needs the hosted endpoint to exist first |

Recommendation: do the packaging/data-dir work now (needed for PyPI in any
case); defer the A/B/C choice until the hosted endpoint exists, then prefer C.

## Phase 2 — keep the full history (worth doing)

Gain: the build currently deletes 1,015,098 of 1,676,075 rows (2008-2020).
Keeping them turns the tool from a "last five years" lookup into a usable
firm-level panel for research — the main audience in the project page.
Cost is small: DB grows from ~220 MB to roughly 500 MB; build time barely
changes (the download dominates).

- Retention setting (`all` or N years), default `all`.
- `desde` / `hasta` filters on `get_financials` and `search_ranking`.
- Record each build's column list; keep dropped columns as `null` and note
  ratios that aren't comparable across years.
- Parquet/DuckDB only if large aggregations become a real request — not now.

## Phase 3 — live per-company lookup (low value, park)

Gain is marginal: the bulk export already refreshes daily, so a live lookup
only helps for filings in the last day or two, and the Supercías information
portal is a session-based web app with no confirmed API. Keep only the cheap
part: the results are already labelled `daily_bulk`. Revisit if users report
missing very recent filings.

## Open data-quality check

- The 2025 ranking's #1 is PESCADOOR S.A.S. — verify against the official
  ranking before relying on the latest (still-filling) year.
