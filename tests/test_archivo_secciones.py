"""list_archivo_secciones/get_archivo_seccion normalize the eight archive clients."""

import typing

import pytest
from mcp.server.mcpserver import MCPServer

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


async def test_category_list_without_total_archivos_omits_it(monkeypatch):
    async def fake_list():
        return {
            "url_fuente": "https://www.cne.gob.ec/estadisticas/bases-de-datos/",
            "categorias": [{"id": "8325", "nombre": "Elecciones Generales 2025"}],
        }

    monkeypatch.setitem(archivo_secciones._CATEGORIA_LISTS, "cne", fake_list)
    result = await archivo_secciones._list_secciones("cne")
    assert result["secciones"] == [{"id": "8325", "nombre": "Elecciones Generales 2025"}]


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


def _text(result) -> str:
    return result.content[0].text


@pytest.fixture
def mcp():
    server = MCPServer("test")
    archivo_secciones.register_archivo_secciones_tools(server)
    return server


_NEW_FUENTES = ["petroecuador", "energia", "cne", "bvg", "bvq"]


@pytest.mark.parametrize("fuente", _NEW_FUENTES)
async def test_new_fuentes_list_and_get_through_the_tool(monkeypatch, mcp, fuente):
    async def fake_list():
        return {
            "url_fuente": "https://example.gob.ec/",
            "categorias": [{"id": "s1", "nombre": "Sección uno"}],
        }

    def fake_static():
        return [{"seccion": "s1", "nombre": "Sección uno", "url": "https://example.gob.ec/s1"}]

    async def fake_get(seccion):
        return {
            "id": seccion,
            "seccion": seccion,
            "nombre": "Sección uno",
            "url": "https://example.gob.ec/s1",
            "archivos": [
                {
                    "titulo": "Archivo",
                    "grupo": "Resultados",
                    "formato": "XLSX",
                    "url": "https://example.gob.ec/a.xlsx",
                }
            ],
        }

    if fuente in archivo_secciones._CATEGORIA_LISTS:
        monkeypatch.setitem(archivo_secciones._CATEGORIA_LISTS, fuente, fake_list)
    else:
        monkeypatch.setitem(archivo_secciones._STATIC_LISTS, fuente, (fake_static, "seccion"))
    monkeypatch.setitem(archivo_secciones._GETTERS, fuente, fake_get)

    listed = await mcp.call_tool("list_archivo_secciones", {"fuente": fuente})
    assert listed.structured_content["fuente"] == fuente
    assert listed.structured_content["total"] == 1
    assert listed.structured_content["secciones"][0]["id"] == "s1"
    assert "- s1: Sección uno" in _text(listed)

    got = await mcp.call_tool("get_archivo_seccion", {"fuente": fuente, "seccion": "s1"})
    assert got.structured_content["total"] == 1
    assert got.structured_content["nombre_fuente"] == archivo_secciones._NOMBRES[fuente]
    assert "Archivo" in _text(got)


async def test_cne_listing_without_total_archivos_has_no_count_in_text(monkeypatch, mcp):
    async def fake_list():
        return {
            "url_fuente": "https://www.cne.gob.ec/estadisticas/bases-de-datos/",
            "categorias": [{"id": "8325", "nombre": "Elecciones Generales 2025"}],
        }

    monkeypatch.setitem(archivo_secciones._CATEGORIA_LISTS, "cne", fake_list)

    result = await mcp.call_tool("list_archivo_secciones", {"fuente": "cne"})

    assert "- 8325: Elecciones Generales 2025" in _text(result)
    assert "archivo(s))" not in _text(result)
    assert "total_archivos" not in result.structured_content["secciones"][0]


async def test_get_text_shows_size_and_modified_date(monkeypatch, mcp):
    async def fake_get(seccion):
        return {
            "seccion": seccion,
            "nombre": "Históricos",
            "url": "https://example.gob.ec/",
            "archivos": [
                {
                    "titulo": "Acciones",
                    "formato": "XLSX",
                    "url": "https://example.gob.ec/a.xlsx",
                    "tamano_bytes": 1433675,
                    "modificado": "2026-10-08T20:35:40+00:00",
                },
                {
                    "titulo": "Primera Vuelta",
                    "grupo": "Resultados",
                    "formato": "DESCONOCIDO",
                    "url": "https://example.gob.ec/b",
                    "tamano": "18.12 MB",
                },
                {"titulo": "Sin datos", "formato": "PDF", "url": "https://example.gob.ec/c.pdf"},
            ],
        }

    monkeypatch.setitem(archivo_secciones._GETTERS, "bvg", fake_get)

    text = _text(await mcp.call_tool("get_archivo_seccion", {"fuente": "bvg", "seccion": "x"}))

    assert "- Acciones [XLSX, 1.4 MB, modificado 2026-10-08]" in text
    assert "- Resultados / Primera Vuelta [DESCONOCIDO, 18.12 MB]" in text
    assert "- Sin datos [PDF]" in text
