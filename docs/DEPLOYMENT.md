# Despliegue remoto

El servidor puede seguir ejecutándose localmente con `stdio` o HTTP. Para
exponerlo a agentes remotos, el despliegue debe tener:

- `MCP_REQUIRE_AUTH=1` y un `MCP_AUTH_TOKEN` largo, secreto y rotado fuera del
  repositorio.
- `MCP_RATE_LIMIT_REQUESTS` y `MCP_RATE_LIMIT_WINDOW_SECONDS` configurados para
  la capacidad real del servidor. El límite se aplica por dirección del cliente
  que ve Uvicorn, además del límite global de concurrencia.
- HTTPS terminado en un proxy como Caddy/Nginx, o `MCP_SSL_CERTFILE` y
  `MCP_SSL_KEYFILE` si Uvicorn termina TLS directamente.
- almacenamiento persistente para `/app/data` en Docker, health check para
  `/health`, y reinicio automático.

El `docker-compose.yml` deja `MCP_REQUIRE_AUTH=1` por defecto. Si falta el
token, el proceso se detiene con un error claro en vez de dejar un MCP remoto
sin autenticación.

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
