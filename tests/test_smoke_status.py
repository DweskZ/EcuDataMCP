from helpers.smoke_status import assess_response, degraded_source


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


def test_keeps_unknown_errors_as_failures():
    assessment = assess_response("Error: unexpected source response", [])

    assert assessment.status == "failed"


def test_accepts_matching_normal_response():
    assert assess_response('{"results": []}', ['"results"']).status == "ok"
