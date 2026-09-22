import httpx
import pytest

from helpers import centrosur_cortes_client as client

# Trimmed but structurally faithful excerpt of the real WordPress Media
# Library REST API response (www.centrosur.gob.ec/wp-json/wp/v2/media,
# confirmed live 2026-09-20): mixes real 2024-crisis and pre-crisis PDFs
# with non-PDF announcement graphics that also match the same search terms.
_CORTES_MEDIA_JSON = [
    {
        "id": 20521,
        "date": "2026-03-07T09:31:53",
        "slug": "cortes-2",
        "title": {"rendered": "cortes"},
        "media_type": "image",
        "mime_type": "image/png",
        "source_url": "https://www.centrosur.gob.ec/wp-content/uploads/2026/03/cortes.png",
    },
    {
        "id": 18605,
        "date": "2024-09-22T18:58:21",
        "slug": "cortes-23-al-29-septiembre-2024",
        "title": {"rendered": "Cortes-23-al-29-septiembre-2024"},
        "media_type": "file",
        "mime_type": "application/pdf",
        "source_url": (
            "https://www.centrosur.gob.ec/wp-content/uploads/2024/09/"
            "Cortes-23-al-29-septiembre-2024.pdf"
        ),
    },
    {
        "id": 18036,
        "date": "2024-04-19T10:50:22",
        "slug": "cortes_18_19_abril_2024",
        "title": {"rendered": "Cortes_18_19_ABRIL_2024"},
        "media_type": "file",
        "mime_type": "application/pdf",
        "source_url": (
            "https://www.centrosur.gob.ec/wp-content/uploads/2024/04/"
            "Cortes_18_19_ABRIL_2024.pdf"
        ),
    },
    {
        "id": 16350,
        "date": "2023-10-27T08:39:46",
        "slug": "cortes-programados-27-oct",
        "title": {"rendered": "Cortes programados 27 oct"},
        "media_type": "file",
        "mime_type": "application/pdf",
        "source_url": (
            "https://www.centrosur.gob.ec/wp-content/uploads/2023/10/"
            "Cortes-programados-27-oct.pdf"
        ),
    },
]

_DESCONEXION_MEDIA_JSON = [
    {
        "id": 9001,
        "date": "2023-01-30T08:00:00",
        "slug": "desconexion-30-31-01-1",
        "title": {"rendered": "DESCONEXION 30 31 01 1"},
        "media_type": "file",
        "mime_type": "application/pdf",
        "source_url": (
            "https://www.centrosur.gob.ec/wp-content/uploads/2023/10/"
            "DESCONEXION-30-31-01-1.pdf"
        ),
    },
    {
        "id": 20200,
        "date": "2024-11-05T12:00:00",
        "slug": "desconexion-definitiva",
        "title": {"rendered": "Desconexion definitiva"},
        "media_type": "image",
        "mime_type": "image/png",
        "source_url": "https://www.centrosur.gob.ec/wp-content/uploads/2024/11/Desconexion-definitiva.png",
    },
]

_EMPTY_MEDIA_JSON: list = []


def _media_url(term: str) -> httpx.URL:
    return httpx.URL(
        client._WP_MEDIA_URL,
        params={
            "search": term,
            "per_page": 100,
            "_fields": "id,date,slug,title,source_url,mime_type,media_type",
        },
    )


@pytest.fixture(autouse=True)
def clear_cache():
    client._archivos_cache.clear()
    yield
    client._archivos_cache.clear()


async def test_fetch_archivos_filters_to_pdfs_only(httpx_mock):
    httpx_mock.add_response(url=_media_url("Cortes"), json=_CORTES_MEDIA_JSON)
    httpx_mock.add_response(url=_media_url("desconexion"), json=_DESCONEXION_MEDIA_JSON)

    archivos = await client._fetch_archivos()

    # The PNG announcement graphics (both search terms return one) are excluded.
    assert len(archivos) == 4
    assert all(a["formato"] == "PDF" for a in archivos)
    assert not any("cortes.png" in a["url"] for a in archivos)
    assert not any("Desconexion-definitiva" in a["url"] for a in archivos)


async def test_fetch_archivos_extracts_anio_mes_from_upload_path(httpx_mock):
    httpx_mock.add_response(url=_media_url("Cortes"), json=_CORTES_MEDIA_JSON)
    httpx_mock.add_response(url=_media_url("desconexion"), json=_DESCONEXION_MEDIA_JSON)

    archivos = await client._fetch_archivos()

    by_titulo = {a["titulo"]: a for a in archivos}
    crisis_pdf = by_titulo["Cortes_18_19_ABRIL_2024"]
    assert crisis_pdf["anio"] == "2024"
    assert crisis_pdf["mes"] == "04"


async def test_search_centrosur_cortes_filters_by_query_accent_insensitive(httpx_mock):
    httpx_mock.add_response(url=_media_url("Cortes"), json=_CORTES_MEDIA_JSON)
    httpx_mock.add_response(url=_media_url("desconexion"), json=_DESCONEXION_MEDIA_JSON)

    result = await client.search_centrosur_cortes(query="septiembre")

    assert result["total"] == 1
    assert result["total_en_archivo"] == 4
    assert "23-al-29-septiembre" in result["archivos"][0]["titulo"]


async def test_search_centrosur_cortes_filters_by_anio(httpx_mock):
    httpx_mock.add_response(url=_media_url("Cortes"), json=_CORTES_MEDIA_JSON)
    httpx_mock.add_response(url=_media_url("desconexion"), json=_DESCONEXION_MEDIA_JSON)

    result = await client.search_centrosur_cortes(query="2023")

    assert result["total"] == 2
    assert {a["anio"] for a in result["archivos"]} == {"2023"}


async def test_empty_archive_is_not_cached(httpx_mock):
    httpx_mock.add_response(url=_media_url("Cortes"), json=_EMPTY_MEDIA_JSON)
    httpx_mock.add_response(url=_media_url("desconexion"), json=_EMPTY_MEDIA_JSON)
    httpx_mock.add_response(url=_media_url("Cortes"), json=_CORTES_MEDIA_JSON)
    httpx_mock.add_response(url=_media_url("desconexion"), json=_DESCONEXION_MEDIA_JSON)

    first = await client._fetch_archivos()
    assert first == []

    second = await client._fetch_archivos()
    assert len(second) == 4
