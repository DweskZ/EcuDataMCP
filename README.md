# EcuDataMCP

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)

**Infraestructura abierta de datos públicos para Ecuador.** EcuDataMCP conecta asistentes de IA, investigadores, periodistas y software con datos oficiales ecuatorianos mediante una interfaz común.

Utiliza el Model Context Protocol (MCP) para que clientes compatibles como Claude, ChatGPT, Gemini y Cursor puedan buscar, explorar y analizar esos datos mediante conversación o software.

En lugar de navegar manualmente por portales gubernamentales, simplemente pregunta cosas como:
- *"¿Qué datos tiene el SRI sobre recaudación tributaria?"*
- *"Muéstrame los datasets de salud del INEC"*
- *"¿Cuáles son los requisitos para sacar el pasaporte?"*
- *"Dame un preview de los datos de transporte aéreo"*

> **Aviso:** Las definiciones, parámetros y descripciones de algunas
> herramientas fueron generadas o asistidas por IA y pueden estar incompletas,
> desactualizadas o no cubrir todos los casos del endpoint subyacente. Una
> herramienta puede devolver resultados parciales, rechazar parámetros válidos
> o comportarse de forma inesperada cuando cambia la fuente oficial. Verifica
> siempre la respuesta contra la fuente enlazada y revisa manualmente los
> resultados antes de usarlos para decisiones importantes.

---

## Documentación del proyecto

- **[ROADMAP.md](ROADMAP.md)** — qué fuentes están integradas y qué falta.
- **[RESEARCH.md](RESEARCH.md)** — el porqué de cada fila del roadmap:
  hallazgos verificados en vivo, dominios investigados, dead ends.
- **[CHANGELOG.md](CHANGELOG.md)** — qué se publicó recientemente.

---

## Beneficios

- **Acceso instantáneo a datos públicos**: Pregunta en lenguaje natural y explora datos de instituciones del Estado ecuatoriano sin navegar portales, descargar archivos ni lidiar con formatos.
- **Unifica múltiples fuentes en un solo punto**: Datos abiertos, trámites, regulaciones, contratación pública, riesgos, datos estadísticos y otras fuentes oficiales, todo accesible desde una sola conversación con tu IA.
- **Preview de datos sin descargas**: `preview_resource_data` parsea CSV/TSV, JSON/GeoJSON, Excel (XLS/XLSX) y algunos archivos comprimidos en memoria; `query_resource_data` consulta el DataStore CKAN sin bajar el archivo completo.
- **Cero fricción**: No necesitas API key ni permisos especiales para las fuentes públicas compatibles.
- **Compatible con cualquier cliente MCP**: Claude, ChatGPT, Gemini, Cursor, VS Code, Windsurf, Le Chat, HuggingChat y más.
- **Listo para producción**: Docker, health checks, logging estructurado, y un servidor HTTP Streamable compatible con MCP.

---

## Casos de uso

### Para ciudadanos
- Consultar requisitos, costos y pasos de cualquier trámite gubernamental sin navegar gob.ec.
- Buscar datos públicos por tema (salud, educación, seguridad, economía) y entender qué publica cada institución.

### Para periodistas e investigadores
- Explorar datasets del catálogo nacional y hacer preview de los datos directamente desde Claude o ChatGPT.
- Cruzar información de múltiples instituciones (SRI, INEC, BCE y ministerios) en una sola conversación.
- Acceder rápidamente a datos de anticorrupción, presupuestos y ejecución del gasto público.

### Para desarrolladores
- Integrar datos abiertos de Ecuador en aplicaciones mediante el protocolo MCP estándar.
- Prototipar dashboards y análisis exploratorios sin escribir código de scraping ni parseo de archivos.
- Usar como backend de datos para agentes de IA que necesiten contexto sobre Ecuador.

### Para el sector público
- Hacer más accesibles y descubribles los datos que ya publican las instituciones.
- Permitir que chatbots institucionales respondan preguntas con datos reales y actualizados.
- Demostrar el valor de los datos abiertos conectándolos directamente con herramientas de IA.

---

## Fuentes de datos

Este MCP unifica fuentes gubernamentales en un solo servidor:

| Fuente | Datos |
|--------|-------|
| **Datos Abiertos y Cuenca en Datos** (CKAN) | Catálogos, DataStore y archivos públicos |
| **SRI** | Datasets estadísticos, recaudación, RUC y Saiku público |
| **Gob.ec** | Trámites, instituciones y regulaciones |
| **SERCOP/OCDS** | Contratación pública |
| **SGR e IG-EPN** | Eventos de riesgo, tsunami y sismos |
| **INEC** | ANDA, Ecuador en Cifras, censos y recursos estadísticos |
| **BCE** | BCEData, IEM y otros indicadores económicos públicos |
| **Superintendencia de Compañías** | Directorio, auditores y datos financieros |
| **Geografía INEC/DPA** | Provincias, cantones y parroquias |

**Sin API key para las fuentes públicas compatibles.**

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
| `MCP_HOST` | Dirección de bind | `127.0.0.1` |
| `MCP_PORT` | Puerto del servidor | `8000` |
| `MCP_TRANSPORT` | Transporte: `http` o `stdio` | `http` |
| `LOG_LEVEL` | Nivel de log (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `MCP_AUTH_TOKEN` | Token Bearer opcional para `/mcp` | vacío |
| `MCP_REQUIRE_AUTH` | Rechaza el arranque remoto sin token | `0` |
| `MCP_RATE_LIMIT_REQUESTS` / `MCP_RATE_LIMIT_WINDOW_SECONDS` | Cuota por cliente/IP | `120` / `60` |
| `MCP_SSL_CERTFILE` / `MCP_SSL_KEYFILE` | Certificado y clave para TLS directo | vacío |

Para ejecutar el transporte stdio localmente:

```bash
uv run python main.py --transport stdio
```

La referencia detallada de cada herramienta está en [docs/TOOLS.md](docs/TOOLS.md).
El contrato JSON para agentes de BCEData/IEM está en
[docs/RESPONSE_CONTRACT.md](docs/RESPONSE_CONTRACT.md).

---

## Endpoints

| Endpoint | Descripción |
|----------|-------------|
| `POST /mcp` | Mensajes JSON-RPC (cliente → servidor) |
| `GET /health` | Health check: `{"status":"ok","uptime_since":"...","version":"..."}` |

Cuando `MCP_AUTH_TOKEN` está definido, `POST /mcp` requiere el encabezado
`Authorization: Bearer <token>`. Para un despliegue remoto usa también
`MCP_REQUIRE_AUTH=1`, HTTPS y un proxy con su propia cuota por IP. `/health`
permanece sin autenticación para que Docker pueda comprobar el servicio.
Consulta [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) para el despliegue remoto.

---

## Ejemplos de uso

### Buscar datos del SRI

> "¿Qué datos tiene el SRI sobre recaudación?"

El MCP buscará los datos públicos del SRI y te mostrará los resultados con títulos, descripciones y enlaces.

### Ver datos de salud

> "Muéstrame un preview de los datos de hospitales"

El MCP descargará el archivo compatible y te mostrará las primeras filas como una tabla formateada.

### Consultar trámites

> "¿Cuáles son los requisitos para obtener el RUC?"

El MCP buscará en el portal gob.ec y te dará los requisitos, procedimiento y costo.

### Explorar por categoría

> "¿Qué categorías de datos hay disponibles?"

El MCP listará las categorías temáticas disponibles.

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
│   ├── preview_resource_data  │  → CSV / JSON / XLS / XLSX
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

Las contribuciones son bienvenidas. Consulta [CONTRIBUTING.md](CONTRIBUTING.md)
para el proceso de colaboración.
