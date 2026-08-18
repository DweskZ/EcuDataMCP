import os
import sqlite3
import time

import pytest

from helpers import supercias_financials


def _build_db(path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE ranking (anio INTEGER, expediente INTEGER, "
        "posicion_general INTEGER, ciiu_n1 TEXT, ciiu_n6 TEXT, "
        "ingresos_ventas REAL, activos REAL, roe REAL)"
    )
    conn.executemany(
        "INSERT INTO ranking VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (2025, 1, 10, "C", "C1010.01", 1000.0, 5000.0, 0.1),
            (2024, 1, 15, "C", "C1010.01", 900.0, 4800.0, 0.09),
            (2025, 2, 3, "G", "G4510.01", 3000.0, 9000.0, 0.2),
            # expediente 3 has financials but no matching companias row --
            # tests the LEFT JOIN / "predates directory coverage" case.
            (2025, 3, 20, "C", "C1010.01", 500.0, 2000.0, 0.05),
        ],
    )
    conn.execute(
        "CREATE TABLE companias (expediente INTEGER, ruc TEXT, nombre TEXT)"
    )
    conn.executemany(
        "INSERT INTO companias VALUES (?, ?, ?)",
        [
            (1, "1790013731001", "ACME"),
            (2, "1790004724001", "OTRA S.A."),
        ],
    )
    conn.execute("CREATE TABLE segmentos (id_segmento INTEGER, segmento TEXT)")
    conn.execute("CREATE TABLE ciiu (ciiu TEXT, descripcion TEXT)")
    conn.execute(
        "CREATE TABLE indicadores_sector (anio INTEGER, ciiu_n1 TEXT, "
        "descripcion TEXT, roe REAL)"
    )
    conn.execute(
        "INSERT INTO indicadores_sector VALUES (2025, 'C', 'Manufactura', 0.08)"
    )
    conn.commit()
    conn.close()


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "financials.sqlite3"
    _build_db(path)
    monkeypatch.setattr(supercias_financials, "DB_PATH", path)
    return path


def test_resolve_expediente_distinguishes_ruc_from_expediente():
    assert supercias_financials._resolve_expediente("123") == 123
    assert supercias_financials._resolve_expediente("1790013731001") is None
    assert supercias_financials._resolve_expediente("") is None
    assert supercias_financials._resolve_expediente("abc") is None


def test_check_db_fresh_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.sqlite3"
    with pytest.raises(supercias_financials.FinancialsDbUnavailable, match="no existe"):
        supercias_financials._check_db_fresh(missing)


def test_check_db_fresh_stale_file(tmp_path):
    path = tmp_path / "old.sqlite3"
    path.write_bytes(b"")
    old_time = time.time() - 8 * 24 * 3600
    os.utime(path, (old_time, old_time))
    with pytest.raises(
        supercias_financials.FinancialsDbUnavailable, match="desactualizada"
    ):
        supercias_financials._check_db_fresh(path)


async def test_get_financials_by_expediente(db_path):
    result = await supercias_financials.get_financials("1")

    assert result["expediente"] == 1
    assert result["nombre"] == "ACME"
    assert result["ruc"] == "1790013731001"
    assert [y["anio"] for y in result["years"]] == [2025, 2024]


async def test_get_financials_by_expediente_not_in_companias(db_path):
    # Financial data must still come back even if the company is missing
    # from the companias table (bi_ranking.csv and bi_compania.csv aren't
    # guaranteed to be in perfect lockstep) -- only nombre/ruc is best-effort.
    result = await supercias_financials.get_financials("3")

    assert result["expediente"] == 3
    assert result["nombre"] is None
    assert result["ruc"] is None
    assert [y["anio"] for y in result["years"]] == [2025]


async def test_get_financials_by_ruc(db_path):
    result = await supercias_financials.get_financials("1790004724001")

    assert result["expediente"] == 2
    assert result["nombre"] == "OTRA S.A."
    assert len(result["years"]) == 1


async def test_get_financials_ruc_not_found(db_path):
    result = await supercias_financials.get_financials("0000000000000")

    assert result["error"] == "not_found"
    assert result["years"] == []


async def test_search_ranking_filters_and_sorts(db_path):
    result = await supercias_financials.search_ranking(anio=2025)
    assert result["total"] == 3
    # Sorted ascending by posicion_general by default.
    assert [c["expediente"] for c in result["companias"]] == [2, 1, 3]


async def test_search_ranking_includes_company_name_and_ruc(db_path):
    result = await supercias_financials.search_ranking(anio=2025, ciiu_n1="c")
    by_expediente = {c["expediente"]: c for c in result["companias"]}

    assert by_expediente[1]["nombre"] == "ACME"
    assert by_expediente[1]["ruc"] == "1790013731001"
    # expediente 3 has no companias row -- LEFT JOIN must still return the
    # ranking row, with nombre/ruc as None, not drop it.
    assert by_expediente[3]["nombre"] is None
    assert by_expediente[3]["ruc"] is None


async def test_search_ranking_filters_by_ciiu(db_path):
    result = await supercias_financials.search_ranking(anio=2025, ciiu_n1="g")
    assert result["total"] == 1
    assert result["companias"][0]["expediente"] == 2


async def test_search_ranking_rejects_unknown_order_by(db_path):
    # Falls back to posicion_general instead of raising/injecting SQL.
    result = await supercias_financials.search_ranking(
        anio=2025, order_by="DROP TABLE ranking;--"
    )
    assert result["total"] == 3


async def test_get_sector_benchmark(db_path):
    benchmark = await supercias_financials.get_sector_benchmark(2025, "c")
    assert benchmark is not None
    assert benchmark["descripcion"] == "Manufactura"

    missing = await supercias_financials.get_sector_benchmark(2025, "z")
    assert missing is None
