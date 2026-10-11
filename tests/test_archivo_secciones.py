"""list_archivo_secciones/get_archivo_seccion normalize the eight archive clients."""

import typing

import pytest

from tools import archivo_secciones


def test_every_fuente_has_a_lister_getter_and_name():
    fuentes = set(typing.get_args(archivo_secciones.Fuente))
    listers = set(archivo_secciones._CATEGORIA_LISTS) | set(archivo_secciones._STATIC_LISTS)
    assert fuentes == listers == set(archivo_secciones._GETTERS)
    assert fuentes == set(archivo_secciones._NOMBRES)


async def test_category_list_normalizes_to_secciones(monkeypatch):
    async def fake_list():
        return {
            "total": 1,
            "url_fuente": "https://example.gob.ec/biblioteca/",
            "categorias": [{"id": 7, "nombre": "Planes", "total_archivos": 3}],
        }

    monkeypatch.setitem(archivo_secciones._CATEGORIA_LISTS, "sgr", fake_list)
    result = await archivo_secciones._list_secciones("sgr")
    assert result["secciones"] == [{"id": 7, "nombre": "Planes", "total_archivos": 3}]
    assert result["url_fuente"] == "https://example.gob.ec/biblioteca/"


async def test_static_list_uses_the_source_key_as_id(monkeypatch):
    def fake_list():
        return [{"modulo": "economico", "nombre": "Económico", "url": "https://x"}]

    monkeypatch.setitem(archivo_secciones._STATIC_LISTS, "sipa", (fake_list, "modulo"))
    result = await archivo_secciones._list_secciones("sipa")
    assert result["secciones"] == [
        {"id": "economico", "nombre": "Económico", "url": "https://x"}
    ]


@pytest.mark.parametrize(
    ("raw_id_key", "raw_url_key"),
    [("id", "url_fuente"), ("seccion", "url"), ("familia", "url"), ("modulo", "url")],
)
async def test_get_normalizes_id_url_and_total(monkeypatch, raw_id_key, raw_url_key):
    async def fake_get(seccion):
        return {
            raw_id_key: seccion,
            "nombre": "Sección",
            raw_url_key: "https://page",
            "archivos": [{"titulo": "a", "url": "https://f", "formato": "PDF"}],
        }

    monkeypatch.setitem(archivo_secciones._GETTERS, "seps", fake_get)
    result = await archivo_secciones._get_seccion("seps", "s1")
    assert result["id"] == "s1"
    assert result["url"] == "https://page"
    assert result["total"] == 1
    assert result["descripcion"] is None
