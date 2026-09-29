# EcuDataMCP — sitio web

Landing page del proyecto, construida con un pequeño generador estático en Python (Jinja2). Vive en `web/`
para que un solo PR pueda actualizar el README del servidor y el sitio a la vez.

## Estructura

- `build.py` — el generador. Lee `data/*.json` y `en/data/*.json`, renderiza `templates/{es,en}/*.html`
  con Jinja2, y escribe todo a `_site/` (`_site/en/` para inglés). Sin dependencias fuera de Python +
  Jinja2 — no hace falta R ni Node para nada.
- `templates/base.html` — el navbar y footer compartidos (una sola plantilla, parametrizada por idioma).
- `templates/{es,en}/*.html` — una plantilla por página por idioma (`index`, `atlas`, `examples`,
  `releases`, `about`, `colaborar`). Igual que antes, mantener los dos idiomas sincronizados es manual:
  un cambio de copy en español necesita el mismo cambio portado a mano en `templates/en/`.
- `data/*.json` / `en/data/*.json` — fuentes, clientes MCP, tools, preguntas de ejemplo y releases.
  Editar estos archivos no requiere saber Python — es solo JSON.
- `data/tool_signatures.json` — extracción cruda en inglés (nombre, parámetros con tipo/default,
  descripción del decorador y docstring) de todas las tools públicas registradas en `../tools/*.py`
  (no incluye las de mantenimiento), generada por `scripts/extract_tool_signatures.py` (un script `ast`,
  no a mano; el workflow de Pages lo corre en cada build). Es la fuente de verdad de qué tools existen y
  qué parámetros tienen: `build.py` descarta de `tools.json` las tools que ya no existen, sincroniza sus
  parámetros con el código y muestra las tools nuevas en una categoría aparte, en inglés, hasta que se
  traduzcan a mano `description`/`long_description`/`params` en `data/tools.json` y `en/data/tools.json`.
- `assets/styles.css` — el CSS del sitio, en texto plano; es la única fuente (no hay SCSS que recompilar).
  Edítalo directamente.
- `assets/` — CSS compilado, `site.js` (toggle de navbar móvil, tabs de clientes MCP, panel de búsqueda,
  botón de copiar), `fuse.min.js` (vendored, motor de la búsqueda), favicon, imagen OG. El ícono de
  búsqueda del navbar es un SVG inline en `templates/base.html`, no una fuente de íconos.

## Cómo se genera

```bash
cd web
uv sync
uv run python build.py
```

Esto regenera `_site/` completo (español + inglés) a partir de `data/*.json` y las plantillas. No hace
falta ningún paso adicional ni ninguna dependencia fuera de Python — a diferencia del setup anterior,
editar un `data/*.json` y correr `build.py` ya refleja el cambio en el HTML.

## Cómo se publica

El workflow [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) construye `web/_site/` y lo
publica en GitHub Pages en cada push a `main` que toque `web/` (también se puede disparar a mano con
`workflow_dispatch`).

URL del sitio: <https://dweskz.github.io/EcuDataMCP/>

En el repo: **Settings → Pages → Source → GitHub Actions** (una sola vez). Mientras eso no esté
activado, también se puede servir desde la rama `gh-pages` (contenido de `_site/` en la raíz).

## Búsqueda

El panel de búsqueda (ícono en el navbar) usa [Fuse.js](https://www.fusejs.io/) contra un `search.json`
que `build.py` genera automáticamente a partir del texto visible de cada página (`<main>` únicamente, sin
navbar/footer). No requiere ningún paso manual.

## Desarrollo local

```bash
cd web
./preview.sh
```

Abre `http://127.0.0.1:8765/`. Sirve el sitio como HTTP real (no `file://`) porque la
búsqueda hace `fetch()` contra `search.json`.

Alternativa manual:

```bash
cd web
uv sync
uv run python build.py
cd _site && python -m http.server 8000
```

