Contribuciones son bienvenidas. Por favor:

1. Fork el repositorio
2. Crea tu feature branch (`git checkout -b feature/nueva-herramienta`)
3. Haz commit de tus cambios (`git commit -m 'feat: agregar nueva herramienta'`)
4. Push a la branch (`git push origin feature/nueva-herramienta`)
5. Abre un Pull Request

## Alcance

Servidor MCP de datos abiertos *del gobierno ecuatoriano* (CKAN nacional y
municipal, gob.ec, SRI, BCE, Supercías, IESS/SENESCYT, IG-EPN, SERCOP, SGR y
más): 84 tools en el perfil `public`. Python, MCP SDK 2.x
(`mcp.server.mcpserver.MCPServer`), transporte stdio o HTTP streamable.
Antes de dar por nueva una fuente, mira [docs/ROADMAP.md](docs/ROADMAP.md)
(qué está integrado y qué falta), [docs/RESEARCH.md](docs/RESEARCH.md) (los
hallazgos y callejones sin salida detrás de cada fila) y
[CHANGELOG.md](CHANGELOG.md).

## Estructura

- `main.py` — wiring del `MCPServer`, endpoint `/health`, CLI (`--transport`,
  `--host`, `--port`).
- `tools/` — un archivo por tool MCP, registrados en
  `tools/__init__.py:register_tools`.
- `helpers/` — un cliente HTTP por fuente (`ckan_client`, `sri_client`,
  `bce_client`, `supercias_client`, …) más lo transversal: `cache.py` (TTL),
  `csv_reader.py` (preview y parseo de CSV/XLS/XLSX/ZIP/tar.gz),
  `safe_download.py`, `format_out.py`, `tls.py`, `geo_data.py`,
  `env_config.py`.
- `prompts/`, `resources/` — prompts y recursos MCP.
- `scripts/` — mantenimiento: `smoke_e2e.py`, `publish_smithery.py` y el
  wrapper de la base de Supercías (la construcción vive en
  `helpers/supercias_financials_build.py` para que las instalaciones
  PyPI/MCPB, sin `scripts/`, también puedan ejecutarla).
- Los datos escritos en tiempo de ejecución (base de Supercías, snapshots
  del BCE) van a `helpers/paths.data_dir()`: `data/` en un clon, el
  directorio de datos del usuario instalado desde PyPI,
  `ECUADOR_MCP_DATA_DIR` lo sobreescribe.
- `web/` — sitio público (generador Jinja2 en `web/build.py`, ES y EN en
  paralelo); detalles en `web/README.md`.
- `tests/` — pytest, un archivo por helper o tool; `pytest-httpx` mockea el
  HTTP saliente.

## Comandos

```bash
uv sync                                  # instalar dependencias
uv run main.py                           # transporte HTTP (default)
uv run python main.py --transport stdio  # transporte stdio
uv run pytest                            # tests
uv run ruff check .                      # lint
uv run python -m helpers.supercias_financials_build  # reconstruir la base de Supercías
```

## Convenciones

- Fuente nueva → `helpers/<fuente>_client.py` nuevo más su `tools/*.py`,
  registrados en `tools/__init__.py`.
- Nunca confiar solo en el campo `format` que declara CKAN: la extensión
  de la URL manda cuando es reconocible, y un sniff del `Content-Type`
  (`helpers/csv_reader.sniff_content_type`) es el último recurso. Varios
  bugs reales del portal (`.tar.gz` declarado como CSV, `.xlsx` declarado
  como CSV) vinieron de fiarse del `format` — ver la sección "Formatos y
  tipos de recursos" de docs/ROADMAP.md.
- Los previews de archivos comprimidos (`.zip`, `.tar.gz`) eligen el
  miembro con `helpers/csv_reader._pick_member` (`.csv` > `.tsv` > `.txt`,
  `None` si no hay nada tabular); no caer en "el primer archivo del zip".
- Descargas y descompresión tienen tope (5 MB de descarga, 20 MB
  descomprimido) para acotar memoria y ancho de banda ante un archivo
  hostil o enorme.
- El parseo de CSV entiende la notación decimal europea (`7.760,2`) y quita
  las columnas de geometría/WKT antes de renderizar un preview.
- Cacheo TTL por fuente vía `helpers/cache.py`; respetar el TTL que ya tiene
  cada cliente en vez de añadir cachés ad hoc.
- Los tests mockean el HTTP con `pytest-httpx`; nunca pegarle a un endpoint
  real desde un test.

## Releases

Subir la versión en `pyproject.toml`, `server.json` y `manifest.json` y
publicar un release de GitHub `vX.Y.Z`; `.github/workflows/publish.yml` sube
a PyPI y al MCP Registry y adjunta el `.mcpb`. Smithery es manual
(`scripts/publish_smithery.py`). Después del release, añadir la entrada en
`web/data/releases.json` y `web/en/data/releases.json`.
