import pytest

from helpers.smoke_status import assess_response, degraded_source
from scripts.smoke_e2e import DegradedChain, chain_step


def test_classifies_ckan_regional_block_as_degraded():
    text = (
        '{"error": "El portal de Datos Abiertos (datosabiertos.gob.ec) '
        'rechazó la conexión (403)."}'
    )

    assessment = assess_response(text, ['"results"'])

    assert assessment.status == "degraded"
    assert assessment.source == "datos_abiertos_ckan"


def test_classifies_cenace_certificate_problem_as_degraded():
    text = (
        "Error executing tool get_cenace_tablero: "
        "https://www.cenace.gob.ec: [SSL: CERTIFICATE_VERIFY_FAILED]"
    )

    assert degraded_source(text) == "cenace_tls"
    assert assess_response(text, ["PRODUCCIÓN"]).status == "degraded"


def test_classifies_sercop_regional_block_as_degraded():
    text = (
        '{"error": "No se pudo conectar al portal de Datos Abiertos de '
        'Compras Públicas (compraspublicas.gob.ec). Esto suele pasar '
        'cuando el servidor se conecta desde fuera de Latinoamérica."}'
    )

    assessment = assess_response(text, ["ocid", "results", "rate_limited", "error"])

    assert assessment.status == "degraded"
    assert assessment.source == "sercop_compras_publicas"


def test_keeps_unknown_errors_as_failures():
    assessment = assess_response("Error: unexpected source response", [])

    assert assessment.status == "failed"


def test_accepts_matching_normal_response():
    assert assess_response('{"results": []}', ['"results"']).status == "ok"


# -- chain steps ------------------------------------------------------
# The dynamic list -> get chains used to hand-roll their own error check,
# so the recurring datosabiertos.gob.ec 403 failed the workflow even though
# the flat checks classified the identical response as degraded.


def test_chain_step_degrades_on_known_source_block():
    text = (
        '{"error": "El portal de Datos Abiertos (datosabiertos.gob.ec) '
        'rechazó la conexión (403)."}'
    )

    with pytest.raises(DegradedChain) as excinfo:
        chain_step(text)

    assert excinfo.value.source == "datos_abiertos_ckan"


def test_chain_step_still_fails_on_an_unknown_error():
    with pytest.raises(AssertionError):
        chain_step("Error: unexpected source response")


def test_chain_step_returns_a_healthy_response_unchanged():
    text = '{"results": [{"id": "abc"}]}'

    assert chain_step(text, ['"results"']) == text
