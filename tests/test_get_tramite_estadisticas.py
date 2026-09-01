from tools.get_tramite_estadisticas import _clean_modificado, _periodo


def test_clean_modificado_strips_time_tag():
    raw = '<time datetime="2026-08-11T11:22:05-05:00">2026-08-11T11:22:05-0500</time>\n'
    assert _clean_modificado(raw) == "2026-08-11T11:22:05-0500"


def test_clean_modificado_handles_empty():
    assert _clean_modificado("") == ""


def test_periodo_zero_pads_int_month():
    assert _periodo(2026, 7) == "2026-07"


def test_periodo_falls_back_gracefully_for_non_numeric_month():
    # A malformed API row shouldn't crash formatting -- just show it as-is.
    assert _periodo(2026, "desconocido") == "2026-desconocido"
