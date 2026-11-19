import os
import sqlite3
from pathlib import Path

import pytest

from helpers import supercias_financials_build as build_script


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
        "CREATE TABLE cuartiles_sector (anio INTEGER, ciiu_n1 TEXT, "
        "indicador TEXT, mediana REAL)"
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
    conn.execute(
        "CREATE TABLE cuartiles_sector (anio INTEGER, ciiu_n1 TEXT, "
        "indicador TEXT, mediana REAL)"
    )
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
    conn.execute(
        "CREATE TABLE cuartiles_sector (anio INTEGER, ciiu_n1 TEXT, "
        "indicador TEXT, mediana REAL)"
    )
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
    conn.execute(
        "CREATE TABLE cuartiles_sector (anio INTEGER, ciiu_n1 TEXT, "
        "indicador TEXT, mediana REAL)"
    )
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
    # 'companias', 'segmentos', 'ciiu', 'cuartiles_sector' never created.
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
    lock.write_text(str(os.getpid()))  # a live build

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


def test_replace_with_retry_waits_out_windows_reader(monkeypatch, tmp_path):
    # On Windows os.replace raises PermissionError while a reader holds the
    # target open; a 15-20 minute build must not be discarded over that.
    src = tmp_path / "db.building"
    dst = tmp_path / "db.sqlite"
    src.write_bytes(b"new")
    dst.write_bytes(b"old")
    attempts: list[int] = []
    real_replace = os.replace

    def flaky_replace(a, b):
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError(5, "Access is denied")
        real_replace(a, b)

    sleeps: list[float] = []
    monkeypatch.setattr(os, "replace", flaky_replace)
    monkeypatch.setattr(build_script.time, "sleep", lambda s: sleeps.append(s))

    build_script._replace_with_retry(src, dst)

    assert dst.read_bytes() == b"new"
    assert not src.exists()
    assert len(attempts) == 3
    assert len(sleeps) == 2


def test_replace_with_retry_gives_up_after_max_attempts(monkeypatch, tmp_path):
    src = tmp_path / "db.building"
    dst = tmp_path / "db.sqlite"
    src.write_bytes(b"new")

    def always_locked(a, b):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(os, "replace", always_locked)
    monkeypatch.setattr(build_script.time, "sleep", lambda s: None)

    with pytest.raises(PermissionError):
        build_script._replace_with_retry(src, dst)


def _ranking_csv(years: range) -> bytes:
    lines = ["anio,expediente,posicion_general,id_estado_financiero,n_empleados,ciiu_n1,roe"]
    for year in years:
        # Ratios only from 2018 and CIIU only from 2009, like the real export.
        roe = '"0,15"' if year >= 2018 else ""
        ciiu = "C" if year >= 2009 else ""
        lines.append(f"{year},1,1,{year}01,12.00,{ciiu},{roe}")
        lines.append(f"{year},2,,,3.00,{ciiu},")  # unranked: no statement
    return ("\n".join(lines) + "\n").encode("utf-8")


@pytest.fixture
def mocked_export(httpx_mock, isolated_state, monkeypatch):
    """Serve a tiny Supercías export (2008-2025) through pytest-httpx."""
    monkeypatch.setattr(build_script, "DB_PATH", isolated_state.DB_PATH)
    monkeypatch.delenv("ECUADOR_MCP_SUPERCIAS_YEARS", raising=False)
    files = {
        "bi_ranking.csv": _ranking_csv(range(2008, 2026)),
        "bi_compania.csv": b"expediente,ruc,nombre\n1,1790013731001,ACME\n",
        "bi_segmento.csv": b"id_segmento,segmento\n1,GRANDE\n",
        "bi_ciiu.csv": b"ciiu,descripcion\nC,Manufactura\n",
    }
    for name, body in files.items():
        httpx_mock.add_response(url=build_script._RESOURCES_BASE + name, content=body)
    return isolated_state.DB_PATH


def test_build_keeps_every_published_year(mocked_export):
    build_script._build()

    conn = sqlite3.connect(mocked_export)
    years = [r[0] for r in conn.execute("SELECT DISTINCT anio FROM ranking ORDER BY anio")]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    conn.close()
    assert years == list(range(2008, 2026))
    # Sector benchmarks come from the ranking itself, not indicadores_sector.csv.
    assert "cuartiles_sector" in tables
    assert "indicadores_sector" not in tables
    assert version == build_script.SCHEMA_VERSION


def test_build_honours_retention_setting(mocked_export, monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_SUPERCIAS_YEARS", "3")
    build_script._build()

    conn = sqlite3.connect(mocked_export)
    years = [r[0] for r in conn.execute("SELECT DISTINCT anio FROM ranking ORDER BY anio")]
    conn.close()
    assert years == [2023, 2024, 2025]


@pytest.mark.parametrize("value", ["0", "-2", "cinco"])
def test_years_to_keep_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("ECUADOR_MCP_SUPERCIAS_YEARS", value)
    with pytest.raises(ValueError, match="ECUADOR_MCP_SUPERCIAS_YEARS"):
        build_script._years_to_keep()


@pytest.mark.parametrize("value", ["", "all", "ALL"])
def test_years_to_keep_defaults_to_full_history(monkeypatch, value):
    monkeypatch.setenv("ECUADOR_MCP_SUPERCIAS_YEARS", value)
    assert build_script._years_to_keep() is None


def test_verify_build_rejects_a_missing_year(tmp_path):
    path = tmp_path / "gap.sqlite3"
    _valid_db(path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO ranking VALUES (2023, 1, 12, 5)")  # 2024 missing
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="falta al menos un año"):
        build_script._verify_build(path)


def test_check_not_shrunk_compares_only_the_new_year_range(tmp_path):
    # Lowering the retention setting drops old years on purpose; only a drop
    # inside the years both builds share means a truncated source file.
    previous = tmp_path / "prev.sqlite3"
    new = tmp_path / "new.sqlite3"
    for path, rows in (
        (previous, [(2010,)] * 50 + [(2025,)] * 10),
        (new, [(2025,)] * 10),
    ):
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE ranking (anio INTEGER)")
        conn.executemany("INSERT INTO ranking VALUES (?)", rows)
        conn.commit()
        conn.close()

    build_script._check_not_shrunk(new, previous)


def test_main_reclaims_lock_of_dead_build(isolated_state, monkeypatch):
    # A build killed with its stdio session never removes its lock; a dead
    # PID must free it at once, not after the 45-minute timeout.
    built: list[bool] = []
    monkeypatch.setattr(build_script, "_build", lambda: built.append(True))
    monkeypatch.setattr(isolated_state, "_pid_alive", lambda pid: False)
    lock = isolated_state.lock_path()
    lock.parent.mkdir(parents=True)
    lock.write_text("999999")

    build_script.main()

    assert built == [True]
    assert not lock.exists()


def test_acquire_lock_records_own_pid(isolated_state):
    assert build_script._acquire_lock() is True
    assert isolated_state.read_lock_pid() == os.getpid()
    assert build_script._acquire_lock() is False  # held by a live process


def test_reclaiming_the_lock_of_a_dead_build_says_so_in_the_log(
    isolated_state, monkeypatch, capsys
):
    # A build that vanishes leaves no traceback and no state: the next run's
    # log is the only place that records it happened.
    monkeypatch.setattr(isolated_state, "_pid_alive", lambda pid: False)
    lock = isolated_state.lock_path()
    lock.parent.mkdir(parents=True)
    lock.write_text("31337")

    assert build_script._acquire_lock() is True

    out = capsys.readouterr().out
    assert "PID 31337" in out and "no liberó el lock" in out


def test_a_fresh_lock_acquisition_prints_nothing(isolated_state, capsys):
    assert build_script._acquire_lock() is True
    assert capsys.readouterr().out == ""


class _FakeKernel32:
    def __init__(self):
        self.states: list[int] = []

    def SetThreadExecutionState(self, flags):
        self.states.append(flags)


def test_keep_awake_holds_and_releases_the_system_required_state_on_windows(monkeypatch):
    kernel32 = _FakeKernel32()
    fake_ctypes = type("C", (), {"windll": type("W", (), {"kernel32": kernel32})})
    monkeypatch.setattr(build_script, "ctypes", fake_ctypes)
    monkeypatch.setattr(build_script.sys, "platform", "win32")

    with build_script._keep_awake():
        assert kernel32.states == [0x80000001]  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    assert kernel32.states == [0x80000001, 0x80000000]


def test_keep_awake_releases_the_state_when_the_build_fails(monkeypatch):
    kernel32 = _FakeKernel32()
    fake_ctypes = type("C", (), {"windll": type("W", (), {"kernel32": kernel32})})
    monkeypatch.setattr(build_script, "ctypes", fake_ctypes)
    monkeypatch.setattr(build_script.sys, "platform", "win32")

    with pytest.raises(RuntimeError), build_script._keep_awake():
        raise RuntimeError("boom")

    assert kernel32.states[-1] == 0x80000000


def test_keep_awake_does_nothing_off_windows(monkeypatch):
    monkeypatch.setattr(build_script.sys, "platform", "linux")

    with build_script._keep_awake():
        pass  # no windll on this platform; touching it would raise


def _ratio_db(rows: list[tuple]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ranking (anio INTEGER, ciiu_n1 TEXT, "
        "id_estado_financiero INTEGER, ingresos_ventas REAL, activos REAL, "
        "patrimonio REAL, liquidez_corriente REAL, margen_operacional REAL, "
        "end_largo_plazo REAL, roe REAL)"
    )
    conn.executemany("INSERT INTO ranking VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return conn


def test_null_uncalculated_ratios():
    conn = _ratio_db(
        [
            # Operating company: margen_operacional 0 is Supercías' "not
            # calculated"; end_largo_plazo 0 (no long-term debt) is real.
            (2023, "G", 1, 100.0, 50.0, 20.0, 1.5, 0.0, 0.0, 0.12),
            # No sales: sales-based ratios are undefined, the rest stay.
            (2023, "G", 2, 0.0, 50.0, 20.0, 1.2, 0.0, 0.1, 0.0),
            # Every ratio 0: none was calculated.
            (2023, "G", 3, 100.0, 50.0, 20.0, 0.0, 0.0, 0.0, 0.0),
            # No financial statement that year.
            (2023, "G", None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            # Equity 0: roe undefined.
            (2023, "G", 5, 100.0, 50.0, 0.0, 2.0, 0.05, 0.3, 0.0),
        ]
    )

    build_script._null_uncalculated_ratios(conn)

    rows = conn.execute(
        "SELECT liquidez_corriente, margen_operacional, end_largo_plazo, roe "
        "FROM ranking ORDER BY rowid"
    ).fetchall()
    assert rows == [
        (1.5, None, 0.0, 0.12),
        (1.2, None, 0.1, 0.0),
        (None, None, None, None),
        (None, None, None, None),
        (2.0, 0.05, 0.3, None),
    ]


def test_build_sector_quartiles_uses_quartiles_not_means():
    # One extreme filing would drag a mean to ~200; the quartiles ignore it.
    values = [0.5, 1.0, 1.5, 2.0, 1000.0]
    conn = _ratio_db(
        [
            (2023, "C", i, 100.0, 50.0, 20.0, v, None, None, None)
            for i, v in enumerate(values, 1)
        ]
        # Too few filings for a benchmark.
        + [(2023, "A", 9, 100.0, 50.0, 20.0, 1.0, None, None, None)]
        # Ratios not calculated don't count as filings.
        + [(2023, "C", 10, 100.0, 50.0, 20.0, None, None, None, None)]
    )

    build_script._build_sector_quartiles(conn)

    rows = conn.execute(
        "SELECT anio, ciiu_n1, indicador, n, p25, mediana, p75 FROM cuartiles_sector"
    ).fetchall()
    assert rows == [(2023, "C", "liquidez_corriente", 5, 1.0, 1.5, 2.0)]
