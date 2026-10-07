# Plan: reaching geoblocked Ecuadorian sources with free services

Status: proposal (2026-09-29). Nothing here is built yet.

## Problem

Several sources reject or drop traffic from outside Ecuador/LatAm or from
datacenter IPs (see `RESEARCH.md` and `helpers/smoke_status.py`):

| Host | Symptom | Likely cause |
|---|---|---|
| `datosabiertos.gob.ec` | 403 "fuera de Latinoamérica" | country |
| `compraspublicas.gob.ec` | TCP handshake dropped | country |
| `sisdatbi.arconel.gob.ec` | timeout, answers under a VPN | country/IP range |
| `eerssa.gob.ec` (PDFs) | Apache 403 | country or rule (unconfirmed) |
| `anda.inec.gob.ec`, `censoecuador.gob.ec` | 403 from GitHub runners | datacenter IP or bot filter |
| `gob.ec` | HTTP 200 with empty body from runners | datacenter IP or bot filter |
| `mercadodevalores.supercias.gob.ec`, `appscvsmovil.supercias.gob.ec` | TCP connect timeout from Render (2026-10-07); 0.15 s from a Canadian home IP | datacenter IP or country |

Re-checked 2026-10-02 from a residential IP in Canada (not a datacenter):
`datosabiertos`, `anda.inec`, `censoecuador` and `eerssa` answer Apache 403,
`reportes.arconel` and `compraspublicas` time out, `www.gob.ec` resets the
connection, while `sisdatbi.arconel` and `www.ecuadorencifras.gob.ec` answer
200. A home IP failing the same way points to a country block, not a
datacenter or bot filter, for ANDA, the census site and gob.ec as well; so
`www.gob.ec` and `censoecuador.gob.ec` joined the default proxied hosts
(`helpers/geo_proxy.py`), and `download_bytes` and `gobec_client` now route
through `proxy_for`. INEC's main site is reachable and stays direct.

The current workaround (a local VPN) does not help CI, PyPI/MCPB installs or
anyone else. Goal: a free path that works away from one laptop.

## Constraints

- Free services only; no paid proxy pools.
- Must work from CI and from other people's installs, not only locally.
- No open proxy: the egress must be authenticated and limited to the
  hosts above.
- Default behavior unchanged when nothing is configured.

## Phase 0: find out what is actually blocked (about 1 hour, free)

The right fix depends on whether each block is by country or by
datacenter/bot fingerprint. Probe each host from:

1. Your home connection, no VPN (control).
2. Your home connection with the free VPN you already use (LatAm exit).
3. A GitHub Actions run (datacenter IP, US) — a throwaway workflow that
   `curl`s each host and prints status, size and first bytes.
4. A free-tier VM in a LatAm region (Phase 1), once it exists.

Record results in `RESEARCH.md` as a table: host x vantage point x result.
Hosts that fail from (4) too are bot-filtered, not geoblocked; a proxy will
not fix them and they drop out of this plan.

## Phase 1: a free egress point in the region

Candidate free tiers, in the order to try them. Free-tier terms and region
lists change, so confirm each on the provider's page before relying on it.

1. **Oracle Cloud Always Free** (ARM or AMD micro VM, no expiry). Has
   South American regions (São Paulo, Santiago, Bogotá). The home region
   is fixed at signup, so choose the closest one to Ecuador (Bogotá if
   offered, else Santiago or São Paulo). Needs a card for verification and
   free capacity is sometimes short.
2. **AWS free tier, São Paulo (`sa-east-1`).** Micro instance free for 12
   months, then it costs money. Use only as a stopgap.
3. **Azure free account, Brazil South.** 12-month B1s, same caveat.
4. **Fly.io / similar.** Have Bogotá, Santiago and Querétaro regions, but
   the free allowance for new accounts has been reduced; check first.

Not viable, so skip: Cloudflare Workers and most PaaS free tiers (egress
IP is chosen by the platform and is not in LatAm), Google Cloud free tier
(US regions only), free public proxy lists (unreliable and unsafe).

Free consumer VPNs (Proton, Windscribe) are fine for Phase 0 spot checks
but cannot be scripted from CI.

Expected outcome: one small VM with a LatAm IP. Confirm Phase 0 probe (4)
shows which hosts it unlocks; if none of the LatAm regions work for a
host, try a different region before abandoning it.

## Phase 2: two ways to use the egress

### 2a. Authenticated tunnel for live requests

- On the VM, run only `sshd` (key auth, no password). No open proxy port.
- Callers open a SOCKS tunnel: `ssh -N -D 1080 user@vm` and set
  `ECUADOR_MCP_GEO_PROXY=socks5://127.0.0.1:1080`.
- CI does the same in a workflow step, with the private key stored as a
  repository secret.
- Works for you on any machine and for CI. Other users would need their own
  VM, so treat it as the maintainer/CI path, not the default for everyone.

### 2b. Snapshot mirror for everyone else

Most of the blocked data changes slowly (catalogs, contracts, cortes PDFs).
Instead of proxying every request:

- A scheduled job on the VM (cron) fetches from the blocked hosts and
  publishes results as static files: GitHub Releases assets or the
  `gh-pages` branch (both free).
- The server reads the snapshot when the live request is blocked, using the
  existing TTL cache and `helpers/paths.data_dir()` conventions (BCE
  snapshots already work this way).
- Users need no configuration and no VPN. The trade-off is staleness
  (hours to days) and that only the endpoints we choose to mirror are
  covered.

Recommended: build 2a first (small, unblocks CI and you), then 2b for the
few highest-value sources chosen from Phase 0 results
(`datosabiertos.gob.ec` and `compraspublicas.gob.ec` first).

## Phase 3: code changes (small, opt-in)

1. `helpers/env_config.py`: `ECUADOR_MCP_GEO_PROXY` (proxy URL) and
   `ECUADOR_MCP_GEO_HOSTS` (comma-separated, defaulting to the Phase 0
   confirmed list).
2. New `helpers/http.py` with `make_client(host, **kw)`: returns an
   `httpx.AsyncClient` that routes geo-listed hosts through the proxy via
   `mounts=`, and keeps the TLS handling from `helpers/tls.py`. Unset
   config means identical behavior to today.
3. Migrate only the affected clients: `ckan_client`, `sercop_client`,
   `gobec_client` (if Phase 0 says it is geo, not bot), `anda_client`,
   `inec_client`, `arconel_reportes_client`. The other clients are left
   alone.
4. One shared error message for geo-listed hosts when a request fails with
   403, an empty body or a connect timeout and no proxy is set. It names
   the host, states that it is likely geoblocked, and points to
   `ECUADOR_MCP_GEO_PROXY`. Replaces the per-client wording in
   `sercop_client.py` and the `smoke_status.py` markers.
5. Snapshot fallback (2b) as a separate change: a small reader in the
   affected client that tries live, then the mirror.
6. Tests with `pytest-httpx`: routing for listed vs unlisted hosts, the
   no-config case, the error message, the snapshot fallback. No real
   network.
7. Docs: README "Geoblocks" section, `ROADMAP.md`, `RESEARCH.md` results
   table, and env entries in `manifest.json` and `server.json`.

## Phase 4: CI

- Add the SSH tunnel step to the live-smoke workflow, guarded on the secret
  being present.
- With the tunnel, the corresponding `degraded` entries in
  `smoke_status.py` should become passes. Keep them for runs without the
  secret (forks, missing secret).

## Risks and open questions

- Oracle idle-reclaim and capacity: keep the VM lightly active (the cron
  mirror does this) and keep a second provider as a fallback.
- ToS: the sources are public open-data portals, but keep request rates low
  and respect each site's limits; use the existing caches.
- Bot-filtered hosts (`gob.ec`, INEC, ANDA, SEPS) may not be fixed by any
  LatAm IP; Phase 0 decides. For those, a real-browser fingerprint or a
  different route is a separate problem.
- Free-tier terms change; the plan names providers to check, not promises.

## Order of work

1. Phase 0 probes (GitHub Actions workflow plus home/VPN checks).
2. Phase 1 VM, re-run probes from it.
3. Phase 3 items 1-4 and 6, then 2a tunnel and Phase 4.
4. Phase 2b mirror for the top sources, then docs.
