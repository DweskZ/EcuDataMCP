"""The smoke test retries a call that failed on a network blip, and only that.

The scheduled run failed on a different source almost daily (a ConnectTimeout
from CentroSur, a ReadTimeout from CEPALSTAT, a 503 from ARCONEL), each time on
one call that answered normally on the next run.
"""

from __future__ import annotations

import pytest

from helpers.smoke_status import is_transient_network_error
from scripts import smoke_e2e as smoke

TIMEOUT = (
    "Error al consultar el archivo de cortes de centrosur: ConnectTimeout "
    "(la fuente no respondió a tiempo; reintenta en unos minutos)"
)


@pytest.fixture
def sleeps(monkeypatch):
    """Record the pauses instead of waiting them out."""
    pauses: list[float] = []

    async def fake_sleep(seconds):
        pauses.append(seconds)

    monkeypatch.setattr(smoke.asyncio, "sleep", fake_sleep)
    return pauses


def _answers(monkeypatch, *responses: tuple[str, bool]) -> list[int]:
    """Serve `responses` in order from every tools/call; return the call counter."""
    calls: list[int] = []

    async def fake_post(client, payload):
        text, is_error = responses[min(len(calls), len(responses) - 1)]
        calls.append(1)
        return {"result": {"content": [{"type": "text", "text": text}], "isError": is_error}}

    monkeypatch.setattr(smoke, "mcp_post", fake_post)
    return calls


@pytest.mark.parametrize(
    "text",
    [
        TIMEOUT,
        "Error al buscar indicadores en CEPALSTAT: ReadTimeout",
        "Error al buscar archivos de sri_datasets: ConnectError",
        "Error al consultar wdi: RemoteProtocolError: server disconnected",
        "Server error '503 Service Unavailable' for url 'https://arconel.example/x'",
        "Server error '504 Gateway Timeout' for url 'https://arconel.example/x'",
    ],
)
def test_a_timeout_a_dropped_connection_or_a_gateway_error_is_transient(text):
    assert is_transient_network_error(text)


@pytest.mark.parametrize(
    "text",
    [
        "Error: no hay datos para ese RUC",
        "Server error '500 Internal Server Error' for url 'https://sri.example/x'",
        "Client error '404 Not Found' for url 'https://sri.example/x'",
        "SGR (ArcGIS) devolvió un error: {'code': 500, 'message': '9017$SITE_NOT_INITIALIZED'}",
    ],
)
def test_a_missing_page_or_a_server_bug_is_not_transient(text):
    assert not is_transient_network_error(text)


async def test_a_blip_is_retried_and_the_second_answer_is_returned(monkeypatch, sleeps):
    calls = _answers(monkeypatch, (TIMEOUT, True), ("cortes: 12 resultados", False))

    assert await smoke.call_tool(None, "search_cortes", {}) == ("cortes: 12 resultados", False)
    assert len(calls) == 2
    assert sleeps == [5]


async def test_a_source_that_stays_down_fails_after_two_retries(monkeypatch, sleeps, capsys):
    calls = _answers(monkeypatch, (TIMEOUT, True))

    assert await smoke.call_tool(None, "search_cortes", {}) == (TIMEOUT, True)
    assert len(calls) == 3
    assert sleeps == [5, 15]
    assert capsys.readouterr().out.count("RETRY    search_cortes") == 2


async def test_an_error_that_is_not_a_network_blip_is_not_retried(monkeypatch, sleeps):
    calls = _answers(monkeypatch, ("Error: no hay datos para ese RUC", True))

    await smoke.call_tool(None, "get_sri_ruc_info", {})

    assert len(calls) == 1 and sleeps == []


async def test_a_successful_answer_that_mentions_a_timeout_is_not_retried(monkeypatch, sleeps):
    calls = _answers(monkeypatch, ("Un ReadTimeout se explica en la sección 3", False))

    await smoke.call_tool(None, "search_normativa", {})

    assert len(calls) == 1 and sleeps == []


async def test_a_known_degraded_source_is_left_to_check_tool(monkeypatch, sleeps):
    # cenace's certificate failure surfaces as a ConnectError, but the source is
    # already named in smoke_status and check_tool retries it itself.
    text = "Error al consultar CENACE: ConnectError: certificate_verify_failed (cenace.gob.ec)"
    calls = _answers(monkeypatch, (text, True))

    await smoke.call_tool(None, "get_cenace_tablero", {})

    assert len(calls) == 1 and sleeps == []
