"""search_archivos normalizes eleven file-link clients behind `fuente`."""

import typing

from tools import search_archivos as sa


def test_every_fuente_has_a_client():
    fuentes = set(typing.get_args(sa.Fuente))
    assert fuentes == set(sa._PAGINATED) | set(sa._UNPAGINATED) | {"salarios"}


def test_normalize_file_maps_aliases_and_keeps_extras():
    item = {"label": "Boletín", "url": "https://f", "format": "PDF", "anio": 2024}
    assert sa._normalize_file(item) == {
        "titulo": "Boletín",
        "url": "https://f",
        "formato": "PDF",
        "anio": 2024,
    }


def test_normalize_file_keeps_both_links_when_a_source_has_two():
    item = {"titulo": "Tabla 2025", "url_ver": "https://ver", "url_descarga": "https://dl"}
    normalized = sa._normalize_file(item)
    assert normalized["url"] == "https://dl"
    assert normalized["url_ver"] == "https://ver"


async def test_unpaginated_sources_are_sliced_here(monkeypatch):
    async def fake(query=""):
        return {
            "source": "CNIG",
            "url_fuente": "https://cnig",
            "archivos": [{"label": f"t{i}", "url": f"https://f/{i}", "format": "PDF"} for i in range(5)],
        }

    monkeypatch.setitem(sa._UNPAGINATED, "cnig", fake)
    result = await sa._search("cnig", "", limit=2, offset=1)
    assert result["total"] == 5
    assert [a["titulo"] for a in result["archivos"]] == ["t1", "t2"]
    assert result["url_fuente"] == "https://cnig"


async def test_salarios_query_filters_titles_and_years(monkeypatch):
    async def fake(anio=None):
        return {
            "source": "Trabajo",
            "tablas": [
                {"titulo": "Salarios sectoriales", "anio": 2024, "url_descarga": "https://a"},
                {"titulo": "Salarios sectoriales", "anio": 2025, "url_descarga": "https://b"},
            ],
            "nota": "No hay tabla 2026.",
        }

    monkeypatch.setattr(sa.salarios_sectoriales_client, "search_tablas_sectoriales", fake)
    result = await sa._search("salarios", "2025", limit=50, offset=0)
    assert [a["url"] for a in result["archivos"]] == ["https://b"]
    assert result["nota"] == "No hay tabla 2026."
