from helpers.gobec_client import _clean_html


def test_clean_html_unescapes_double_encoded_quotes():
    raw = "&amp;quot;0080 Reglamento&amp;quot;"
    assert _clean_html(raw) == '"0080 Reglamento"'


def test_clean_html_lists():
    raw = "<p>Intro</p><ul><li>Uno</li><li>Dos</li></ul>"
    text = _clean_html(raw)
    assert "Intro" in text
    assert "- Uno" in text
    assert "- Dos" in text
