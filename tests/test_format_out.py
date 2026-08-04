import json

from helpers.format_out import normalize_format, render_output


def test_normalize_format():
    assert normalize_format("JSON") == "json"
    assert normalize_format("text") == "text"
    assert normalize_format(None) == "text"


def test_render_json_and_text():
    data = {"ok": True, "n": 1}
    assert json.loads(render_output(data, "json"))["ok"] is True
    assert render_output(data, "text", text_builder=lambda d: f"n={d['n']}") == "n=1"
