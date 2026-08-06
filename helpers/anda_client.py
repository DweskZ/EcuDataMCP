import logging
from typing import Any

import httpx

from helpers import env_config
from helpers.logging import MAIN_LOGGER_NAME
from helpers.user_agent import USER_AGENT

logger = logging.getLogger(MAIN_LOGGER_NAME)

_TIMEOUT = 20.0

# NADA marks surveys with no microdata attached (aggregate-only publications,
# e.g. price indices) as form_model "data_na". Anything else ("direct",
# "external", etc.) means the survey has actual microdata behind it.
NO_MICRODATA_FORM_MODEL = "data_na"


def _anda_url(path: str) -> str:
    return f"{env_config.get_base_url('anda')}{path}"


async def search_catalog(
    query: str = "",
    limit: int = 10,
    session: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Search the ANDA (NADA) survey/census catalog.

    ANDA's full-text search (`sk`) is loose — multi-word queries are matched
    fairly broadly rather than as a strict AND, so short specific keywords
    work better than long phrases.
    """
    own = session is None
    if own:
        session = httpx.AsyncClient(headers={"User-Agent": USER_AGENT})
    assert session is not None
    try:
        params: dict[str, Any] = {"ps": min(limit, 50)}
        if query:
            params["sk"] = query
        logger.debug("ANDA GET catalog params=%s", params)
        resp = await session.get(
            _anda_url("catalog"), params=params, timeout=_TIMEOUT, follow_redirects=True
        )
        resp.raise_for_status()
        return resp.json().get("result", {})
    except httpx.HTTPError as exc:
        logger.error("ANDA request failed: %s", exc)
        raise
    finally:
        if own:
            await session.aclose()


def has_microdata(row: dict[str, Any]) -> bool:
    """True if a catalog entry has downloadable microdata, not just aggregates."""
    return row.get("form_model") != NO_MICRODATA_FORM_MODEL
