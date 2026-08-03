# Ecuador MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)

**Servidor MCP (Model Context Protocol) que permite a chatbots de IA (Claude, ChatGPT, Gemini, Cursor, etc.) buscar, explorar y analizar datos abiertos del gobierno de Ecuador, directamente por conversación.**

En lugar de navegar manualmente por portales gubernamentales, simplemente pregunta cosas como:
- *"¿Qué datos tiene el SRI sobre recaudación tributaria?"*
- *"Muéstrame los datasets de salud del INEC"*
- *"¿Cuáles son los requisitos para sacar el pasaporte?"*
- *"Dame un preview de los datos de transporte aéreo"*

---

## Beneficios

- **Acceso instantáneo a datos públicos**: Pregunta en lenguaje natural y obtén datos de 98 instituciones del Estado ecuatoriano sin navegar portales, descargar archivos ni lidiar con formatos.
- **Unifica múltiples fuentes en un solo punto**: Datos abiertos (CKAN), trámites gubernamentales (gob.ec) y categorías temáticas, todo accesible desde una sola conversación con tu IA.
- **Preview de datos sin descargas**: La herramienta `preview_resource_data` descarga y parsea archivos CSV en memoria para que el LLM pueda "ver" los datos y responder preguntas sobre ellos, sin que tú descargues nada.
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

Este MCP unifica **3 fuentes gubernamentales** en un solo servidor:

| Fuente | Datos | Cobertura |
|--------|-------|-----------|
| **Datos Abiertos** (CKAN) | 1,581 datasets de 98+ instituciones | www.datosabiertos.gob.ec |
| **Trámites** (Gob.ec) | Procedimientos gubernamentales, requisitos, costos | gob.ec/api/v1 |
| **Categorías temáticas** | 18 categorías: Salud, Educación, Economía, etc. | Portal de datos abiertos |

**Sin API key. Sin restricciones de acceso. 100% datos públicos.**

---

## Conecta tu chatbot al servidor MCP

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
| `LOG_LEVEL` | Nivel de log (DEBUG, INFO, WARNING, ERROR) | `INFO` |

---

## Herramientas disponibles (11 tools)

### Datos Abiertos (5 tools)

| Tool | Descripción |
|------|-------------|
| `search_datasets` | Buscar datasets por palabras clave entre los 1,581 del catálogo. Soporta filtro por categoría. |
| `get_dataset_info` | Metadata detallada de un dataset: título, descripción, organización, tags, licencia, fechas. |
| `list_dataset_resources` | Listar todos los archivos (recursos) de un dataset con formato, tamaño y URL. |
| `get_resource_info` | Información detallada de un archivo específico. |
| `preview_resource_data` | **Descarga un CSV y muestra las primeras filas como tabla.** Permite al LLM "ver" los datos sin que descargues nada. |

### Trámites Gubernamentales (3 tools)

| Tool | Descripción |
|------|-------------|
| `search_tramites` | Buscar trámites del gobierno ecuatoriano (cédula, pasaporte, RUC, licencia, etc.) |
| `get_tramite_info` | Detalle completo: requisitos, procedimiento, costo, tiempo estimado. |
| `list_instituciones` | Listar instituciones públicas del Ecuador con sus datos de contacto. |

### Exploración (3 tools)

| Tool | Descripción |
|------|-------------|
| `search_organizations` | Buscar entre 98+ instituciones que publican datos (INEC, SRI, BCE, MSP, etc.) |
| `get_organization_info` | Info de una organización con listado de todos sus datasets. |
| `list_categories` | Las 18 categorías temáticas: Salud, Educación, Economía, Seguridad, Anticorrupción, etc. |

### Flujo de trabajo típico

```
1. search_datasets("recaudación tributaria")     → Encuentra datasets del SRI
2. list_dataset_resources("dataset-id")           → Ve los archivos disponibles
3. preview_resource_data("resource-id")           → Mira los datos en una tabla
```

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
│   ├── search_datasets        │
│   ├── get_dataset_info       │  → helpers/ckan_client.py → CKAN API (www.datosabiertos.gob.ec)
│   ├── list_dataset_resources │
│   ├── get_resource_info      │
│   ├── preview_resource_data  │  → helpers/csv_reader.py  → Descarga directa CSV
│   ├── search_organizations   │
│   ├── get_organization_info  │
│   ├── list_categories        │
│   ├── search_tramites        │
│   ├── get_tramite_info       │  → helpers/gobec_client.py → Gob.ec API
│   └── list_instituciones     │
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
