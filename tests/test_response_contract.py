from helpers.response_contract import CONTRACT_VERSION, with_response_metadata


def test_response_metadata_preserves_payload_and_has_all_contract_fields():
    result = with_response_metadata(
        {"total": 3},
        source="Fuente oficial",
        source_url="https://example.test/catalogo",
        freshness="catalogo_actual",
        schema_name="catalogo_v1",
        schema_fields=["total", "tablas"],
        consulted_at="2026-08-31T00:00:00+00:00",
    )

    assert result["total"] == 3
    assert result["metadatos"] == {
        "contrato": CONTRACT_VERSION,
        "fuente": "Fuente oficial",
        "url_fuente": "https://example.test/catalogo",
        "consultado_en": "2026-08-31T00:00:00+00:00",
        "fecha_publicacion": None,
        "fecha_corte": None,
        "frescura": "catalogo_actual",
        "esquema": {"nombre": "catalogo_v1", "campos_principales": ["total", "tablas"]},
    }
