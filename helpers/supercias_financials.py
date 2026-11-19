"""Query layer over the Supercías financial-ranking dataset (bi_ranking.csv).

Distinct from helpers/supercias_client.py's company directory: this is the
"Ranking" dataset (https://appscvsmovil.supercias.gob.ec/ranking/reporte.html),
derived from real balance-sheet filings — revenue, assets, equity, profit,
and ~38 financial ratios per company per fiscal year. The directory only has
"capital suscrito"; this has actual financial performance.

The source CSV (bi_ranking.csv) is ~356 MB / ~1.7M rows covering fiscal years
2008-present, too large to hold in memory the way supercias_client.py holds
the (also large, but 10x smaller) company directory. Instead this module only
ever *queries* a local SQLite database that
`helpers/supercias_financials_build.py` builds ahead of time, with every year
the export carries. Older years carry fewer columns (financial ratios only
from 2018, CIIU from 2009), so queries check that the requested year and
column actually have data before answering.

Building takes ~15-20 minutes (the 356 MB download dominates), too slow to run
inline inside a single MCP tool call. Instead, `_check_db_fresh` launches
that script as a background subprocess -- via `_trigger_background_build`
-- the moment it notices the DB is missing or older than
`_MAX_DB_AGE_SECONDS`, both from `ensure_financials_db_fresh()` at server
startup (see main.py) and from every query that hits a missing/stale DB.
A missing DB raises `FinancialsDbUnavailable`; a stale one keeps being
served, flagged through `financials_status()`, while the refresh runs.
Failed builds back off (1h/6h/24h, recorded in supercias_build.state.json)
and the build script's lock file keeps concurrent processes from building
at the same time. The build runs detached from the server (own session on
POSIX, outside the client's job object on Windows when allowed), and its
lock holds its PID, so a build killed anyway frees the lock at once instead
of blocking retries until the 45-minute timeout.

The build also turns ratios Supercías could not calculate (stored as 0)
into NULL and precomputes per-sector quartiles (`cuartiles_sector`), which
replace Supercías' own sector means (`indicadores_sector.csv`): those are
plain means that a few extreme filings dominate.

Company names/RUCs are resolved from this same SQLite DB's own `companias`
table (loaded from bi_compania.csv by the build script), not by calling into
helpers.supercias_client's separately-cached directory. An earlier version
did the latter and had a real bug for it: get_financials(expediente) needed
a name/RUC lookup, that module's search only matched name/RUC text (not
expediente), so the lookup silently failed almost every time. Duplicating
three small columns (expediente, ruc, nombre) for ~226k rows is cheap next
to the size of this DB, and removes that cross-module dependency
entirely -- this module's queries never await anything from
helpers.supercias_client.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from helpers.paths import data_dir
from helpers.response_contract import with_response_metadata

logger = logging.getLogger(__name__)

DB_PATH = data_dir() / "supercias_financials.sqlite3"
# Run as a module, not a scripts/ path: PyPI and MCPB installs ship the
# helpers package but not scripts/.
_BUILD_MODULE = "helpers.supercias_financials_build"
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
# The dataset refreshes far less often than the daily company directory.
# Past this age a refresh is started, but the existing DB keeps being served
# (flagged as stale) -- refusing it would turn a Supercías outage into an
# outage of these tools even though the previous data is still valid.
_MAX_DB_AGE_SECONDS = 7 * 24 * 3600
# A build (download ~356 MB + load) normally takes ~15-20 minutes. Past this,
# a lock or a server-launched process is considered hung and is reclaimed.
BUILD_TIMEOUT_SECONDS = 45 * 60
# Wait before retrying after 1, 2, 3+ consecutive failed builds, so an
# unreachable source doesn't trigger a fresh 356 MB download on every query.
_RETRY_BACKOFF_SECONDS = (3600, 6 * 3600, 24 * 3600)
# Stamped into the built DB as PRAGMA user_version. Bump it whenever a build
# script fix changes the data, so existing DBs are rebuilt on first use
# instead of serving the old data until they age out. 2 = n_empleados fix,
# 3 = full history (2008-present) instead of the last five years, 4 = ratios
# Supercías could not calculate stored as NULL instead of 0, and sector
# quartiles (cuartiles_sector) instead of its sector means.
SCHEMA_VERSION = 4
# Oldest build still served while the rebuild runs: version-2/3 DBs have the
# same ranking columns, only fewer years or zeros for NULLs (and no sector
# quartiles), so refusing them would make the tools unavailable for 15-20
# minutes for no reason.
_MIN_SERVED_SCHEMA_VERSION = 2
_FULL_HISTORY_SCHEMA_VERSION = 3

# Win32 constants for _pid_alive (OpenProcess / GetExitCodeProcess).
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_ACCESS_DENIED = 5
_STILL_ACTIVE = 259
# The build must outlive the server: a stdio client that closes its session
# kills the server's process tree (on Windows, the job object it runs in),
# and with it a build that is 15 minutes into a 20-minute run. A process this
# one creates stays in that job unless the job permits breakaway, and the
# check is silent: CREATE_BREAKAWAY_FROM_JOB is accepted when the *immediate*
# job (the venv launcher's) allows it, while the child still lands in an outer
# job that does not, so no error ever tells us the build is killable. Only a
# process another service creates is outside every job of ours, so
# _spawn_build asks WMI first and uses the detached/breakaway flags only when
# WMI is unavailable.
_WINDOWS_DETACHED_FLAGS = (
    getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
)
_WINDOWS_BREAKAWAY_FLAG = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
_WINDOWS_NO_WINDOW_FLAG = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
# A process WMI creates gets the WMI service's environment, not ours, so the
# variables the build reads are handed over in a file (see
# helpers/supercias_detached_launch.py).
_DETACHED_LAUNCH_MODULE = "helpers.supercias_detached_launch"
_DETACHED_ENV_PREFIXES = ("ECUADOR_MCP_",)
_DETACHED_ENV_NAMES = frozenset({
    "CKAN_INSECURE_TLS", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
})
_WMI_LAUNCH_SECONDS = 30

# Guards the in-process launcher only. Cross-process exclusion (two servers,
# the maintenance container, a manual run) is the build script's lock file.
_build_lock = threading.Lock()
_build_process: subprocess.Popen | _WmiBuild | None = None
_build_started_at: float | None = None

_RANKING_COLUMNS = (
    "anio", "expediente", "posicion_general", "cia_imvalores",
    "id_estado_financiero", "ingresos_ventas", "activos", "patrimonio",
    "utilidad_an_imp", "impuesto_renta", "n_empleados", "ingresos_totales",
    "utilidad_ejercicio", "utilidad_neta", "cod_segmento", "ciiu_n1",
    "ciiu_n6", "liquidez_corriente", "prueba_acida", "end_activo",
    "end_patrimonial", "end_activo_fijo", "end_corto_plazo",
    "end_largo_plazo", "cobertura_interes", "apalancamiento",
    "apalancamiento_financiero", "end_patrimonial_ct", "end_patrimonial_nct",
    "apalancamiento_c_l_plazo", "rot_cartera", "rot_activo_fijo",
    "rot_ventas", "per_med_cobranza", "per_med_pago", "impac_gasto_a_v",
    "impac_carga_finan", "rent_neta_activo", "margen_bruto",
    "margen_operacional", "rent_neta_ventas", "rent_ope_patrimonio",
    "rent_ope_activo", "roe", "roa", "fortaleza_patrimonial",
    "gastos_financieros", "gastos_admin_ventas", "depreciaciones",
    "amortizaciones", "costos_ventas_prod", "deuda_total",
    "deuda_total_c_plazo", "total_gastos",
)

# The ratio columns (2018 onwards); the rest of _RANKING_COLUMNS are ids,
# codes and amounts.
RATIO_COLUMNS = (
    "liquidez_corriente", "prueba_acida", "end_activo", "end_patrimonial",
    "end_activo_fijo", "end_corto_plazo", "end_largo_plazo",
    "cobertura_interes", "apalancamiento", "apalancamiento_financiero",
    "end_patrimonial_ct", "end_patrimonial_nct", "apalancamiento_c_l_plazo",
    "rot_cartera", "rot_activo_fijo", "rot_ventas", "per_med_cobranza",
    "per_med_pago", "impac_gasto_a_v", "impac_carga_finan",
    "rent_neta_activo", "margen_bruto", "margen_operacional",
    "rent_neta_ventas", "rent_ope_patrimonio", "rent_ope_activo", "roe",
    "roa", "fortaleza_patrimonial",
)
# Not on one scale even at the sector median (checked 2021-2025):
# margen_operacional is a fraction in 2021 (median 0.07) but spans about
# -25 to 90 from 2022, and the two "days" ratios have medians of ~1,000
# (cobranza) and ~18,000 (pago), with no fixed factor against 365 /
# rot_cartera. No conversion recovers them, so they are kept as published
# and flagged wherever they are shown.
UNRELIABLE_RATIOS = ("margen_operacional", "per_med_cobranza", "per_med_pago")
UNRELIABLE_RATIOS_NOTE = (
    "margen_operacional, per_med_cobranza y per_med_pago no tienen una escala "
    "coherente en la fuente (ni en la mediana del sector): úsalos con cautela."
)
# Ratios compared against the sector in get_financials (one entry per year).
COMPARISON_COLUMNS = (
    "liquidez_corriente", "prueba_acida", "end_activo", "end_patrimonial",
    "margen_bruto", "rent_neta_ventas", "roe", "roa",
)

# Qualified with the "r." alias used in search_ranking's JOIN query, so an
# unqualified user-supplied order_by can't collide with a companias column.
_ORDERABLE_COLUMNS = frozenset(_RANKING_COLUMNS)


class FinancialsDbUnavailable(Exception):
    """Raised when the SQLite build is missing or has an outdated schema."""


class YearNotLoaded(ValueError):
    """Raised when a requested fiscal year is not in the local DB."""


def lock_path() -> Path:
    return DB_PATH.parent / "supercias_build.lock"


def state_path() -> Path:
    return DB_PATH.parent / "supercias_build.state.json"


def read_build_state() -> dict[str, Any]:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_build_state(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _pid_alive(pid: int) -> bool:
    """True if a process with this PID is still running."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # os.kill(pid, 0) would *terminate* the process on Windows.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = (
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong),
        )
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            # Access denied means it exists but belongs to another user.
            return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_lock_pid() -> int | None:
    """PID recorded in the build lock, or None if missing/unreadable."""
    try:
        return int(lock_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def lock_is_stale() -> bool:
    """True if the lock exists but its build is gone (dead PID or too old).

    A build killed along with its session (a stdio client closing on
    Windows) never reaches the `finally` that removes the lock, so its age
    alone would block every retry for BUILD_TIMEOUT_SECONDS.
    """
    try:
        age = time.time() - lock_path().stat().st_mtime
    except OSError:
        return False
    if age > BUILD_TIMEOUT_SECONDS:
        return True
    pid = read_lock_pid()
    # No PID yet: the lock was created a moment ago and is still being written.
    return pid is not None and not _pid_alive(pid)


def _lock_is_held() -> bool:
    """True while a live build process holds a lock younger than the timeout."""
    return lock_path().exists() and not lock_is_stale()


def _in_backoff(state: dict[str, Any]) -> bool:
    failures = int(state.get("fallos_consecutivos") or 0)
    last_attempt = state.get("ultimo_intento_ts")
    if failures <= 0 or last_attempt is None:
        return False
    wait = _RETRY_BACKOFF_SECONDS[min(failures, len(_RETRY_BACKOFF_SECONDS)) - 1]
    return time.time() - float(last_attempt) < wait


def _kill_build(process: subprocess.Popen | _WmiBuild) -> None:
    """Kill a build subprocess and anything it started.

    On Windows a venv's python.exe is a launcher that runs the real
    interpreter as its child, so `Popen.kill()` ends only the launcher: the
    build keeps running, still holding its lock. `taskkill /T` takes the whole
    tree. Elsewhere the build is the process itself and `kill()` is enough.
    """
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning(
                "taskkill no pudo terminar el árbol del build (PID %d): %s",
                process.pid, exc,
            )
    # Also covers a missing taskkill, and is harmless on an exited process.
    process.kill()


def _build_in_progress() -> bool:
    """True while this process's own build subprocess is still running.

    Mutates `_build_process`: the caller must hold `_build_lock`.
    """
    global _build_process
    if _build_process is None or _build_process.poll() is not None:
        return False
    # Kill a server-launched build that hangs (e.g. a download trickling
    # below httpx's read timeout), or it would block every future refresh.
    if (
        _build_started_at is not None
        and time.time() - _build_started_at > BUILD_TIMEOUT_SECONDS
    ):
        logger.warning(
            "Build de Supercías (PID %d) superó %d min; se termina",
            _build_process.pid, BUILD_TIMEOUT_SECONDS // 60,
        )
        _kill_build(_build_process)
        # Reap it, or a killed POSIX child lingers as a zombie until exit.
        try:
            _build_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning(
                "Build de Supercías (PID %d) no terminó tras kill()",
                _build_process.pid,
            )
        _build_process = None
        return False
    return True


def _process_creation_time(pid: int) -> int | None:
    """Creation time (FILETIME ticks) of a Windows process, None if unreadable.

    A PID can be reused once its process ends; the creation time tells the
    process we started from a later one that got the same number.
    """
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetProcessTimes.argtypes = (ctypes.c_void_p,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not kernel32.GetProcessTimes(
            handle, ctypes.byref(created), ctypes.byref(exited),
            ctypes.byref(kernel), ctypes.byref(user),
        ):
            return None
        return (created.dwHighDateTime << 32) | created.dwLowDateTime
    finally:
        kernel32.CloseHandle(handle)


class _WmiBuild:
    """Stand-in for the Popen of a build that WMI started on our behalf.

    The build is not our child, so there is no exit status and no handle to
    wait on: liveness is the PID plus its creation time, so a reused PID is
    never mistaken for the build (or killed by `_kill_build`).
    """

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode: int | None = None
        self._created = _process_creation_time(pid)

    def poll(self) -> int | None:
        if self.returncode is None:
            same_process = (
                _pid_alive(self.pid)
                and _process_creation_time(self.pid) == self._created
            )
            if not same_process:
                self.returncode = -1  # ended; WMI gives no exit status
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired("supercias build", timeout)
            time.sleep(0.2)
        return self.returncode if self.returncode is not None else -1

    def kill(self) -> None:
        if self.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(self.pid), "/F"],
                capture_output=True, check=False, timeout=10,
            )


def _spawn_via_wmi(log_path: Path) -> _WmiBuild | None:
    """Start the build through the WMI service, outside every job of ours.

    `Win32_Process.Create` makes WMI the parent, so the build survives a
    client that closes its session and tears down the job the server runs in
    (a controlled test showed a plain detached child dying with the job while
    the WMI-created one lived on). Returns None, leaving the caller to fall
    back to a plain detached Popen, when PowerShell or WMI is unavailable.
    """
    powershell = shutil.which("powershell")
    if powershell is None:
        return None
    env_path = log_path.with_name("supercias_build.env.json")
    handed_over = {
        key: value for key, value in os.environ.items()
        if key.upper().startswith(_DETACHED_ENV_PREFIXES)
        or key.upper() in _DETACHED_ENV_NAMES
    }
    command_line = subprocess.list2cmdline(
        [sys.executable, "-m", _DETACHED_LAUNCH_MODULE, str(env_path), str(log_path)]
    )
    script = (
        "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
        "-Arguments @{CommandLine = $env:ECUADOR_MCP_WMI_COMMAND; "
        "CurrentDirectory = $env:ECUADOR_MCP_WMI_CWD}; "
        "if ($r.ReturnValue -ne 0) { exit 1 }; $r.ProcessId"
    )
    try:
        env_path.write_text(json.dumps(handed_over), encoding="utf-8")
        done = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            env={
                **os.environ,
                "ECUADOR_MCP_WMI_COMMAND": command_line,
                "ECUADOR_MCP_WMI_CWD": str(_PACKAGE_ROOT),
            },
            capture_output=True, text=True, check=False,
            timeout=_WMI_LAUNCH_SECONDS, creationflags=_WINDOWS_NO_WINDOW_FLAG,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        env_path.unlink(missing_ok=True)
        logger.warning("No se pudo lanzar el build de Supercías por WMI: %s", exc)
        return None
    pid = done.stdout.strip()
    if done.returncode != 0 or not pid.isdigit():
        env_path.unlink(missing_ok=True)
        logger.warning(
            "WMI no lanzó el build de Supercías (código %d): %s",
            done.returncode, (done.stderr or done.stdout).strip()[:200],
        )
        return None
    return _WmiBuild(int(pid))


def _spawn_build(log_file: Any) -> subprocess.Popen | _WmiBuild:
    """Launch the build detached from this process's session and job."""
    kwargs: dict[str, Any] = {
        "cwd": _PACKAGE_ROOT,
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
        "close_fds": True,
    }
    args = [sys.executable, "-m", _BUILD_MODULE]
    if sys.platform != "win32":
        # Own session: no SIGHUP when the client's terminal/session goes away.
        return subprocess.Popen(args, start_new_session=True, **kwargs)
    via_wmi = _spawn_via_wmi(Path(log_file.name))
    if via_wmi is not None:
        return via_wmi
    try:
        return subprocess.Popen(
            args,
            creationflags=_WINDOWS_DETACHED_FLAGS | _WINDOWS_BREAKAWAY_FLAG,
            **kwargs,
        )
    except PermissionError:
        # The client's job object forbids breakaway; the build still runs
        # detached, but dies if that job is closed.
        logger.warning(
            "No se pudo separar el build de Supercías del job del cliente; "
            "cerrar la sesión puede interrumpirlo"
        )
        return subprocess.Popen(args, creationflags=_WINDOWS_DETACHED_FLAGS, **kwargs)


def _trigger_background_build() -> None:
    """Start helpers/supercias_financials_build.py in the background.

    A no-op while a build is running (in this process, or in any process
    holding the lock file) and while backing off after failed builds -- every
    missing/stale check calls this, so it must be safe to call repeatedly.
    Runs as a separate process (not a thread) because the build is CPU-bound
    CSV parsing plus ~1.7M SQLite inserts; a thread would contend for the GIL
    with the server's own request handling for several minutes.
    """
    global _build_process, _build_started_at
    with _build_lock:
        if _build_in_progress() or _lock_is_held():
            return
        if _in_backoff(read_build_state()):
            return
        # Under the stdio transport the server's stdout IS the JSON-RPC
        # stream: an inherited stdout would let the build's print() progress
        # lines corrupt it and make the client drop the connection. Same for
        # stdin, which carries the client's requests.
        # Truncated per build: only the latest run's output is useful for
        # diagnosing a failure, and appending forever was never rotated.
        log_path = DB_PATH.parent / "supercias_build.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "wb") as log_file:
            _build_process = _spawn_build(log_file)
        _build_started_at = time.time()
        logger.info(
            "Construyendo/refrescando la base financiera de Supercías en "
            "segundo plano (PID %d): %s -- log en %s",
            _build_process.pid, _BUILD_MODULE, log_path,
        )


def _db_schema_version(path: Path) -> int | None:
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            return conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return None


def _unavailable_suffix() -> str:
    state = read_build_state()
    if state.get("ultimo_error") and _in_backoff(state):
        return (
            f" El último intento de construcción falló "
            f"({state.get('ultimo_intento')}): {state['ultimo_error']}. "
            "Se reintentará automáticamente más tarde."
        )
    return (
        " Se está construyendo automáticamente en segundo plano -- vuelve a "
        "intentar en unos minutos."
    )


def _check_db_fresh(path: Path | None = None) -> bool:
    """Raise if the DB can't be served at all; return True if it is stale.

    A stale DB is still served (and a refresh started): it remains the latest
    valid build, and refusing it would make a Supercías outage an outage of
    these tools too. The same goes for a build one schema version behind.
    """
    # Read the module attribute at call time, not as a bound default -- a
    # default evaluated at def-time would freeze the original DB_PATH value,
    # which breaks tests (and anything else) that monkeypatch DB_PATH.
    if path is None:
        path = DB_PATH
    if not path.exists():
        _trigger_background_build()
        raise FinancialsDbUnavailable(
            "La base de datos financiera de Supercías no existe todavía "
            "(descarga ~356 MB, 15-20 minutos la primera vez)."
            + _unavailable_suffix()
        )
    version = _db_schema_version(path)
    if version is None or version < _MIN_SERVED_SCHEMA_VERSION:
        _trigger_background_build()
        raise FinancialsDbUnavailable(
            f"La base de datos financiera de Supercías fue construida con una "
            f"versión anterior del esquema ({version}, se requiere "
            f"{SCHEMA_VERSION})." + _unavailable_suffix()
        )
    stale = (
        version < SCHEMA_VERSION
        or time.time() - path.stat().st_mtime > _MAX_DB_AGE_SECONDS
    )
    if stale:
        _trigger_background_build()
    return stale


def _available_years(conn: sqlite3.Connection) -> list[int]:
    return [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT anio FROM ranking WHERE anio IS NOT NULL ORDER BY anio"
        )
    ]


def format_years(years: list[int]) -> str:
    """Collapse [2008, 2009, ..., 2025] into "2008-2025" (gaps as commas)."""
    if not years:
        return "ninguno"
    spans: list[list[int]] = []
    for year in years:
        if spans and year == spans[-1][1] + 1:
            spans[-1][1] = year
        else:
            spans.append([year, year])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in spans)


def _year_not_loaded(anio: int, years: list[int]) -> YearNotLoaded:
    message = (
        f"El año fiscal {anio} no está en la base local de Supercías. "
        f"Años disponibles: {format_years(years)}."
    )
    # Before the full-history build replaces a version-2 DB, only the last
    # five years are there; say the rest is coming instead of implying the
    # year doesn't exist.
    version = _db_schema_version(DB_PATH)
    if version is not None and version < _FULL_HISTORY_SCHEMA_VERSION:
        message += (
            " La base se está reconstruyendo con el histórico completo "
            "(desde 2008) -- vuelve a intentar en unos minutos."
        )
    return YearNotLoaded(message)


def _year_has_data(conn: sqlite3.Connection, anio: int, column: str) -> bool:
    # `column` always comes from _RANKING_COLUMNS, never straight from a user.
    row = conn.execute(
        f"SELECT 1 FROM ranking WHERE anio = ? AND {column} IS NOT NULL LIMIT 1",
        (anio,),
    ).fetchone()
    return row is not None


def financials_status(path: Path | None = None) -> dict[str, Any]:
    """Build/freshness status of the local DB, for /health and tool metadata."""
    if path is None:
        path = DB_PATH
    state = read_build_state()
    with _build_lock:
        in_progress = _build_in_progress()
    status: dict[str, Any] = {
        "disponible": False,
        "construida_en": None,
        "antiguedad_dias": None,
        "desactualizada": None,
        "anios": None,
        "anios_disponibles": None,
        "actualizacion_pendiente": False,
        "construccion_en_curso": in_progress or _lock_is_held(),
        "ultimo_intento": state.get("ultimo_intento"),
        "ultimo_error": state.get("ultimo_error"),
    }
    if not path.exists():
        return status
    version = _db_schema_version(path)
    if version is None or version < _MIN_SERVED_SCHEMA_VERSION:
        return status
    mtime = path.stat().st_mtime
    age = time.time() - mtime
    upgrade_pending = version < SCHEMA_VERSION
    status.update(
        disponible=True,
        construida_en=datetime.fromtimestamp(mtime, UTC).isoformat(),
        antiguedad_dias=round(age / 86400, 1),
        desactualizada=upgrade_pending or age > _MAX_DB_AGE_SECONDS,
        actualizacion_pendiente=upgrade_pending,
    )
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            years = _available_years(conn)
        finally:
            conn.close()
        if years:
            status["anios"] = [years[0], years[-1]]
            status["anios_disponibles"] = years
    except sqlite3.DatabaseError:
        pass
    return status


def with_financials_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach provenance plus the local build's status under ``metadatos``."""
    status = financials_status()
    result = with_response_metadata(
        payload,
        source="Superintendencia de Compañías — Ranking de Compañías",
        source_url="https://appscvsmovil.supercias.gob.ec/ranking/reporte.html",
        freshness="daily_bulk",
        schema_name="supercias.ranking",
        schema_fields=["anio", "expediente", "posicion_general", "ingresos_ventas"],
        published_at=status["construida_en"],
    )
    result["metadatos"]["base_local"] = status
    return result


def stale_warning_lines(data: dict[str, Any]) -> list[str]:
    status = (data.get("metadatos") or {}).get("base_local") or {}
    if status.get("actualizacion_pendiente"):
        return [
            (
                "Aviso: la base local (años "
                f"{format_years(status.get('anios_disponibles') or [])}) es de una "
                "versión anterior y se está reconstruyendo: la nueva trae el "
                "histórico completo (desde 2008), deja vacíos los ratios que "
                "Supercías no pudo calcular (hoy figuran como 0) y añade los "
                "cuartiles por sector."
            )
        ]
    if not status.get("desactualizada"):
        return []
    return [
        (
            f"Aviso: base local de {status.get('antiguedad_dias')} días "
            f"(construida {status.get('construida_en')}); se está refrescando."
        )
    ]


def ensure_financials_db_fresh() -> None:
    """Kick off a background build/refresh at server startup if needed.

    Called once from main() so an operator never has to run
    scripts/build_supercias_financials_db.py by hand before first use --
    reuses the same missing/stale check _connect() runs per query, and
    swallows FinancialsDbUnavailable since at startup there's no request to
    fail; _trigger_background_build already logged that the build started.
    """
    try:
        _check_db_fresh()
    except FinancialsDbUnavailable:
        pass


def _connect(path: Path | None = None) -> sqlite3.Connection:
    if path is None:
        path = DB_PATH
    _check_db_fresh(path)
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve_expediente(value: str) -> int | None:
    """expediente is a small integer; a 13-digit numeric string is a RUC instead."""
    value = (value or "").strip()
    if not value:
        return None
    if value.isdigit() and len(value) != 13:
        return int(value)
    return None


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _lookup_compania(
    conn: sqlite3.Connection, expediente: int
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT expediente, ruc, nombre FROM companias WHERE expediente = ?",
        (expediente,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def _companias_by_ruc(conn: sqlite3.Connection, ruc: str) -> list[dict[str, Any]]:
    # ~156 RUCs map to more than one expediente in bi_compania.csv, so a RUC
    # lookup can be ambiguous and must not silently pick one of them.
    cur = conn.execute(
        "SELECT expediente, nombre FROM companias WHERE ruc = ? ORDER BY expediente",
        (ruc,),
    )
    return [_row_to_dict(r) for r in cur.fetchall()]


def _query_get_financials(
    expediente_or_ruc: str,
    anio: int | None,
    desde: int | None = None,
    hasta: int | None = None,
) -> dict[str, Any]:
    if anio is not None and (desde is not None or hasta is not None):
        raise ValueError("Usa anio para un solo año, o desde/hasta para un rango; no ambos.")
    if desde is not None and hasta is not None and desde > hasta:
        raise ValueError(f"desde ({desde}) es posterior a hasta ({hasta}).")

    conn = _connect()
    try:
        years_loaded = _available_years(conn)
        if anio is not None and anio not in years_loaded:
            raise _year_not_loaded(anio, years_loaded)
        if anio is not None:
            desde = hasta = anio
        in_range = [
            y
            for y in years_loaded
            if (desde is None or y >= desde) and (hasta is None or y <= hasta)
        ]
        if not in_range:
            raise YearNotLoaded(
                f"Ningún año del rango pedido (desde={desde}, hasta={hasta}) está "
                f"en la base local de Supercías. Años disponibles: "
                f"{format_years(years_loaded)}."
            )

        expediente = _resolve_expediente(expediente_or_ruc)
        if expediente is None:
            ruc = (expediente_or_ruc or "").strip()
            matches = _companias_by_ruc(conn, ruc)
            if not matches:
                return {
                    "error": "not_found",
                    "expediente_or_ruc": expediente_or_ruc,
                    "years": [],
                }
            if len(matches) > 1:
                return {
                    "error": "ambiguous",
                    "expediente_or_ruc": expediente_or_ruc,
                    "candidatos": matches,
                    "years": [],
                }
            expediente = matches[0]["expediente"]

        # Best-effort name/RUC lookup for display; not fatal if it's missing
        # since a company can appear in `ranking` (from bi_ranking.csv) even
        # if it's absent from `companias` (from bi_compania.csv) -- the two
        # source files aren't guaranteed to be in perfect lockstep.
        compania = _lookup_compania(conn, expediente)

        cur = conn.execute(
            "SELECT * FROM ranking WHERE expediente = ? AND anio BETWEEN ? AND ? "
            "ORDER BY anio DESC",
            (expediente, in_range[0], in_range[-1]),
        )
        years = [_row_to_dict(r) for r in cur.fetchall()]
        # Quartiles of the company's own sector that year, so a ratio can be
        # read against peers rather than against Supercías' skewed means.
        if _has_quartiles(conn):
            for year in years:
                if year.get("ciiu_n1"):
                    quartiles = _sector_quartiles(
                        conn, year["anio"], year["ciiu_n1"], COMPARISON_COLUMNS
                    )
                    if quartiles:
                        year["cuartiles_sector"] = quartiles

        return {
            "expediente": expediente,
            "nombre": compania.get("nombre") if compania else None,
            "ruc": compania.get("ruc") if compania else None,
            "years": years,
        }
    finally:
        conn.close()


def _query_search_ranking(
    anio: int | None,
    ciiu_n1: str,
    order_by: str,
    descending: bool,
    limit: int,
    offset: int,
) -> tuple[
    int | None, int, list[dict[str, Any]], list[str], dict[str, Any] | None
]:
    if order_by not in _ORDERABLE_COLUMNS:
        disponibles = ", ".join(sorted(_ORDERABLE_COLUMNS))
        raise ValueError(f"order_by inválido '{order_by}'. Disponibles: {disponibles}")

    conn = _connect()
    try:
        # Without a year, rankings from different years interleave (one
        # "posición 1" per year), so default to the latest year in the DB.
        years_loaded = _available_years(conn)
        if anio is None:
            anio = years_loaded[-1] if years_loaded else None
        elif anio not in years_loaded:
            raise _year_not_loaded(anio, years_loaded)

        # Older years lack whole groups of columns (ratios before 2018, CIIU
        # in 2008). Sorting or filtering on an all-NULL column would return an
        # arbitrary order or nothing, so say why instead.
        if anio is not None and not _year_has_data(conn, anio, order_by):
            raise ValueError(
                f"order_by='{order_by}' no tiene datos para {anio}: Supercías "
                "publica los ratios financieros desde 2018. Para años "
                "anteriores ordena por posicion_general, ingresos_ventas, "
                "activos, patrimonio, utilidad_an_imp o n_empleados."
            )
        if anio is not None and ciiu_n1 and not _year_has_data(conn, anio, "ciiu_n1"):
            raise ValueError(
                f"ciiu_n1 no está disponible para {anio}: Supercías publica la "
                "actividad económica (CIIU) desde 2009."
            )

        clauses: list[str] = []
        params: list[Any] = []
        if anio is not None:
            clauses.append("r.anio = ?")
            params.append(anio)
        if ciiu_n1:
            clauses.append("r.ciiu_n1 = ?")
            params.append(ciiu_n1.strip().upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        total = conn.execute(
            f"SELECT COUNT(*) FROM ranking r {where}", params
        ).fetchone()[0]

        direction = "DESC" if descending else "ASC"
        # LEFT JOIN, not INNER: a ranking row missing from companias should
        # still come back (with ruc/nombre as None) rather than silently
        # vanish from results. NULLs sort last either way: SQLite puts them
        # first in ASC, and 2008-2018 have thousands of unranked rows (no
        # financial statement that year) with a NULL posicion_general.
        cur = conn.execute(
            f"""
            SELECT r.*, c.ruc AS ruc, c.nombre AS nombre
            FROM ranking r
            LEFT JOIN companias c ON c.expediente = r.expediente
            {where}
            ORDER BY r.{order_by} IS NULL, r.{order_by} {direction}
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        rows = [_row_to_dict(r) for r in cur.fetchall()]

        notas: list[str] = []
        if anio is not None and not _year_has_data(conn, anio, "roe"):
            notas.append(
                f"Para {anio} Supercías no publica ratios financieros (empiezan "
                "en 2018): solo ingresos, activos, patrimonio, utilidad, "
                "impuesto a la renta y empleados."
            )
        if order_by in UNRELIABLE_RATIOS:
            notas.append(UNRELIABLE_RATIOS_NOTE)
        cuartiles = None
        if anio is not None and ciiu_n1 and _has_quartiles(conn):
            cuartiles = _sector_quartiles(conn, anio, ciiu_n1.strip().upper()) or None
        return anio, total, rows, notas, cuartiles
    finally:
        conn.close()


def _has_quartiles(conn: sqlite3.Connection) -> bool:
    # Builds before schema 4 (still served while rebuilding) don't have it.
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cuartiles_sector'"
    ).fetchone()
    return row is not None


def _sector_quartiles(
    conn: sqlite3.Connection,
    anio: int,
    ciiu_n1: str,
    columns: tuple[str, ...] = RATIO_COLUMNS,
) -> dict[str, dict[str, Any]]:
    """{indicador: {n, p25, mediana, p75}} for one fiscal year and sector."""
    placeholders = ", ".join("?" for _ in columns)
    cur = conn.execute(
        "SELECT indicador, n, p25, mediana, p75 FROM cuartiles_sector "
        f"WHERE anio = ? AND ciiu_n1 = ? AND indicador IN ({placeholders})",
        (anio, ciiu_n1, *columns),
    )
    found = {
        row["indicador"]: {
            "n": row["n"],
            "p25": row["p25"],
            "mediana": row["mediana"],
            "p75": row["p75"],
        }
        for row in cur.fetchall()
    }
    return {col: found[col] for col in columns if col in found}


def _query_sector_benchmark(anio: int, ciiu_n1: str) -> dict[str, Any] | None:
    sector = ciiu_n1.strip().upper()
    conn = _connect()
    try:
        if not _has_quartiles(conn):
            return None
        indicadores = _sector_quartiles(conn, anio, sector)
        if not indicadores:
            return None
        row = conn.execute(
            "SELECT descripcion FROM ciiu WHERE ciiu = ?", (sector,)
        ).fetchone()
        return {
            "anio": anio,
            "ciiu_n1": sector,
            "descripcion": row["descripcion"] if row else None,
            "indicadores": indicadores,
            "nota": UNRELIABLE_RATIOS_NOTE,
        }
    finally:
        conn.close()


async def get_financials(
    expediente_or_ruc: str,
    anio: int | None = None,
    desde: int | None = None,
    hasta: int | None = None,
) -> dict[str, Any]:
    """
    Financial history for a company, most recent fiscal year first.

    Args:
        expediente_or_ruc: Either the company's Supercías "expediente" number
            or its 13-digit RUC (resolved to expediente via this DB's own
            `companias` table).
        anio: Optional single fiscal year filter; raises YearNotLoaded
            (listing the loaded years) if that year isn't in the DB.
        desde: Optional first fiscal year of a range (inclusive).
        hasta: Optional last fiscal year of a range (inclusive).
    """
    return await asyncio.to_thread(
        _query_get_financials, expediente_or_ruc, anio, desde, hasta
    )


async def search_ranking(
    anio: int | None = None,
    ciiu_n1: str = "",
    order_by: str = "posicion_general",
    descending: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Filter/rank companies within one fiscal year of the local DB.

    Args:
        anio: Fiscal year filter; defaults to the latest year in the DB.
            Raises YearNotLoaded (listing the loaded years) if not there.
        ciiu_n1: Optional CIIU level-1 economic activity filter (single letter).
        order_by: Column to sort by (any ranking column). Raises if unknown.
        descending: Sort highest-first (e.g. top revenue/profit) instead of
            ascending. posicion_general is already rank-ordered ascending
            (1 = best), so leave this False when sorting by it.
        limit: Max results.
        offset: Pagination offset.
    """
    anio, total, rows, notas, cuartiles = await asyncio.to_thread(
        _query_search_ranking, anio, ciiu_n1, order_by, descending, limit, offset
    )
    result: dict[str, Any] = {
        "anio": anio,
        "total": total,
        "offset": offset,
        "companias": rows,
    }
    if cuartiles:
        result["cuartiles_sector"] = cuartiles
    if notas:
        result["notas"] = notas
    return result


async def get_sector_benchmark(anio: int, ciiu_n1: str) -> dict[str, Any] | None:
    """Sector quartiles (p25/median/p75) of every ratio, for one year + CIIU level-1.

    None when the sector/year has no quartiles, or the DB predates them.
    """
    return await asyncio.to_thread(_query_sector_benchmark, anio, ciiu_n1)
