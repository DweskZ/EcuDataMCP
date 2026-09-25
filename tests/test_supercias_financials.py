import os
import sqlite3
import sys
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
    conn.execute(f"PRAGMA user_version = {supercias_financials.SCHEMA_VERSION}")
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    # The lock and state files live next to DB_PATH; keep every test away
    # from the real data/ directory (a real failed build there would put
    # these tests in backoff).
    monkeypatch.setattr(
        supercias_financials, "DB_PATH", tmp_path / "data" / "financials.sqlite3"
    )
    monkeypatch.setattr(supercias_financials, "_build_started_at", None)


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


@pytest.fixture
def no_real_build(monkeypatch):
    """Stub the background build launcher so these tests never spawn the
    real script (network download) just for hitting a missing/stale DB."""
    calls: list[None] = []
    monkeypatch.setattr(
        supercias_financials, "_trigger_background_build", lambda: calls.append(None)
    )
    return calls


def test_check_db_fresh_missing_file(tmp_path, no_real_build):
    missing = tmp_path / "does_not_exist.sqlite3"
    with pytest.raises(supercias_financials.FinancialsDbUnavailable, match="no existe"):
        supercias_financials._check_db_fresh(missing)
    assert no_real_build == [None]


def test_check_db_fresh_serves_stale_file_and_refreshes(tmp_path, no_real_build):
    # A stale DB is still the latest valid build: serve it (flagged) while a
    # refresh runs, instead of turning a Supercías outage into a tool outage.
    path = tmp_path / "old.sqlite3"
    _build_db(path)
    old_time = time.time() - 8 * 24 * 3600
    os.utime(path, (old_time, old_time))

    assert supercias_financials._check_db_fresh(path) is True
    assert no_real_build == [None]
    status = supercias_financials.financials_status(path)
    assert status["disponible"] is True
    assert status["desactualizada"] is True
    assert status["anios"] == [2024, 2025]


class _RunningProcess:
    pid = 4242

    def poll(self):
        return None


def test_trigger_background_build_backs_off_after_failure(monkeypatch):
    popen_calls: list[list[str]] = []
    monkeypatch.setattr(supercias_financials, "_build_process", None)
    monkeypatch.setattr(
        supercias_financials.subprocess,
        "Popen",
        lambda args, **kw: popen_calls.append(args) or _RunningProcess(),
    )
    supercias_financials.write_build_state(
        {
            "fallos_consecutivos": 1,
            "ultimo_intento_ts": time.time() - 60,
            "ultimo_error": "ConnectError: boom",
        }
    )

    supercias_financials._trigger_background_build()
    assert popen_calls == []

    # Once the 1-hour backoff for a single failure has elapsed, retry.
    supercias_financials.write_build_state(
        {"fallos_consecutivos": 1, "ultimo_intento_ts": time.time() - 3700}
    )
    supercias_financials._trigger_background_build()
    assert len(popen_calls) == 1


def test_trigger_background_build_skips_while_lock_held(monkeypatch):
    popen_calls: list[list[str]] = []
    monkeypatch.setattr(supercias_financials, "_build_process", None)
    monkeypatch.setattr(
        supercias_financials.subprocess,
        "Popen",
        lambda args, **kw: popen_calls.append(args) or _RunningProcess(),
    )
    lock = supercias_financials.lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("123")

    supercias_financials._trigger_background_build()
    assert popen_calls == []

    # An abandoned lock (older than the build timeout) no longer blocks.
    old = time.time() - supercias_financials.BUILD_TIMEOUT_SECONDS - 60
    os.utime(lock, (old, old))
    supercias_financials._trigger_background_build()
    assert len(popen_calls) == 1


def test_build_in_progress_kills_hung_build(monkeypatch):
    killed: list[bool] = []

    class _HungProcess:
        pid = 4242

        def poll(self):
            return None

        def kill(self):
            killed.append(True)

    monkeypatch.setattr(supercias_financials, "_build_process", _HungProcess())
    monkeypatch.setattr(
        supercias_financials,
        "_build_started_at",
        time.time() - supercias_financials.BUILD_TIMEOUT_SECONDS - 1,
    )

    assert supercias_financials._build_in_progress() is False
    assert killed == [True]


def test_missing_db_message_reports_last_failure(tmp_path, no_real_build):
    supercias_financials.write_build_state(
        {
            "fallos_consecutivos": 2,
            "ultimo_intento_ts": time.time(),
            "ultimo_intento": "2026-09-25T00:00:00+00:00",
            "ultimo_error": "ConnectError: Supercías caído",
        }
    )
    with pytest.raises(
        supercias_financials.FinancialsDbUnavailable, match="Supercías caído"
    ):
        supercias_financials._check_db_fresh(tmp_path / "missing.sqlite3")


def test_financials_status_missing_db(tmp_path):
    status = supercias_financials.financials_status(tmp_path / "missing.sqlite3")
    assert status["disponible"] is False
    assert status["anios"] is None


def test_trigger_background_build_spawns_once_while_running(monkeypatch):
    popen_calls: list[list[str]] = []

    class _FakeProcess:
        def __init__(self):
            self.pid = 4242

        def poll(self):
            return None  # still running

    def fake_popen(args, **kwargs):
        popen_calls.append(args)
        return _FakeProcess()

    monkeypatch.setattr(supercias_financials, "_build_process", None)
    monkeypatch.setattr(supercias_financials.subprocess, "Popen", fake_popen)

    supercias_financials._trigger_background_build()
    supercias_financials._trigger_background_build()

    assert len(popen_calls) == 1
    assert popen_calls[0][0] == sys.executable
    assert popen_calls[0][1].endswith("build_supercias_financials_db.py")


def test_trigger_background_build_spawns_again_once_previous_finished(monkeypatch):
    popen_calls: list[list[str]] = []

    class _FakeProcess:
        def __init__(self, exit_code):
            self.pid = 4242
            self._exit_code = exit_code

        def poll(self):
            return self._exit_code

    processes = [_FakeProcess(None), _FakeProcess(0)]

    def fake_popen(args, **kwargs):
        popen_calls.append(args)
        return processes[len(popen_calls) - 1]

    monkeypatch.setattr(supercias_financials, "_build_process", None)
    monkeypatch.setattr(supercias_financials.subprocess, "Popen", fake_popen)

    supercias_financials._trigger_background_build()
    processes[0]._exit_code = 0  # first build finished
    supercias_financials._trigger_background_build()

    assert len(popen_calls) == 2


def test_ensure_financials_db_fresh_swallows_missing_db(tmp_path, monkeypatch):
    monkeypatch.setattr(supercias_financials, "DB_PATH", tmp_path / "missing.sqlite3")
    triggered: list[None] = []
    monkeypatch.setattr(
        supercias_financials, "_trigger_background_build", lambda: triggered.append(None)
    )

    supercias_financials.ensure_financials_db_fresh()  # must not raise

    assert triggered == [None]


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


async def test_get_financials_ambiguous_ruc_returns_candidates(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO companias VALUES (4, '1790004724001', 'OTRA DUP')")
    conn.commit()
    conn.close()

    result = await supercias_financials.get_financials("1790004724001")

    assert result["error"] == "ambiguous"
    assert [c["expediente"] for c in result["candidatos"]] == [2, 4]


async def test_search_ranking_defaults_to_latest_year(db_path):
    result = await supercias_financials.search_ranking()
    assert result["anio"] == 2025
    assert {c["anio"] for c in result["companias"]} == {2025}


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
    with pytest.raises(ValueError, match="order_by inválido"):
        await supercias_financials.search_ranking(
            anio=2025, order_by="DROP TABLE ranking;--"
        )


async def test_search_ranking_descending_sorts_highest_first(db_path):
    result = await supercias_financials.search_ranking(
        anio=2025, order_by="posicion_general", descending=True
    )
    positions = [c["posicion_general"] for c in result["companias"]]
    assert positions == sorted(positions, reverse=True)


async def test_get_sector_benchmark(db_path):
    benchmark = await supercias_financials.get_sector_benchmark(2025, "c")
    assert benchmark is not None
    assert benchmark["descripcion"] == "Manufactura"

    missing = await supercias_financials.get_sector_benchmark(2025, "z")
    assert missing is None


def test_check_db_fresh_rebuilds_outdated_schema_version(tmp_path, no_real_build):
    path = tmp_path / "old_schema.sqlite3"
    _build_db(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    with pytest.raises(supercias_financials.FinancialsDbUnavailable, match="esquema"):
        supercias_financials._check_db_fresh(path)
    assert no_real_build == [None]


def test_trigger_background_build_never_inherits_stdio(monkeypatch, tmp_path):
    # Under the stdio transport, stdout is the JSON-RPC stream: the build's
    # print() output must not reach it or the client drops the connection.
    popen_kwargs: list[dict] = []

    class _FakeProcess:
        pid = 4242

        def poll(self):
            return None

    def fake_popen(args, **kwargs):
        popen_kwargs.append(kwargs)
        return _FakeProcess()

    monkeypatch.setattr(supercias_financials, "DB_PATH", tmp_path / "db.sqlite3")
    monkeypatch.setattr(supercias_financials, "_build_process", None)
    monkeypatch.setattr(supercias_financials.subprocess, "Popen", fake_popen)

    supercias_financials._trigger_background_build()

    kwargs = popen_kwargs[0]
    assert kwargs["stdin"] is supercias_financials.subprocess.DEVNULL
    assert kwargs["stdout"] not in (None, sys.stdout)
    assert kwargs["stderr"] is supercias_financials.subprocess.STDOUT
    assert (tmp_path / "supercias_build.log").exists()
