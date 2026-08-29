from helpers.text_utils import strip_accents


def test_strip_accents_default_lowercases():
    assert strip_accents("Inscripción") == "inscripcion"
    assert strip_accents("Cédula") == "cedula"


def test_strip_accents_preserve_case():
    assert strip_accents("Inscripción", lower=False) == "Inscripcion"


def test_strip_accents_none_input():
    assert strip_accents(None) == ""


def test_strip_accents_empty_string():
    assert strip_accents("") == ""
