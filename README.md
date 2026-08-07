# Ecuador MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)

**Servidor MCP (Model Context Protocol) que permite a chatbots de IA (Claude, ChatGPT, Gemini, Cursor, etc.) buscar, explorar y analizar datos abiertos del gobierno de Ecuador, directamente por conversación.**

> Este repositorio es un fork de [DweskZ/EcuDataMCP](https://github.com/DweskZ/EcuDataMCP).

En lugar de navegar manualmente por portales gubernamentales, simplemente pregunta cosas como:
- *"¿Qué datos tiene el SRI sobre recaudación tributaria?"*
- *"Muéstrame los datasets de salud del INEC"*
- *"¿Cuáles son los requisitos para sacar el pasaporte?"*
- *"Dame un preview de los datos de transporte aéreo"*

---

## Beneficios

- **Acceso instantáneo a datos públicos**: Pregunta en lenguaje natural y obtén datos de 98 instituciones del Estado ecuatoriano sin navegar portales, descargar archivos ni lidiar con formatos.
- **Unifica múltiples fuentes en un solo punto**: Datos abiertos (CKAN), trámites gubernamentales (gob.ec) y categorías temáticas, todo accesible desde una sola conversación con tu IA.
- **Preview de datos sin descargas**: `preview_resource_data` parsea CSV/TSV, JSON/GeoJSON y XLSX en memoria; `query_resource_data` consulta el DataStore CKAN sin bajar el archivo completo.
- **Cero fricción**: No necesitas API key, no necesitas cuenta, no necesitas permisos especiales. 100% datos públicos bajo licencia abierta.
- **Compatible con cualquier cliente MCP**: Claude, ChatGPT, Gemini, Cursor, VS Code, Windsurf, Le Chat, HuggingChat y más.
- **Listo para producción**: Docker, health checks, logging estructurado, y un servidor HTTP Streamable que sigue la especificación MCP al pie de la letra.

---

## Casos de uso

### Para ciudadanos
- Consultar requisitos, costos y pasos de cualquier trámite gubernamental sin navegar gob.ec.
- Buscar datos públicos por tema (salud, educación, seguridad, economía) y entender qué publica cada institución.

### Para periodistas e investigadores
- Explorar los 1,581 datasets del catálogo nacional y hacer preview de los datos directamente desde Claude o ChatGPT.
- Cruzar información de múltiples instituciones (SRI, INEC, Ministerios) en una sola conversación.
- Acceder rápidamente a datos de anticorrupción, presupuestos y ejecución del gasto público.

### Para desarrolladores
- Integrar datos abiertos de Ecuador en aplicaciones mediante el protocolo MCP estándar.
- Prototipar dashboards y análisis exploratorios sin escribir código de scraping ni parseo de CSV.
- Usar como backend de datos para agentes de IA que necesiten contexto sobre Ecuador.

### Para el sector público
- Hacer más accesibles y descubribles los datos que ya publican las instituciones.
- Permitir que chatbots institucionales respondan preguntas con datos reales y actualizados.
- Demostrar el valor de los datos abiertos conectándolos directamente con herramientas de IA.

---

## Fuentes de datos

Este MCP unifica **fuentes gubernamentales** en un solo servidor:

| Fuente | Datos | Cobertura |
|--------|-------|-----------|
| **Datos Abiertos** (CKAN) | Catálogo nacional + DataStore + preview CSV/JSON/XLSX | www.datosabiertos.gob.ec |
| **Trámites e instituciones** (Gob.ec) | Procedimientos, requisitos, costos | gob.ec/api/v1 |
| **Regulaciones** (Gob.ec) | Normas, acuerdos, Registro Oficial | gob.ec/api/v1/regulaciones |
| **Contratos públicos** (SERCOP/OCDS) | Licitaciones, compradores, proveedores | datosabiertos.compraspublicas.gob.ec |
| **Gestión de Riesgos** (SGR) | Eventos COE + estaciones SAT tsunami | sgrportal.gestionderiesgos.gob.ec |
| **Geografía** (DPA) | 24 provincias + 224 cantones (códigos INEC) | referencia offline |

**Sin API key. Sin restricciones de acceso. 100% datos públicos.**

---

## Conecta tu chatbot al servidor MCP

### Opción rápida: pídeselo a tu IA

Si usas un asistente con acceso a la terminal (Claude Code, Cursor, Windsurf, etc.), puedes pegarle este prompt y dejar que él mismo clone el repo, instale las dependencias y edite la configuración de tu cliente MCP:

```
Clona https://github.com/DweskZ/EcuDataMCP, instala sus dependencias con uv sync,
y regístralo como servidor MCP en mi cliente (Claude Desktop / Claude Code / Cursor)
usando modo stdio con `uv run --directory <ruta-del-clon> python main.py --transport stdio`.
Verifica que el servidor responda antes de darlo por terminado.
```

Revisa siempre lo que tu asistente cambie (archivos de configuración, comandos ejecutados) antes de confirmar.

### Manual

### Claude Desktop

Agrega lo siguiente a tu archivo de configuración de Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json` en macOS, `%APPDATA%\Claude\claude_desktop_config.json` en Windows):

```json
{
  "mcpServers": {
    "ecuador-datos": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://localhost:8000/mcp"
      ]
    }
  }
}
```

### Cursor

1. Abre Cursor Settings
2. Busca "MCP"
3. Agrega un nuevo servidor MCP:

```json
{
  "mcpServers": {
    "ecuador-datos": {
      "url": "http://localhost:8000/mcp",
      "transport": "http"
    }
  }
}
```

### VS Code

Agrega a tu archivo `mcp.json` (ejecuta **MCP: Open User Configuration** desde la paleta de comandos):

```json
{
  "servers": {
    "ecuador-datos": {
      "url": "http://localhost:8000/mcp",
      "type": "http"
    }
  }
}
```

### ChatGPT

*Disponible para planes pagos (Plus, Pro, Team, Enterprise).*

1. Ve a `Settings` > `Apps and connectors`
2. Abre `Advanced settings` y habilita **Developer mode**
3. En `Settings` > `Connectors` > `Browse connectors`, haz clic en **Add a new connector**
4. Configura la URL: `http://localhost:8000/mcp`

### Claude Code

```bash
claude mcp add --transport http ecuador-datos http://localhost:8000/mcp
```

### Gemini CLI

Agrega a `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "ecuador-datos": {
      "httpUrl": "http://localhost:8000/mcp"
    }
  }
}
```

### Le Chat (Mistral)

1. Ve a `Intelligence` > `Connectors`
2. `Add connector` > `Custom MCP Connector`
3. Nombre: "Ecuador Datos" / URL: `http://localhost:8000/mcp`

### Windsurf

Agrega a `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "ecuador-datos": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://localhost:8000/mcp"]
    }
  }
}
```

### HuggingChat

1. En el chat, haz clic en el ícono `+` > `MCP Servers` > `Manage MCP Servers`
2. `Add Server` con nombre "Ecuador Datos" y URL `http://localhost:8000/mcp`

---

## Ejecutar localmente

### Con Docker (recomendado)

```bash
git clone https://github.com/DweskZ/EcuDataMCP.git
cd EcuDataMCP

# Iniciar con configuración por defecto (puerto 8000)
docker compose up -d

# Con variables personalizadas
MCP_PORT=8007 LOG_LEVEL=DEBUG docker compose up -d

# Detener
docker compose down
```

### Instalación manual

Requiere Python 3.11+ y [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/DweskZ/EcuDataMCP.git
cd EcuDataMCP

# Instalar dependencias
uv sync

# Copiar variables de entorno
cp .env.example .env

# Iniciar el servidor
uv run main.py
```

**Variables de entorno:**

| Variable | Descripción | Default |
|----------|-------------|---------|
| `MCP_HOST` | Dirección de bind | `0.0.0.0` |
| `MCP_PORT` | Puerto del servidor | `8000` |
| `MCP_TRANSPORT` | Transporte: `http` o `stdio` | `http` |
| `LOG_LEVEL` | Nivel de log (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `CKAN_INSECURE_TLS` | Reintento TLS inseguro solo para el portal de datos (`1`/`0`) | `1` |

Stdio local:

```bash
uv run python main.py --transport stdio
```

---

## Herramientas disponibles (24 tools)

Casi todos los tools aceptan `format="json"` además de texto.

### Entrada unificada

| Tool | Descripción |
|------|-------------|
| `list_capabilities` | Resume fuentes, tools, prompts y límites del servidor. |
| `search_ecuador` | Busca a la vez en datasets, orgs, trámites, regulaciones, contratos y riesgos. |
| `lookup_ubicacion` | Provincias, cantones y parroquias (código INEC, región, población). |

### Datos Abiertos

| Tool | Descripción |
|------|-------------|
| `search_datasets` | Buscar datasets por palabras clave. Soporta filtro por categoría. |
| `list_recent_datasets` | Datasets más recientemente actualizados en el portal. |
| `get_dataset_info` | Metadata detallada de un dataset: título, descripción, organización, tags, licencia, fechas. |
| `list_dataset_resources` | Listar todos los archivos (recursos) de un dataset con formato, tamaño y URL. |
| `get_resource_info` | Información detallada de un archivo específico. |
| `preview_resource_data` | Preview de CSV/TSV, JSON/GeoJSON o XLSX como tabla (máx. 5 MB). |
| `query_resource_data` | Consulta tabular vía CKAN DataStore (filtros, texto, paginación) sin descargar el archivo. |

### Trámites Gubernamentales

| Tool | Descripción |
|------|-------------|
| `search_tramites` | Buscar trámites del gobierno ecuatoriano (cédula, pasaporte, RUC, licencia, etc.) |
| `get_tramite_info` | Detalle completo: requisitos, procedimiento, costo, tiempo estimado. |
| `list_instituciones` | Listar instituciones públicas del Ecuador. |
| `get_institucion_info` | Detalle de una institución (sector, web, descripción). |

### Regulaciones y contratos

| Tool | Descripción |
|------|-------------|
| `search_regulaciones` | Buscar/listar regulaciones en gob.ec (con ref. Registro Oficial). |
| `get_regulacion_info` | Detalle de una regulación + enlace al PDF. |
| `search_contratos` | Buscar procedimientos de contratación pública (SERCOP/OCDS). |
| `get_contrato_info` | Expediente OCDS: comprador, licitación, adjudicaciones, contratos. |

### Riesgos (SGR)

| Tool | Descripción |
|------|-------------|
| `search_eventos_riesgo` | Eventos de emergencia/riesgo del COE (deslizamientos, inundaciones, etc.). |
| `list_sat_tsunami` | Estaciones SAT de alerta temprana por tsunami. |

### Exploración

| Tool | Descripción |
|------|-------------|
| `search_organizations` | Buscar entre 98+ instituciones que publican datos (INEC, SRI, BCE, MSP, etc.) |
| `get_organization_info` | Info de una organización con listado de sus datasets. |
| `list_categories` | Categorías temáticas con conteo de datasets. |
| `get_category_info` | Detalle de una categoría y datasets de ejemplo. |

### Flujo de trabajo típico

```
1. search_ecuador("recaudación tributaria")       → Orientación rápida
2. list_dataset_resources("dataset-id")           → Ve los archivos disponibles
3. query_resource_data("resource-id", query=...)  → Consulta tabular (DataStore)
   # o preview_resource_data("resource-id")       → Preview del archivo
```

### Prompts MCP

Plantillas listas para el cliente (Claude/Cursor): `explorar_datos`, `consultar_tramite`, `investigar_contrato`, `buscar_regulacion`, `monitorear_riesgos`.

### Resources MCP

| URI | Contenido |
|-----|-----------|
| `ecuador://fuentes` | Fuentes integradas y tools asociadas |
| `ecuador://provincias` | 24 provincias (JSON) |
| `ecuador://cantones` | 224 cantones (JSON) |
| `ecuador://parroquias` | ~1040 parroquias (JSON) |
| `ecuador://instituciones-clave` | IDs frecuentes de gob.ec (SRI, IESS, etc.) |

---

## Endpoints

| Endpoint | Descripción |
|----------|-------------|
| `POST /mcp` | Mensajes JSON-RPC (cliente → servidor) |
| `GET /health` | Health check: `{"status":"ok","uptime_since":"...","version":"..."}` |

---

## Ejemplos de uso

### Buscar datos del SRI

> "¿Qué datos tiene el SRI sobre recaudación?"

El MCP buscará en los 114 datasets del SRI y te mostrará los resultados con títulos, descripciones y enlaces.

### Ver datos de salud

> "Muéstrame un preview de los datos de hospitales"

El MCP descargará el CSV y te mostrará las primeras filas como una tabla formateada.

### Consultar trámites

> "¿Cuáles son los requisitos para obtener el RUC?"

El MCP buscará en el portal gob.ec y te dará los requisitos, procedimiento y costo.

### Explorar por categoría

> "¿Qué categorías de datos hay disponibles?"

El MCP listará las 18 categorías temáticas con el conteo de datasets en cada una.

---

## Arquitectura

```
Cliente MCP (Claude, ChatGPT, Cursor, etc.)
    │
    ▼ POST /mcp
┌──────────────────────────────┐
│   FastMCP Server (main.py)   │
├──────────────────────────────┤
│  tools/                      │
│   ├── search_ecuador         │  → CKAN + gob.ec (unificado)
│   ├── search_datasets        │
│   ├── query_resource_data    │  → CKAN DataStore
│   ├── preview_resource_data  │  → CSV / JSON / XLSX
│   ├── get_category_info      │  → helpers/ckan_client.py
│   ├── search_tramites        │
│   ├── get_institucion_info   │  → helpers/gobec_client.py
│   └── ...                    │
└──────────────────────────────┘
```

---

## Licencia

MIT License - ver [LICENSE](LICENSE) para más detalles.

---

## Contribuir

Contribuciones son bienvenidas. Por favor:

1. Fork el repositorio
2. Crea tu feature branch (`git checkout -b feature/nueva-herramienta`)
3. Haz commit de tus cambios (`git commit -m 'feat: agregar nueva herramienta'`)
4. Push a la branch (`git push origin feature/nueva-herramienta`)
5. Abre un Pull Request
