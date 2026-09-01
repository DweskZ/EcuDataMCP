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
  docstring completo) de los tools en `../tools/*.py`, generada por `scripts/extract_tool_signatures.py`
  (un script `ast`, no a mano). Es la fuente de la que se traduce a mano `description`/`long_description`/
  `params` en `data/tools.json` y `en/data/tools.json`. Si se agrega o cambia un tool, correr ese script
  y portar a mano lo que cambió — no hay sincronización automática.
- `styles.scss` — se mantiene como referencia legible (variables de tema, comentarios), pero **ya no se
  compila automáticamente**. El CSS real que sirve el sitio es `assets/styles.css`, ya compilado
  (Bootstrap `darkly` + este SCSS, fusionados una sola vez). Para cambiar el tema: edita `styles.css`
  directamente (es CSS plano, no minificado más allá de lo que ya traía), o instala Dart Sass
  una vez para recompilar `styles.scss` y pega el resultado en `styles.css`.
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

`_site/` se copia tal cual a la rama `gh-pages` del repo (o del fork), que sirve el sitio vía GitHub
Pages. No hay CI que lo automatice todavía — es un paso manual después de correr `build.py` y revisar el
resultado.

## Búsqueda

El panel de búsqueda (ícono en el navbar) usa [Fuse.js](https://www.fusejs.io/) contra un `search.json`
que `build.py` genera automáticamente a partir del texto visible de cada página (`<main>` únicamente, sin
navbar/footer). No requiere ningún paso manual.

## Desarrollo local

```bash
cd web/_site
python -m http.server 8000
```

Y abre `http://localhost:8000/index.html`. Sirve el sitio como HTTP real (no `file://`) porque la
búsqueda hace `fetch()` contra `search.json`, que el navegador bloquea por CORS si abres el HTML
directamente desde el disco.
