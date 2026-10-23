import json

from helpers.format_out import cap_rows, normalize_format, render_output


def test_normalize_format():
    assert normalize_format("JSON") == "json"
    assert normalize_format("text") == "text"
    assert normalize_format(None) == "text"


def test_render_json_and_text():
    data = {"ok": True, "n": 1}
    assert json.loads(render_output(data, "json"))["ok"] is True
    assert render_output(data, "text", text_builder=lambda d: f"n={d['n']}") == "n=1"


def test_cap_rows_leaves_small_payload_untouched():
    payload = {"results": [{"id": i} for i in range(3)]}
    assert cap_rows(payload, "results", 10_000) is payload


def test_cap_rows_truncates_and_declares_it():
    payload = {"total": 50, "results": [{"id": i, "pad": "x" * 100} for i in range(50)]}
    capped = cap_rows(payload, "results", 2_000)
    kept = len(capped["results"])
    assert 1 <= kept < 50
    assert len(json.dumps(capped).encode()) <= 2_000 + 400
    truncado = capped["metadatos"]["truncado"]
    assert truncado["filas_devueltas"] == kept
    assert truncado["filas_omitidas"] == 50 - kept
    assert "page_size" in truncado["como_pedir_el_resto"]
    assert len(payload["results"]) == 50


def test_cap_rows_uses_the_callers_hint():
    payload = {"results": [{"pad": "x" * 5_000}, {"pad": "y" * 5_000}]}
    capped = cap_rows(payload, "results", 100, hint="usar compact=true")
    assert capped["metadatos"]["truncado"]["como_pedir_el_resto"] == "usar compact=true"


def test_cap_rows_keeps_one_row_even_if_it_exceeds_the_cap():
    payload = {"results": [{"pad": "x" * 5_000}, {"pad": "y" * 5_000}]}
    capped = cap_rows(payload, "results", 100)
    assert len(capped["results"]) == 1
