import importlib.util
import sqlite3
from pathlib import Path

import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "build_supercias_financials_db.py"
)
_spec = importlib.util.spec_from_file_location(
    "build_supercias_financials_db", _SCRIPT_PATH
)
build_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_script)


def _valid_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE ranking (anio INTEGER, expediente INTEGER, "
        "posicion_general INTEGER)"
    )
    conn.execute("INSERT INTO ranking VALUES (2025, 1, 10)")
    conn.execute(
        "CREATE TABLE companias (expediente INTEGER, ruc TEXT, nombre TEXT)"
    )
    conn.execute("INSERT INTO companias VALUES (1, '1790013731001', 'ACME')")
    conn.execute("CREATE TABLE segmentos (id_segmento INTEGER, segmento TEXT)")
    conn.execute("CREATE TABLE ciiu (ciiu TEXT, descripcion TEXT)")
    conn.execute(
        "CREATE TABLE indicadores_sector (anio INTEGER, ciiu_n1 TEXT)"
    )
    conn.commit()
    conn.close()


def test_verify_build_accepts_well_formed_db(tmp_path):
    path = tmp_path / "ok.sqlite3"
    _valid_db(path)
    build_script._verify_build(path)  # must not raise


def test_verify_build_rejects_empty_ranking_table(tmp_path):
    path = tmp_path / "empty.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE ranking (anio INTEGER, expediente INTEGER, "
        "posicion_general INTEGER)"
    )
    conn.execute(
        "CREATE TABLE companias (expediente INTEGER, ruc TEXT, nombre TEXT)"
    )
    conn.execute("INSERT INTO companias VALUES (1, '1790013731001', 'ACME')")
    conn.execute("CREATE TABLE segmentos (id_segmento INTEGER, segmento TEXT)")
    conn.execute("CREATE TABLE ciiu (ciiu TEXT, descripcion TEXT)")
    conn.execute("CREATE TABLE indicadores_sector (anio INTEGER, ciiu_n1 TEXT)")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="'ranking' quedó vacía"):
        build_script._verify_build(path)


def test_verify_build_rejects_empty_companias_table(tmp_path):
    path = tmp_path / "empty_companias.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE ranking (anio INTEGER, expediente INTEGER, "
        "posicion_general INTEGER)"
    )
    conn.execute("INSERT INTO ranking VALUES (2025, 1, 10)")
    conn.execute(
        "CREATE TABLE companias (expediente INTEGER, ruc TEXT, nombre TEXT)"
    )
    conn.execute("CREATE TABLE segmentos (id_segmento INTEGER, segmento TEXT)")
    conn.execute("CREATE TABLE ciiu (ciiu TEXT, descripcion TEXT)")
    conn.execute("CREATE TABLE indicadores_sector (anio INTEGER, ciiu_n1 TEXT)")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="'companias' quedó vacía"):
        build_script._verify_build(path)


def test_verify_build_rejects_missing_required_column(tmp_path):
    path = tmp_path / "missing_col.sqlite3"
    conn = sqlite3.connect(path)
    # 'posicion_general' missing.
    conn.execute("CREATE TABLE ranking (anio INTEGER, expediente INTEGER)")
    conn.execute("INSERT INTO ranking VALUES (2025, 1)")
    conn.execute(
        "CREATE TABLE companias (expediente INTEGER, ruc TEXT, nombre TEXT)"
    )
    conn.execute("INSERT INTO companias VALUES (1, '1790013731001', 'ACME')")
    conn.execute("CREATE TABLE segmentos (id_segmento INTEGER, segmento TEXT)")
    conn.execute("CREATE TABLE ciiu (ciiu TEXT, descripcion TEXT)")
    conn.execute("CREATE TABLE indicadores_sector (anio INTEGER, ciiu_n1 TEXT)")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="posicion_general"):
        build_script._verify_build(path)


def test_verify_build_rejects_missing_table(tmp_path):
    path = tmp_path / "missing_table.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE ranking (anio INTEGER, expediente INTEGER, "
        "posicion_general INTEGER)"
    )
    conn.execute("INSERT INTO ranking VALUES (2025, 1, 10)")
    # 'companias', 'segmentos', 'ciiu', 'indicadores_sector' never created.
    # PRAGMA table_info on a missing table returns no rows rather than
    # erroring, so this surfaces as "missing all required columns", not a
    # distinct "no such table" error -- either way, _verify_build must
    # reject it. 'companias' is checked right after 'ranking', so that's
    # the table named in the error here.
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="companias"):
        build_script._verify_build(path)
