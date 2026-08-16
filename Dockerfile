FROM python:3.13-slim

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

EXPOSE ${MCP_PORT:-8000}

CMD ["uv", "run", "python", "main.py"]
