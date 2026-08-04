import os

_API_URLS = {
    "ckan": "https://www.datosabiertos.gob.ec/api/3/action/",
    "ckan_site": "https://www.datosabiertos.gob.ec/",
    "gobec": "https://www.gob.ec/api/v1/",
    "gobec_site": "https://www.gob.ec/",
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
    return _API_URLS[api_name]


def get_mcp_host() -> str:
    return os.getenv("MCP_HOST", "0.0.0.0")


def get_mcp_port() -> int:
    port_str = os.getenv("MCP_PORT", "8000")
    try:
        return int(port_str)
    except ValueError:
        return 8000
