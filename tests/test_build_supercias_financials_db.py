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
        "posicion_general INTEGER, n_empleados INTEGER)"
    )
    conn.execute("INSERT INTO ranking VALUES (2025, 1, 10, 5)")
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


def test_quote_ident_escapes_embedded_double_quote():
    assert build_script._quote_ident('bad"col') == '"bad""col"'


def test_load_csv_table_handles_header_with_embedded_quote(tmp_path):
    # A CSV header field of "weird""col" is standard CSV escaping for a
    # literal double quote inside the column name -- exactly the character
    # that would break an unescaped f-string-built CREATE TABLE statement.
    csv_path = tmp_path / "weird.csv"
    csv_path.write_text('anio,"weird""col"\n2025,5\n', encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "out.sqlite3")

    header = build_script._load_csv_table(conn, csv_path, "t", {"anio"}, set())

    assert header == ["anio", 'weird"col']
    rows = conn.execute('SELECT anio, "weird""col" FROM t').fetchall()
    assert rows == [(2025, 5.0)]


def test_convert_parses_european_decimal_notation():
    assert build_script._convert("7.760,2", "REAL") == 7760.2
    assert build_script._convert("1500", "REAL") == 1500.0


def test_convert_handles_decimal_formatted_integer_column():
    # bi_ranking.csv's n_empleados is declared INTEGER here but the source
    # ships it as a decimal string ("2.00", "11547.00") like its REAL-typed
    # neighbors -- confirmed live 2026-09-21 against the real CSV
    # (Corporación Favorita, expediente 384, año 2024: "11547.00"). A bare
    # int("2.00") raises ValueError, which used to silently null out every
    # single n_empleados value in the built database.
    assert build_script._convert("2.00", "INTEGER") == 2
    assert build_script._convert("11547.00", "INTEGER") == 11547
    # Genuinely non-numeric INTEGER-column values still fall back to None
    # rather than raising.
    assert build_script._convert("n/a", "INTEGER") is None


def test_verify_build_accepts_well_formed_db(tmp_path):
    path = tmp_path / "ok.sqlite3"
    _valid_db(path)
    build_script._verify_build(path)  # must not raise


def test_verify_build_rejects_empty_ranking_table(tmp_path):
    path = tmp_path / "empty.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE ranking (anio INTEGER, expediente INTEGER, "
        "posicion_general INTEGER, n_empleados INTEGER)"
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
        "posicion_general INTEGER, n_empleados INTEGER)"
    )
    conn.execute("INSERT INTO ranking VALUES (2025, 1, 10, 5)")
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
        "posicion_general INTEGER, n_empleados INTEGER)"
    )
    conn.execute("INSERT INTO ranking VALUES (2025, 1, 10, 5)")
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


def test_load_csv_table_rejects_many_malformed_rows(tmp_path):
    csv_path = tmp_path / "truncated.csv"
    csv_path.write_text("anio,valor\n2025,1\n2025\n", encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "out.sqlite3")
    with pytest.raises(RuntimeError, match="truncado"):
        build_script._load_csv_table(conn, csv_path, "t", {"anio"}, set())


def test_check_not_shrunk_rejects_sharp_drop(tmp_path):
    previous = tmp_path / "prev.sqlite3"
    new = tmp_path / "new.sqlite3"
    for path, rows in ((previous, 10), (new, 5)):
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE ranking (anio INTEGER)")
        conn.executemany("INSERT INTO ranking VALUES (?)", [(2025,)] * rows)
        conn.commit()
        conn.close()

    with pytest.raises(RuntimeError, match="bajó de 10 a 5"):
        build_script._check_not_shrunk(new, previous)
    build_script._check_not_shrunk(previous, new)  # growth is fine
    build_script._check_not_shrunk(new, tmp_path / "none.sqlite3")  # no previous


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    from helpers import supercias_financials

    monkeypatch.setattr(
        supercias_financials, "DB_PATH", tmp_path / "data" / "financials.sqlite3"
    )
    return supercias_financials


def test_main_skips_when_lock_held(isolated_state, monkeypatch):
    built: list[bool] = []
    monkeypatch.setattr(build_script, "_build", lambda: built.append(True))
    lock = isolated_state.lock_path()
    lock.parent.mkdir(parents=True)
    lock.write_text("1")

    build_script.main()

    assert built == []
    assert lock.exists()  # another build's lock is left alone


def test_main_records_failure_and_releases_lock(isolated_state, monkeypatch):
    def boom():
        raise ConnectionError("Supercías caído")

    monkeypatch.setattr(build_script, "_build", boom)
    with pytest.raises(ConnectionError):
        build_script.main()
    with pytest.raises(ConnectionError):
        build_script.main()

    state = isolated_state.read_build_state()
    assert state["fallos_consecutivos"] == 2
    assert "Supercías caído" in state["ultimo_error"]
    assert not isolated_state.lock_path().exists()

    monkeypatch.setattr(build_script, "_build", lambda: None)
    build_script.main()
    state = isolated_state.read_build_state()
    assert state["fallos_consecutivos"] == 0
    assert state["ultimo_error"] is None


def test_convert_integer_rejects_inf_and_fractions_without_raising():
    assert build_script._convert("inf", "INTEGER") is None
    assert build_script._convert("2.5", "INTEGER") is None


def test_verify_build_rejects_all_null_n_empleados(tmp_path):
    path = tmp_path / "null_empleados.sqlite3"
    _valid_db(path)
    conn = sqlite3.connect(path)
    conn.execute("UPDATE ranking SET n_empleados = NULL")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="n_empleados"):
        build_script._verify_build(path)
