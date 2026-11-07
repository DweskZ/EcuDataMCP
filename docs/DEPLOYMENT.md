# Despliegue remoto

El servidor puede seguir ejecutándose localmente con `stdio` o HTTP. Para
exponerlo a agentes remotos, el despliegue debe tener:

- `MCP_REQUIRE_AUTH=1` y un `MCP_AUTH_TOKEN` largo, secreto y rotado fuera del
  repositorio.
- `MCP_RATE_LIMIT_REQUESTS` y `MCP_RATE_LIMIT_WINDOW_SECONDS` configurados para
  la capacidad real del servidor. El límite se aplica por dirección del cliente
  que ve Uvicorn, además del límite global de concurrencia. Detrás de un proxy
  inverso, define `FORWARDED_ALLOW_IPS` (variable nativa de Uvicorn) con la
  dirección del proxy: por defecto solo confía en `127.0.0.1`, e ignora
  `X-Forwarded-For` de cualquier otro origen, así que todos los clientes
  compartirían un único cupo.
- HTTPS terminado en un proxy como Caddy/Nginx, o `MCP_SSL_CERTFILE` y
  `MCP_SSL_KEYFILE` si Uvicorn termina TLS directamente.
- almacenamiento persistente para `/app/data` en Docker, health check para
  `/health`, y reinicio automático.

El `docker-compose.yml` deja `MCP_REQUIRE_AUTH=1` por defecto. Si falta el
token, el proceso se detiene con un error claro en vez de dejar un MCP remoto
sin autenticación.

Para un despliegue remoto, considerar `MCP_PROFILE=public` en el servicio
`mcp` expuesto — deja fuera `audit_bce_catalog` y `compare_bce_sources`
(escriben snapshots/reportes locales, no son una consulta de solo lectura)
— y levantar el servicio `mcp-maintenance` (mismo `docker-compose.yml`, bajo
`docker compose --profile maintenance up`) solo cuando el operador
necesite correrlos, en su propio puerto y `MCP_MAINTENANCE_AUTH_TOKEN`. Ver
docs/MCP_ARCHITECTURE.md § Fase 1.

Ejemplo mínimo detrás de un proxy HTTPS:

```text
Internet HTTPS
    |
    v
Proxy TLS (Caddy/Nginx) ---> http://mcp:8000/mcp
                                  |
                                  +--> /health
```

El proxy debe reenviar únicamente `/mcp` y `/health`, bloquear cualquier ruta
administrativa que no sea necesaria y aplicar su propio límite por IP si conoce
la IP original del cliente. El límite interno sigue siendo útil como segunda
capa.

Para una prueba local del modo HTTP protegido:

```powershell
$env:MCP_AUTH_TOKEN = "un-token-de-prueba"
$env:MCP_REQUIRE_AUTH = "1"
uv run python main.py --host 127.0.0.1
```

Este repositorio deja preparado el proceso y su configuración, pero no crea
una instancia pública ni administra DNS, certificados, secretos o facturación.

## Instancia pública en Render

La instancia pública corre en Render (plan gratuito, Oregon), servicio
`ecuador-mcp` del workspace `ecuador-mcp`:
`https://ecuador-mcp-lb0s.onrender.com/mcp` (`/health` para el estado). Se
construye con el `Dockerfile` desde la rama `main` del fork
`dsanchezp18/EcuDataMCP`. En el plan gratuito el servicio se suspende tras
unos 15 minutos sin tráfico, y la primera petición después tarda cerca de un
minuto. Tampoco hay disco persistente, así que la base de financieros de
Supercías se reconstruye tras cada reinicio.

**Alcance por origen (2026-11-04).** Se probaron 57 URLs de fuentes, una
petición por URL y por origen. Resultados:

| Origen | URLs que respondieron (de 57) |
|---|---|
| VPN con salida en Ecuador | 52 |
| Render Oregon | 47 |
| Azure, las nueve regiones de EE. UU. | 44-45 |
| Azure Mexico Central y Chile Central | 44 |
| Conexión residencial en Canadá (Shaw, Edmonton) | 41 |
| Azure Canada Central y Canada East | 38-39 |
| Azure Brazil South | 34 |

Hallazgos:

- **Render frente a Azure EE. UU.:** Render llega además a
  `www.igepn.edu.ec` y CNE, que devuelven 403 a todas las regiones de Azure.
- **IP de Canadá, residencial o de centro de datos:** no llegan a Supercías,
  SERCOP, SIGTIERRAS, el Ministerio del Trabajo ni el CKAN de Cuenca.
- **IP de Latinoamérica:** solo Mexico y Chile (y la VPN) llegan a ANDA y a
  `censoecuador.gob.ec`, pero desde ahí no responden el Ministerio del Trabajo
  ni el CKAN de Cuenca, y Emelnorte devuelve 418.
- **Brazil South** es el peor origen: además no llega a `www.gob.ec`, MSP, la
  SGR, ARCSA, MEF/MDEP, Ambiente y Energía ni CNIG.
- **Solo desde la VPN:** infoMIES, SEPS y MINEDEC. Hace falta
  `ECUADOR_MCP_GEO_PROXY` con salida en Ecuador.
- **Fallan desde todos los orígenes:** `evaluaciones.evaluacion.gob.ec`
  (INEVAL BI) cierra el handshake TLS. `reportes.arconel.gob.ec` responde
  "Error en runtime" (500) o no responde.

Una instancia en Azure Container Apps (Brazil South, luego East US) funcionó
el 2026-11-04 y se retiró el mismo día. Costaba unos 25-40 USD al mes y no
llegaba a más fuentes que Render.

## Variables de entorno

Lista completa de lo que lee el código (`helpers/env_config.py`,
`helpers/paths.py`, `helpers/geo_proxy.py`, `helpers/tls.py`,
`helpers/usage.py` y los stores del BCE). README.md muestra solo las más
usadas; `.env.example` trae las mismas variables listas para copiar. Ninguna
es obligatoria salvo `MCP_AUTH_TOKEN` cuando `MCP_REQUIRE_AUTH=1`.

### Servidor

| Variable | Descripción | Default |
|----------|-------------|---------|
| `MCP_HOST` | Dirección de bind. `docker-compose.yml` la fija en `0.0.0.0` | `127.0.0.1` |
| `MCP_PORT` | Puerto del servidor HTTP (`--port` lo sobreescribe) | `8000` |
| `MCP_TRANSPORT` | `http` o `stdio` (`--transport` lo sobreescribe). La imagen Docker arranca en `stdio` | `http` |
| `MCP_PROFILE` | `public` (84 tools), `maintenance` (solo `audit_bce_catalog` y `compare_bce_sources`) o `all` | `public` |
| `LOG_LEVEL` | Nivel de log de Python: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `MCP_AUTH_TOKEN` | Token Bearer exigido en `POST /mcp`; vacío desactiva la autenticación | vacío |
| `MCP_REQUIRE_AUTH` | `1` aborta el arranque si falta `MCP_AUTH_TOKEN`; `docker-compose.yml` lo deja en `1` | `0` |
| `MCP_MAX_CONCURRENT_REQUESTS` | Tope global de peticiones MCP y descargas simultáneas (1–256) | `8` |
| `MCP_RATE_LIMIT_REQUESTS` | Peticiones por cliente/IP dentro de la ventana; `0` desactiva el límite | `120` |
| `MCP_RATE_LIMIT_WINDOW_SECONDS` | Ventana del límite anterior, en segundos (1–3600) | `60` |
| `MCP_SSL_CERTFILE` / `MCP_SSL_KEYFILE` | Certificado y clave PEM si Uvicorn termina TLS directamente | vacío |
| `FORWARDED_ALLOW_IPS` | Variable de Uvicorn: proxies cuyo `X-Forwarded-For` se acepta como IP real del cliente | `127.0.0.1` |

`docker-compose.yml` añade `MCP_MAINTENANCE_PORT` (`8001`) y
`MCP_MAINTENANCE_AUTH_TOKEN` para el servicio `mcp-maintenance`; se traducen a
`MCP_PORT` y `MCP_AUTH_TOKEN` dentro de ese contenedor, el código no las lee.

### Datos en disco

| Variable | Descripción | Default |
|----------|-------------|---------|
| `ECUADOR_MCP_DATA_DIR` | Directorio de datos escritos en tiempo de ejecución (base SQLite de Supercías, snapshots, `usage.jsonl`) | `data/` en un clon; `%LOCALAPPDATA%\ecuador-mcp`, `~/Library/Application Support/ecuador-mcp` o `$XDG_DATA_HOME/ecuador-mcp` instalado desde PyPI |
| `BCE_CATALOG_SNAPSHOT_DIR` | Snapshots del catálogo BCEData que escribe `audit_bce_catalog` | `<data_dir>/bce_catalog_snapshots` |
| `BCE_EQUIVALENCE_REVIEW_DIR` | Mapas de equivalencia que escribe `compare_bce_sources` | `<data_dir>/bce_equivalence_reviews` |
| `IEM_CATALOG_DIR` | Catálogo IEM persistido para inspección | `<data_dir>/iem_catalog_snapshots` |
| `ECUADOR_MCP_DISK_CACHE` | `0` deja todos los cachés en memoria; con `1` los catálogos caros se guardan en `<data_dir>/cache/` y sobreviven reinicios, y una copia vencida (hasta 7 días) responde, marcada `frescura: "obsoleta"`, cuando su fuente falla | `1` |
| `ECUADOR_MCP_MAX_RESPONSE_BYTES` | Tope de bytes del `structuredContent` de cualquier tool; pasado el tope se recorta la lista principal y se declara en `metadatos.truncado` | `200000` |
| `ECUADOR_MCP_USAGE_LOG` | `1` guarda cada llamada (tool, resultado, duración; nunca argumentos) en `<data_dir>/usage.jsonl`; `scripts/usage_report.py` lo resume | vacío |

### Geobloqueo y TLS

| Variable | Descripción | Default |
|----------|-------------|---------|
| `ECUADOR_MCP_GEO_PROXY` | URL `http://`, `https://` o `socks5://` de un egress dentro de LatAm por el que salen las peticiones a los hosts geobloqueados (ver [GEOBLOCK_PLAN.md](GEOBLOCK_PLAN.md)) | vacío (conexión directa) |
| `ECUADOR_MCP_GEO_HOSTS` | Lista separada por comas de hosts que usan ese proxy; sustituye la lista por defecto de `helpers/geo_proxy.py` (datosabiertos.gob.ec, www.gob.ec, ANDA, ARCONEL, SERCOP, Supercías, …) | lista interna |
| `ECUADOR_MCP_HIDE_GEOBLOCKED` | `1` retira de `tools/list` las tools cuya única fuente rechaza tráfico fuera de la región (ANDA y Supercías) cuando no hay proxy | vacío |
| `CKAN_INSECURE_TLS` | `1` permite un único reintento sin verificar TLS contra los portales de datos abiertos en la lista de `helpers/tls.py`, solo ante un error real de certificado | `0` |

### URLs base de las fuentes

Cada par `*_API_URL` / `*_SITE_URL` sustituye la API y el sitio de una
fuente (`helpers/env_config.py`); sirven para apuntar a un mirror o a un
entorno de pruebas.

| Variable | Fuente | Default |
|----------|--------|---------|
| `CKAN_API_URL` / `CKAN_SITE_URL` | Portal nacional de datos abiertos | `https://www.datosabiertos.gob.ec/api/3/action/` / `https://www.datosabiertos.gob.ec/` |
| `CUENCA_API_URL` / `CUENCA_SITE_URL` | CKAN municipal de Cuenca | `https://cuencaendatos.cuenca.gob.ec/api/3/action/` / `https://cuencaendatos.cuenca.gob.ec/` |
| `LATACUNGA_API_URL` / `LATACUNGA_SITE_URL` | CKAN municipal de Latacunga | `https://datosabiertos.latacunga.gob.ec/api/3/action/` / `https://datosabiertos.latacunga.gob.ec/` |
| `IADB_API_URL` / `IADB_SITE_URL` | CKAN del BID | `https://data.iadb.org/api/3/action/` / `https://data.iadb.org/` |
| `ANDA_API_URL` / `ANDA_SITE_URL` | ANDA (microdatos INEC, NADA) | `https://anda.inec.gob.ec/anda5/index.php/api/` / `https://anda.inec.gob.ec/anda5/` |
| `GOBEC_API_URL` / `GOBEC_SITE_URL` | gob.ec (trámites, instituciones, regulaciones) | `https://www.gob.ec/api/v1/` / `https://www.gob.ec/` |
| `SERCOP_API_URL` / `SERCOP_SITE_URL` | SERCOP datos abiertos (contratación pública) | `https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/` / `https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/` |

### Solo CI

`.github/workflows/smoke.yml` lee los secretos `GEO_SSH_KEY`, `GEO_SSH_HOST` y
`GEO_SSH_KNOWN_HOSTS` para abrir el túnel SOCKS que alimenta
`ECUADOR_MCP_GEO_PROXY`; los tres son obligatorios en conjunto (sin
`GEO_SSH_KNOWN_HOSTS` el paso falla, nunca acepta una clave de host sin
verificar). `scripts/smoke_e2e.py` escribe su resumen en
`GITHUB_STEP_SUMMARY` cuando existe.
