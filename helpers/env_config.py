import os

_API_URLS = {
    "ckan": "https://www.datosabiertos.gob.ec/api/3/action/",
    "ckan_site": "https://www.datosabiertos.gob.ec/",
    "gobec": "https://www.gob.ec/api/v1/",
    "gobec_site": "https://www.gob.ec/",
    "sercop": "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/api/",
    "sercop_site": "https://datosabiertos.compraspublicas.gob.ec/PLATAFORMA/",
    "anda": "https://anda.inec.gob.ec/anda5/index.php/api/",
    "anda_site": "https://anda.inec.gob.ec/anda5/",
    "cuenca": "https://cuencaendatos.cuenca.gob.ec/api/3/action/",
    "cuenca_site": "https://cuencaendatos.cuenca.gob.ec/",
}

_ENV_OVERRIDES = {
    "ckan": "CKAN_API_URL",
    "ckan_site": "CKAN_SITE_URL",
    "gobec": "GOBEC_API_URL",
    "gobec_site": "GOBEC_SITE_URL",
    "sercop": "SERCOP_API_URL",
    "sercop_site": "SERCOP_SITE_URL",
    "anda": "ANDA_API_URL",
    "anda_site": "ANDA_SITE_URL",
    "cuenca": "CUENCA_API_URL",
    "cuenca_site": "CUENCA_SITE_URL",
}


def get_base_url(api_name: str) -> str:
    """
    Get the base URL for a specific API.

    Args:
        api_name: One of "ckan", "ckan_site", "gobec", "gobec_site"

    Returns:
        The API endpoint URL.

    Raises:
        KeyError: If api_name is not valid.
    """
    if api_name not in _API_URLS:
        raise KeyError(
            f"Invalid api_name: {api_name}. "
            f"Valid values are: {', '.join(_API_URLS.keys())}"
        )
    env_key = _ENV_OVERRIDES[api_name]
    return os.getenv(env_key, _API_URLS[api_name])


def get_mcp_host() -> str:
    # Local installs should not expose the server to the whole network by
    # default. Docker Compose explicitly overrides this to 0.0.0.0.
    return os.getenv("MCP_HOST", "127.0.0.1")


def get_mcp_port() -> int:
    port_str = os.getenv("MCP_PORT", "8000")
    try:
        return int(port_str)
    except ValueError:
        return 8000


def get_transport() -> str:
    """Return 'stdio' or 'http'. Env MCP_TRANSPORT overrides default http."""
    raw = os.getenv("MCP_TRANSPORT", "http").strip().lower()
    return "stdio" if raw == "stdio" else "http"


def get_mcp_auth_token() -> str | None:
    token = os.getenv("MCP_AUTH_TOKEN", "").strip()
    return token or None


def get_mcp_max_concurrent_requests() -> int:
    raw = os.getenv("MCP_MAX_CONCURRENT_REQUESTS", "8")
    try:
        return min(256, max(1, int(raw)))
    except ValueError:
        return 8
