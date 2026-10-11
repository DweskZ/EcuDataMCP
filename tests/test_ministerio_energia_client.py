import asyncio

import httpx
import pytest

from helpers import ministerio_energia_client as client

_UP = "https://www.ambienteyenergia.gob.ec/wp-content/uploads"


def _item(item_id, date, path, mime="application/pdf", title=None):
    name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return {
        "id": item_id,
        "date": date,
        "title": {"rendered": title or name},
        "mime_type": mime,
        "source_url": f"{_UP}/{path}",
    }


# Trimmed excerpt of the real media-library search results (confirmed live
# 2026-10-10), mixing statistics with unrelated media that the same search
# terms also return.
_HIDRO_2024 = _item(
    1, "2025-12-09T10:00:00", "2025/12/ESTADISTICAS-DE-HIDROCARBUROS-2024_8.12.2025.pdf"
)
_HIDRO_MATRIZ = _item(
    2,
    "2025-05-28T10:00:00",
    "2025/05/7.2.1-Matriz-Produccin-Campo-Hidrocarburos-2024_29.01.2025.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
_HIDRO_CRUDO = _item(3, "2019-01-30T09:00:00", "2019/01/2008-ESTADISTICA-CRUDO.pdf")
_REGLAMENTO = _item(
    4, "2019-02-19T09:00:00", "2019/02/REGLAMENTO-DE-OPERACIONES-HIDROCARBURIFERAS.pdf"
)
_MINERAS_PDF = _item(
    5,
    "2025-05-28T11:00:00",
    "2025/05/7.3.2-Informe-Exportaciones-Mineras-2024-VF-signed-Subsanado.pdf",
)
_MINERAS_PNG = _item(
    6,
    "2022-12-23T11:00:00",
    "2022/12/Exportaciones-mineras-hasta-octubre-2022.png",
    mime="image/png",
)
_SEMANA = _item(7, "2021-07-05T11:00:00", "2021/07/Semana-26-Reporte-Mineria.pdf")
_SEMANA_ACENTO = _item(
    8, "2020-10-05T11:00:00", "2020/10/Semana-40-Reporte-Miner%C3%ADa.pdf"
)
_BEN_2025 = _item(
    9, "2026-09-11T11:00:00", "2026/09/CAPITULO_001-BEN_2025_compressed.pdf"
)
_BEN_24 = _item(10, "2025-09-01T11:00:00", "2025/09/BEN_24-CAPITULO_1.pdf")
_BEN_ONLY_NAME = _item(
    11, "2026-08-11T11:00:00", "2026/08/4439-0913731279-PERALTA-BENITEZ-JILL-LIANA.pdf"
)

_BY_TERM = {
    "Hidrocarburifera": [_HIDRO_CRUDO, _REGLAMENTO],
    "Estadistica de Hidrocarburos": [_HIDRO_2024],
    "Matriz Produccin": [_HIDRO_MATRIZ],
    "exportaciones mineras": [_MINERAS_PDF, _MINERAS_PNG],
    "Reporte Mineria": [_SEMANA, _SEMANA_ACENTO],
    "BEN_": [_BEN_2025, _BEN_24, _BEN_ONLY_NAME],
    # The same item can come back under several terms.
    "Estadistica Crudo": [_HIDRO_CRUDO],
}


def _search_url(term, page=1):
    return httpx.URL(
        client._WP_MEDIA_URL,
        params={
            "search": term,
            "per_page": 100,
            "page": page,
            "_fields": client._FIELDS,
        },
    )


def _mock_all_terms(httpx_mock, by_term=None):
    by_term = _BY_TERM if by_term is None else by_term
    terms = dict.fromkeys(t for s in client._SECCIONES for t in s["terminos"])
    for term in terms:
        httpx_mock.add_response(
            url=_search_url(term),
            json=by_term.get(term, []),
            headers={"X-WP-TotalPages": "1"},
        )


@pytest.fixture(autouse=True)
def clear_cache():
    client._archivo_cache.clear()
    yield
    client._archivo_cache.clear()


async def test_list_secciones_counts_files_per_section(httpx_mock):
    _mock_all_terms(httpx_mock)

    result = await client.list_secciones()

    counts = {c["id"]: c["total_archivos"] for c in result["categorias"]}
    # The regulation PDF and the unrelated BEN-substring file match no section.
    assert counts == {
        "estadistica_hidrocarburos": 3,
        "mineria_exportaciones_recaudacion": 1,
        "mineria_reportes_semanales": 2,
        "balance_energetico": 2,
    }
    assert result["total"] == 4


async def test_get_seccion_drops_images_and_unrelated_media(httpx_mock):
    _mock_all_terms(httpx_mock)

    mineria = await client.get_seccion_archivos("mineria_exportaciones_recaudacion")

    assert [a["formato"] for a in mineria["archivos"]] == ["PDF"]
    all_urls = {
        a["url"]
        for s in client._SECCIONES
        for a in (await client.get_seccion_archivos(s["id"]))["archivos"]
    }
    assert not any(u.endswith(".png") for u in all_urls)
    assert not any("REGLAMENTO" in u or "PERALTA-BENITEZ" in u for u in all_urls)


async def test_files_are_deduplicated_and_sorted_newest_first(httpx_mock):
    _mock_all_terms(httpx_mock)

    hidro = await client.get_seccion_archivos("estadistica_hidrocarburos")

    # _HIDRO_CRUDO comes back under two search terms but is listed once.
    assert [a["fecha_subida"][:4] for a in hidro["archivos"]] == [
        "2025",
        "2025",
        "2019",
    ]
    assert len({a["url"] for a in hidro["archivos"]}) == 3


async def test_periodo_is_the_first_year_in_the_filename(httpx_mock):
    _mock_all_terms(httpx_mock)

    hidro = await client.get_seccion_archivos("estadistica_hidrocarburos")
    ben = await client.get_seccion_archivos("balance_energetico")

    por_url = {
        a["url"].rsplit("/", 1)[-1]: a for a in hidro["archivos"] + ben["archivos"]
    }
    # Uploaded in Dec 2025 but it is the 2024 yearbook.
    assert (
        por_url["ESTADISTICAS-DE-HIDROCARBUROS-2024_8.12.2025.pdf"]["periodo"] == "2024"
    )
    assert por_url["2008-ESTADISTICA-CRUDO.pdf"]["periodo"] == "2008"
    assert por_url["CAPITULO_001-BEN_2025_compressed.pdf"]["periodo"] == "2025"
    # No year in the name: left empty, not guessed from the upload date.
    assert por_url["BEN_24-CAPITULO_1.pdf"]["periodo"] is None


async def test_filename_filter_ignores_accents_in_encoded_urls(httpx_mock):
    _mock_all_terms(httpx_mock)

    semanales = await client.get_seccion_archivos("mineria_reportes_semanales")

    assert len(semanales["archivos"]) == 2


async def test_spreadsheet_formats_are_reported(httpx_mock):
    _mock_all_terms(httpx_mock)

    hidro = await client.get_seccion_archivos("estadistica_hidrocarburos")

    assert {a["formato"] for a in hidro["archivos"]} == {"PDF", "XLSX"}


async def test_unknown_seccion_raises_with_valid_ids():
    with pytest.raises(ValueError, match="balance_energetico"):
        await client.get_seccion_archivos("petroleo")


async def test_seccion_accepts_the_display_name(httpx_mock):
    _mock_all_terms(httpx_mock)

    result = await client.get_seccion_archivos("Balance Energético Nacional (BEN)")

    assert result["id"] == "balance_energetico"


async def test_pages_past_the_first_are_followed(httpx_mock):
    terms = list(dict.fromkeys(t for s in client._SECCIONES for t in s["terminos"]))
    httpx_mock.add_response(
        url=_search_url(terms[0]),
        json=[_HIDRO_CRUDO],
        headers={"X-WP-TotalPages": "2"},
    )
    httpx_mock.add_response(
        url=_search_url(terms[0], page=2),
        json=[_HIDRO_2024],
        headers={"X-WP-TotalPages": "2"},
    )
    for term in terms[1:]:
        httpx_mock.add_response(
            url=_search_url(term), json=[], headers={"X-WP-TotalPages": "1"}
        )

    hidro = await client.get_seccion_archivos("estadistica_hidrocarburos")

    assert len(hidro["archivos"]) == 2


async def test_dropped_connection_is_retried(httpx_mock, monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(client.asyncio, "sleep", no_sleep)
    terms = list(dict.fromkeys(t for s in client._SECCIONES for t in s["terminos"]))
    httpx_mock.add_exception(httpx.ReadError("Server disconnected"))
    httpx_mock.add_response(
        url=_search_url(terms[0]),
        json=[_HIDRO_CRUDO],
        headers={"X-WP-TotalPages": "1"},
    )
    for term in terms[1:]:
        httpx_mock.add_response(
            url=_search_url(term), json=[], headers={"X-WP-TotalPages": "1"}
        )

    hidro = await client.get_seccion_archivos("estadistica_hidrocarburos")

    assert len(hidro["archivos"]) == 1


async def test_empty_archive_is_not_cached(httpx_mock):
    _mock_all_terms(httpx_mock, by_term={})
    _mock_all_terms(httpx_mock)

    first = await client.list_secciones()
    assert {c["total_archivos"] for c in first["categorias"]} == {0}

    second = await client.list_secciones()
    assert sum(c["total_archivos"] for c in second["categorias"]) == 8


async def test_browser_user_agent_is_sent(httpx_mock):
    _mock_all_terms(httpx_mock)

    await client.list_secciones()

    for request in httpx_mock.get_requests():
        assert request.headers["User-Agent"].startswith("Mozilla/5.0")


def _fake_get_page(by_term, delay=0.0, failing=(), stats=None):
    async def fake(session, term, page):
        if stats is not None:
            stats["now"] += 1
            stats["max"] = max(stats["max"], stats["now"])
        try:
            await asyncio.sleep(delay)
            if term in failing:
                raise httpx.ConnectError("boom")
            pages = by_term.get(term, [[]])
            return (pages[page - 1] if page <= len(pages) else []), len(pages)
        finally:
            if stats is not None:
                stats["now"] -= 1

    return fake


async def test_search_requests_are_concurrent_but_bounded(monkeypatch):
    stats = {"now": 0, "max": 0}
    monkeypatch.setattr(
        client, "_get_page", _fake_get_page({"BEN_": [[_BEN_2025]]}, delay=0.02, stats=stats)
    )

    result = await client.get_seccion_archivos("balance_energetico")

    assert len(result["archivos"]) == 1
    assert 1 < stats["max"] <= client._CONCURRENCY


async def test_extra_pages_are_fetched_and_merged(monkeypatch):
    by_term = {"BEN_": [[_BEN_2025], [_BEN_24]]}
    monkeypatch.setattr(client, "_get_page", _fake_get_page(by_term))

    result = await client.get_seccion_archivos("balance_energetico")

    assert [a["fecha_subida"][:4] for a in result["archivos"]] == ["2026", "2025"]


async def test_failed_term_returns_partial_result_and_is_not_cached(monkeypatch):
    by_term = {"BEN_": [[_BEN_2025]], "Reporte Mineria": [[_SEMANA]]}
    monkeypatch.setattr(client, "_get_page", _fake_get_page(by_term, failing={"BEN_"}))

    mineria = await client.get_seccion_archivos("mineria_reportes_semanales")

    assert len(mineria["archivos"]) == 1
    assert client._archivo_cache.get("archivo") is None


async def test_all_terms_failing_raises(monkeypatch):
    every_term = {t for s in client._SECCIONES for t in s["terminos"]}
    monkeypatch.setattr(client, "_get_page", _fake_get_page({}, failing=every_term))

    with pytest.raises(ValueError, match="biblioteca de medios"):
        await client.get_seccion_archivos("balance_energetico")


async def test_items_from_foreign_hosts_are_dropped(monkeypatch):
    foreign = {**_BEN_2025, "id": 99, "source_url": "https://evil.example/2026/09/BEN_2025.pdf"}
    monkeypatch.setattr(
        client, "_get_page", _fake_get_page({"BEN_": [[foreign, _BEN_24]]})
    )

    result = await client.get_seccion_archivos("balance_energetico")

    assert [a["url"] for a in result["archivos"]] == [_BEN_24["source_url"]]
