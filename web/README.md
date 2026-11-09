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
  descripción del decorador y docstring) de todos los tools públicos registrados en `../tools/*.py`
  (no incluye las de mantenimiento), generada por `scripts/extract_tool_signatures.py` (un script `ast`,
  no a mano; el workflow de Pages lo corre en cada build). Es la fuente de verdad de qué tools existen y
  qué parámetros tienen: `build.py` descarta de `tools.json` los tools que ya no existen, sincroniza sus
  parámetros con el código y muestra los tools nuevos en una categoría aparte, en inglés, hasta que se
  traduzcan a mano `description`/`long_description`/`params` en `data/tools.json` y `en/data/tools.json`.
- `assets/og-image.png` — imagen social, regenerada con los conteos de `data/` por `scripts/make_og_image.py` (`uv run --with pillow python scripts/make_og_image.py`).
- `assets/site.css` (global: paleta blanca + acentos de la bandera, header, footer, páginas internas),
  `assets/home.css` (solo la home) y `assets/atlas.css` (solo la Referencia): CSS propio en texto plano;
  edítalos directamente. No hay Bootstrap ni modo oscuro. Las fuentes de Google Fonts (Inter, Playfair
  Display, Source Serif 4, IBM Plex Mono) se cargan con un `<link>` en `templates/base.html`.
- `assets/home.js` — comportamiento de la home (mapa, búsqueda real sobre el catálogo, terminal con
  transcripts, explorador de fuentes, respuestas guardadas, tabs de clientes, carrusel). Lee todo de un
  JSON embebido (`#home-data`) que arma `build.py` desde `data/*.json`; no tiene datos propios.
- `assets/site.js` — navbar móvil, panel de búsqueda del sitio y botón de copiar; `assets/fuse.min.js`
  (vendored) es el motor de esa búsqueda.

### Datos de la home

- `data/sources.json` — fuentes por tema/institución; cada tema lleva su `color` (el del punto en el mapa).
  De aquí salen los conteos (fuentes, temas, en línea), el mapa y el explorador.
- `data/ecuador_provinces.json` — geometría de las provincias continentales (rutas SVG ya proyectadas;
  fuente: geoBoundaries, CC BY 4.0, simplificada, sin Galápagos). `build.py` dibuja el mapa y reparte un
  punto por fuente de forma determinista; la posición es ilustrativa.
- `data/stored_answers.json` (+ `en/data/`) — preguntas con respuestas reales guardadas, con
  `extracted_at` y `server_version`. Al refrescarlas, actualiza esos dos campos y los textos; no cambies
  cifras al traducir.
- `data/transcripts.json` (+ `en/data/`) — los ejemplos de la terminal (llamadas reales a tools). Un paso
  con `"kind": "reason"` no es una llamada a una tool y se muestra en cursiva gris.
- `data/search_lexicon.json` (+ `en/data/`) — palabras vacías, sinónimos y enlaces a ejemplos de la
  búsqueda del hero (sin acentos ni mayúsculas).
- `data/clients.json` — snippets por cliente MCP; los `featured` son las pestañas de la home, el resto
  va en "Otros clientes". `alt` documenta la variante remota/HTTP por separado.
- `data/org_logos.json` — logos del carrusel del backstage.

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

El workflow no usa el despliegue de "GitHub Actions" de Pages: publica el contenido de `_site/` en la rama
`gh-pages` y Pages la sirve con **Settings → Pages → Source → Deploy from a branch** (`gh-pages`, raíz).
No borres la rama `gh-pages`.

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

