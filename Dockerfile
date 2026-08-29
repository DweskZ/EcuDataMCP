FROM python:3.14-slim

# Runs as this instead of root -- the server only reads outbound HTTP and
# holds in-memory caches, no reason for it to run with root's filesystem
# reach if a dependency (or the process itself) is ever compromised.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser

WORKDIR /app

RUN pip install --no-cache-dir uv

# Manifests first so this layer caches across source-only changes.
COPY pyproject.toml uv.lock ./

# Source before install: pyproject.toml declares helpers/tools/prompts/
# resources as this package's own directories, and readme="README.md" in
# its build metadata -- installing before those exist (as the previous
# `pip install .` before `COPY . .` did) produces an incomplete
# distribution that only ran because the later COPY put raw source files
# on the working directory anyway, not because the install itself worked.
COPY helpers/ helpers/
COPY tools/ tools/
COPY prompts/ prompts/
COPY resources/ resources/
# scripts/ isn't imported by the server itself, but stays in the image so an
# operator can run its one-off data-fetch/smoke-test scripts via
# `docker compose exec mcp uv run python scripts/<name>.py`.
COPY scripts/ scripts/
COPY main.py README.md ./

# --locked: fail the build rather than silently re-resolving if uv.lock
# and pyproject.toml ever drift, instead of installing whatever versions
# happen to be newest that day (the previous plain `pip install .` had no
# lockfile at all, so Docker and CI could end up on different dependency
# graphs from the same commit).
RUN uv sync --locked --no-dev

# /app/data doesn't exist yet -- it's only created at runtime by
# scripts/build_supercias_financials_db.py, and docker-compose.yml mounts a
# named volume there. Docker copies a fresh named volume's initial
# ownership from whatever's already at that path in the image, so this has
# to exist (owned by appuser) before that mount happens, or the volume
# comes up root-owned and that script can't write to it as appuser.
RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

EXPOSE ${MCP_PORT:-8000}

CMD ["uv", "run", "python", "main.py"]
