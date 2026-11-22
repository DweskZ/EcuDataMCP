import pytest

from helpers.anda_materiales import get_related_materials, parse_material_links


def test_parse_only_same_catalog_downloads():
    html = '''<a title="Serie histórica IPC" href="/anda5/index.php/catalog/809/download/16419"></a>
    <a href="https://anda.inec.gob.ec/anda5/index.php/catalog/809/download/16424">Canasta básica</a>
    <a href="/anda5/index.php/catalog/999/download/123">Otro estudio</a>
    <a href="https://evil.example/anda5/index.php/catalog/809/download/16420">Extraño</a>
    <a href="/anda5/index.php/catalog/809/download/16419">Duplicado</a>'''
    result = parse_material_links(html, "https://anda.inec.gob.ec/anda5/index.php/catalog/809/related-materials", "809")
    assert [row["nombre"] for row in result] == ["Serie histórica IPC", "Canasta básica"]
    assert result[0]["url"].endswith("/809/download/16419")


@pytest.mark.asyncio
async def test_related_materials_requests_page(httpx_mock):
    url = "https://anda.inec.gob.ec/anda5/index.php/catalog/809/related-materials"
    httpx_mock.add_response(url=url, text='<a href="/anda5/index.php/catalog/809/download/16424">Canasta</a>')
    result = await get_related_materials("809")
    assert result["total"] == 1
    assert result["url_fuente"] == url


@pytest.mark.asyncio
async def test_invalid_id_rejected():
    with pytest.raises(ValueError):
        await get_related_materials("../other")
