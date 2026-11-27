"""A check that only timed out is tried again after the other checks, not failed at once.

On 2026-11-25 get_cortes_horarios for EEASA hit a ConnectTimeout three times
within 20 s on the runner and failed the whole scheduled run, while the same
call answered from both hosted servers that day. Twelve of the last twenty
scheduled runs failed, each on a different host's timeout. The in-call retries
only span 20 s; the second pass comes minutes later.
"""

from __future__ import annotations

import json

import httpx
import pytest

from scripts import smoke_e2e as smoke

TIMEOUT = (
    "Error al procesar el horario de cortes de eeasa: ConnectTimeout "
    "(la fuente no respondió a tiempo; reintenta en unos minutos)"
)
IESS_TIMEOUT = (
    "Error al consultar el certificado de cumplimiento patronal del IESS: "
    "ConnectTimeout (la fuente no respondió a tiempo; reintenta en unos minutos)"
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


# A first try plus its two in-call retries all time out, then the second pass runs.
THREE_TIMEOUTS = ((TIMEOUT, True),) * 3


async def test_a_check_that_keeps_timing_out_is_held_back_not_failed(monkeypatch, sleeps, capsys):
    calls = _answers(monkeypatch, (TIMEOUT, True))
    tally = smoke.Tally()

    await smoke.run_check(None, tally, "get_cortes_horarios", {}, [])

    assert len(calls) == 3
    assert tally.failed == 0
    assert len(tally.timed_out) == 1
    assert "DEFER    get_cortes_horarios" in capsys.readouterr().out


async def test_a_held_back_check_that_answers_the_second_time_is_degraded(
    monkeypatch, sleeps, capsys
):
    _answers(monkeypatch, *THREE_TIMEOUTS, ("5 avisos", False))
    tally = smoke.Tally()
    await smoke.run_check(None, tally, "get_cortes_horarios", {}, [])

    await tally.timed_out[0]()

    assert tally.failed == 0
    assert tally.degraded == {"timeout:get_cortes_horarios"}
    assert "RECOVERED get_cortes_horarios" in capsys.readouterr().out


async def test_a_held_back_check_that_times_out_again_fails(monkeypatch, sleeps, capsys):
    _answers(monkeypatch, (TIMEOUT, True))
    tally = smoke.Tally()
    await smoke.run_check(None, tally, "get_cortes_horarios", {}, [])

    await tally.timed_out[0]()

    assert tally.failed == 1
    assert tally.degraded == set()
    assert "FAIL get_cortes_horarios" in capsys.readouterr().out


async def test_a_failure_that_is_not_a_timeout_fails_at_once(monkeypatch, sleeps):
    _answers(monkeypatch, ("Error: no hay datos para ese RUC", True))
    tally = smoke.Tally()

    await smoke.run_check(None, tally, "get_sri_ruc_info", {}, [])

    assert tally.failed == 1
    assert tally.timed_out == []


async def test_a_timeout_from_a_source_already_known_as_degraded_is_not_held_back(
    monkeypatch, sleeps
):
    _answers(monkeypatch, (IESS_TIMEOUT, True))
    tally = smoke.Tally()

    await smoke.run_check(None, tally, "get_certificado_cumplimiento_patronal", {}, [])

    assert tally.failed == 0
    assert tally.degraded == {"iess_certificado_timeout"}
    assert tally.timed_out == []


async def test_a_chain_that_times_out_is_held_back_and_recovers(monkeypatch, sleeps, capsys):
    _answers(monkeypatch, *THREE_TIMEOUTS, ("lista", False))

    async def chain(client):
        await smoke.call_chain_step(client, "list_catalogo", {})

    tally = smoke.Tally()
    await smoke.run_chain(None, tally, "cepalstat: search -> indicador", chain)
    assert tally.failed == 0 and len(tally.timed_out) == 1

    await tally.timed_out[0]()

    out = capsys.readouterr().out
    assert tally.failed == 0
    assert tally.degraded == {"timeout:cepalstat: search -> indicador"}
    assert "OK   cepalstat: search -> indicador" in out


async def test_a_chain_that_fails_for_another_reason_fails_at_once(monkeypatch, sleeps):
    async def chain(client):
        raise AssertionError("search_informes_igepn returned no reports")

    tally = smoke.Tally()
    await smoke.run_chain(None, tally, "igepn: search -> informe", chain)

    assert tally.failed == 1 and tally.timed_out == []


def _fake_server(timeouts: int):
    """Answer every tool with "ok", except get_cortes_horarios, which times out `timeouts` times."""
    seen: list[int] = []

    def reply(text: str, is_error: bool) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": text}], "isError": is_error},
            },
        )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "hidden_tools": []})
        body = json.loads(request.content or b"{}")
        method = body.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": 0, "result": {}},
                headers={"mcp-session-id": "test-session"},
            )
        if method == "tools/call":
            if body["params"]["name"] == "get_cortes_horarios":
                seen.append(1)
                if len(seen) <= timeouts:
                    return reply(TIMEOUT, True)
            return reply("ok", False)
        return httpx.Response(202)

    return handler


def _serve(monkeypatch, timeouts: int) -> None:
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        smoke.httpx,
        "AsyncClient",
        lambda *a, **k: real_client(transport=httpx.MockTransport(_fake_server(timeouts))),
    )


async def test_main_runs_a_second_pass_and_reports_a_recovered_check(monkeypatch, sleeps, capsys):
    _serve(monkeypatch, timeouts=3)

    await smoke.main()
    out = capsys.readouterr().out

    assert "DEFER    get_cortes_horarios" in out
    assert "== second pass: 1 check(s) that timed out ==" in out
    assert "RECOVERED get_cortes_horarios" in out
    assert "FAIL get_cortes_horarios" not in out
    assert smoke.SECOND_PASS_PAUSE in sleeps


async def test_main_fails_a_check_that_times_out_in_both_passes(monkeypatch, sleeps, capsys):
    _serve(monkeypatch, timeouts=99)

    await smoke.main()
    out = capsys.readouterr().out

    assert "DEFER    get_cortes_horarios" in out
    assert "FAIL get_cortes_horarios" in out
    assert "RECOVERED" not in out


async def test_main_has_no_second_pass_when_nothing_timed_out(monkeypatch, sleeps, capsys):
    _serve(monkeypatch, timeouts=0)

    await smoke.main()

    assert "second pass" not in capsys.readouterr().out
    assert smoke.SECOND_PASS_PAUSE not in sleeps
