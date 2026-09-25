"""Query layer over the Supercías financial-ranking dataset (bi_ranking.csv).

Distinct from helpers/supercias_client.py's company directory: this is the
"Ranking" dataset (https://appscvsmovil.supercias.gob.ec/ranking/reporte.html),
derived from real balance-sheet filings — revenue, assets, equity, profit,
and ~38 financial ratios per company per fiscal year. The directory only has
"capital suscrito"; this has actual financial performance.

The source CSV (bi_ranking.csv) is ~356 MB / ~1.7M rows covering 2008-present,
too large to hold in memory the way supercias_client.py holds the (also
large, but 10x smaller) company directory. Instead this module only ever
*queries* a local SQLite database that `scripts/build_supercias_financials_db.py`
builds ahead of time, pruned to the last 5 fiscal years during that build.

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
at the same time.

Company names/RUCs are resolved from this same SQLite DB's own `companias`
table (loaded from bi_compania.csv by the build script), not by calling into
helpers.supercias_client's separately-cached directory. An earlier version
did the latter and had a real bug for it: get_financials(expediente) needed
a name/RUC lookup, that module's search only matched name/RUC text (not
expediente), so the lookup silently failed almost every time. Duplicating
three small columns (expediente, ruc, nombre) for ~226k rows is cheap next
to the ~180 MB this DB already is, and removes that cross-module dependency
entirely -- this module's queries never await anything from
helpers.supercias_client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from helpers.response_contract import with_response_metadata

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "supercias_financials.sqlite3"
_BUILD_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "build_supercias_financials_db.py"
)
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
# instead of serving the old data until they age out. 2 = n_empleados fix.
SCHEMA_VERSION = 2

# Guards the in-process launcher only. Cross-process exclusion (two servers,
# the maintenance container, a manual run) is the build script's lock file.
_build_lock = threading.Lock()
_build_process: subprocess.Popen | None = None
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

# Qualified with the "r." alias used in search_ranking's JOIN query, so an
# unqualified user-supplied order_by can't collide with a companias column.
_ORDERABLE_COLUMNS = frozenset(_RANKING_COLUMNS)


class FinancialsDbUnavailable(Exception):
    """Raised when the SQLite build is missing or has an outdated schema."""


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


def _lock_is_held() -> bool:
    """True while any process holds a build lock younger than the timeout."""
    try:
        age = time.time() - lock_path().stat().st_mtime
    except OSError:
        return False
    return age < BUILD_TIMEOUT_SECONDS


def _in_backoff(state: dict[str, Any]) -> bool:
    failures = int(state.get("fallos_consecutivos") or 0)
    last_attempt = state.get("ultimo_intento_ts")
    if failures <= 0 or last_attempt is None:
        return False
    wait = _RETRY_BACKOFF_SECONDS[min(failures, len(_RETRY_BACKOFF_SECONDS)) - 1]
    return time.time() - float(last_attempt) < wait


def _build_in_progress() -> bool:
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
        _build_process.kill()
        _build_process = None
        return False
    return True


def _trigger_background_build() -> None:
    """Start scripts/build_supercias_financials_db.py in the background.

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
        log_path = DB_PATH.parent / "supercias_build.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "ab") as log_file:
            _build_process = subprocess.Popen(
                [sys.executable, str(_BUILD_SCRIPT_PATH)],
                cwd=_BUILD_SCRIPT_PATH.parents[1],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        _build_started_at = time.time()
        logger.info(
            "Construyendo/refrescando la base financiera de Supercías en "
            "segundo plano (PID %d): %s -- log en %s",
            _build_process.pid, _BUILD_SCRIPT_PATH, log_path,
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
    these tools too.
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
    if version != SCHEMA_VERSION:
        _trigger_background_build()
        raise FinancialsDbUnavailable(
            f"La base de datos financiera de Supercías fue construida con una "
            f"versión anterior del esquema ({version}, se requiere "
            f"{SCHEMA_VERSION})." + _unavailable_suffix()
        )
    stale = time.time() - path.stat().st_mtime > _MAX_DB_AGE_SECONDS
    if stale:
        _trigger_background_build()
    return stale


def financials_status(path: Path | None = None) -> dict[str, Any]:
    """Build/freshness status of the local DB, for /health and tool metadata."""
    if path is None:
        path = DB_PATH
    state = read_build_state()
    status: dict[str, Any] = {
        "disponible": False,
        "construida_en": None,
        "antiguedad_dias": None,
        "desactualizada": None,
        "anios": None,
        "construccion_en_curso": _build_in_progress() or _lock_is_held(),
        "ultimo_intento": state.get("ultimo_intento"),
        "ultimo_error": state.get("ultimo_error"),
    }
    if not path.exists() or _db_schema_version(path) != SCHEMA_VERSION:
        return status
    mtime = path.stat().st_mtime
    age = time.time() - mtime
    status.update(
        disponible=True,
        construida_en=datetime.fromtimestamp(mtime, UTC).isoformat(),
        antiguedad_dias=round(age / 86400, 1),
        desactualizada=age > _MAX_DB_AGE_SECONDS,
    )
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            status["anios"] = list(
                conn.execute("SELECT MIN(anio), MAX(anio) FROM ranking").fetchone()
            )
        finally:
            conn.close()
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
    expediente_or_ruc: str, anio: int | None
) -> dict[str, Any]:
    conn = _connect()
    try:
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

        if anio is not None:
            cur = conn.execute(
                "SELECT * FROM ranking WHERE expediente = ? AND anio = ? "
                "ORDER BY anio DESC",
                (expediente, anio),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM ranking WHERE expediente = ? ORDER BY anio DESC",
                (expediente,),
            )
        years = [_row_to_dict(r) for r in cur.fetchall()]

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
) -> tuple[int | None, int, list[dict[str, Any]]]:
    if order_by not in _ORDERABLE_COLUMNS:
        disponibles = ", ".join(sorted(_ORDERABLE_COLUMNS))
        raise ValueError(f"order_by inválido '{order_by}'. Disponibles: {disponibles}")

    conn = _connect()
    try:
        # Without a year, rankings from different years interleave (one
        # "posición 1" per year), so default to the latest year in the DB.
        if anio is None:
            anio = conn.execute("SELECT MAX(anio) FROM ranking").fetchone()[0]
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
        # vanish from results.
        cur = conn.execute(
            f"""
            SELECT r.*, c.ruc AS ruc, c.nombre AS nombre
            FROM ranking r
            LEFT JOIN companias c ON c.expediente = r.expediente
            {where}
            ORDER BY r.{order_by} {direction}
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        return anio, total, [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _query_sector_benchmark(anio: int, ciiu_n1: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT * FROM indicadores_sector WHERE anio = ? AND ciiu_n1 = ?",
            (anio, ciiu_n1.strip().upper()),
        )
        row = cur.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


async def get_financials(
    expediente_or_ruc: str, anio: int | None = None
) -> dict[str, Any]:
    """
    Financial history for a company, most recent fiscal year first.

    Args:
        expediente_or_ruc: Either the company's Supercías "expediente" number
            or its 13-digit RUC (resolved to expediente via this DB's own
            `companias` table).
        anio: Optional single fiscal year filter.
    """
    return await asyncio.to_thread(_query_get_financials, expediente_or_ruc, anio)


async def search_ranking(
    anio: int | None = None,
    ciiu_n1: str = "",
    order_by: str = "posicion_general",
    descending: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Filter/rank companies within the cached fiscal years.

    Args:
        anio: Fiscal year filter; defaults to the latest year in the DB.
        ciiu_n1: Optional CIIU level-1 economic activity filter (single letter).
        order_by: Column to sort by (any ranking column). Raises if unknown.
        descending: Sort highest-first (e.g. top revenue/profit) instead of
            ascending. posicion_general is already rank-ordered ascending
            (1 = best), so leave this False when sorting by it.
        limit: Max results.
        offset: Pagination offset.
    """
    anio, total, rows = await asyncio.to_thread(
        _query_search_ranking, anio, ciiu_n1, order_by, descending, limit, offset
    )
    return {"anio": anio, "total": total, "offset": offset, "companias": rows}


async def get_sector_benchmark(anio: int, ciiu_n1: str) -> dict[str, Any] | None:
    """Sector-level average of the same ratios, for one fiscal year + CIIU level-1."""
    return await asyncio.to_thread(_query_sector_benchmark, anio, ciiu_n1)
