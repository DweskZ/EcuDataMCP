"""Build/refresh the Supercías financials SQLite DB from the ranking export.

Downloads bi_ranking.csv (~356 MB, ~1.7M rows, fiscal years 2008-present)
plus the small lookup tables (bi_compania.csv, bi_segmento.csv, bi_ciiu.csv)
from https://appscvsmovil.supercias.gob.ec/ranking/reporte.html and loads
them into a local SQLite database. Every fiscal year in the export is kept,
so the tools can query the full history (see docs/RESEARCH.md for which
columns each year carries: ratios only from 2018, CIIU from 2009). A host
short on disk can keep only the last N years with
ECUADOR_MCP_SUPERCIAS_YEARS=N.

Ratios Supercías could not calculate arrive as 0 and are stored as NULL
(`_null_uncalculated_ratios`). Sector benchmarks are quartiles computed from
the ranking itself (`cuartiles_sector`); the export's own
indicadores_sector.csv is no longer downloaded, since its plain means are
dominated by a few extreme filings and only cover 2018-2023.

Launched automatically as a background subprocess by
helpers/supercias_financials.py (`_trigger_background_build`), both at
server startup and whenever a query hits a missing/stale DB -- an operator
never needs to run this by hand, though it is safe to run directly for a
manual/CI refresh. A lock file next to the DB (`supercias_build.lock`)
makes a second concurrent build -- from another server, the maintenance
container or a manual run -- exit immediately instead of racing this one;
the lock records this process's PID, and a lock whose PID is no longer
running, or older than BUILD_TIMEOUT_SECONDS, is treated as abandoned. The
server launches this detached from its own session, so closing a stdio
client does not kill a build halfway through. Every run
records its outcome in `supercias_build.state.json`, which the server uses
to back off after failures and to report status. Takes ~15-20 minutes (the
356 MB download dominates); the server starts a refresh once the DB is
older than 7 days but keeps serving the old one meanwhile.

bi_compania.csv (expediente, ruc, nombre, tipo, pro_codigo, provincia) IS
downloaded, as the `companias` table -- an earlier version of this script
skipped it on the theory that helpers/supercias_client.py's directory cache
already has the same fields, joined on `expediente`. That created a real
coupling bug: get_financials()/search_ranking() need a live, separately
warmed, separately-TTL'd cache from a different module just to show a
company's name next to its financials. Duplicating three small columns for
~226k rows is cheap (a few MB) next to the size of this DB, and makes this
module fully self-contained.

Lives in the package (not scripts/) so installs from PyPI or an MCPB bundle,
which don't ship scripts/, can still run it; helpers/supercias_financials.py
launches it as `python -m helpers.supercias_financials_build`.

Usage:
    uv run python -m helpers.supercias_financials_build
    uv run python scripts/build_supercias_financials_db.py   # same, kept for habit
"""

from __future__ import annotations

import contextlib
import csv
import ctypes
import itertools
import os
import shutil
import sqlite3
import statistics
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx

from helpers import supercias_financials
from helpers.csv_reader import _EU_DECIMAL_RE, _convert_eu_decimal
from helpers.geo_proxy import proxy_for, unreachable_hint
from helpers.supercias_financials import BUILD_TIMEOUT_SECONDS, SCHEMA_VERSION
from helpers.tls import legacy_cipher_context
from helpers.user_agent import USER_AGENT

DB_PATH = supercias_financials.DB_PATH
_RESOURCES_BASE = "https://appscvsmovil.supercias.gob.ec/ranking/recursos/"
# Short connect timeout: a network the host drops (Render, 2026-10-07) only
# fails by timing out, and 300 s of that just delays the error.
_TIMEOUT = httpx.Timeout(300.0, connect=15.0)
# Optional retention cap in fiscal years; unset, empty or "all" keeps every
# year Supercías publishes (2008 onwards).
_YEARS_ENV = "ECUADOR_MCP_SUPERCIAS_YEARS"
_BATCH_SIZE = 5000
# A few malformed lines are tolerable; more means a truncated/corrupt file.
_MAX_SKIPPED_SHARE = 0.001
# A new build with far fewer ranking rows than the live one is more likely a
# partial source file than a real drop in filings.
_MIN_ROWS_VS_PREVIOUS = 0.8
# Whole-download deadline: httpx's timeout is per read, so a trickling
# connection could otherwise keep the build (and its lock) alive for hours.
_DOWNLOAD_DEADLINE_SECONDS = BUILD_TIMEOUT_SECONDS - 10 * 60

_RANKING_INT_COLUMNS = {
    "anio", "expediente", "posicion_general", "cia_imvalores",
    "id_estado_financiero", "n_empleados", "cod_segmento",
}
_RANKING_TEXT_COLUMNS = {"ciiu_n1", "ciiu_n6"}

# Supercías writes 0 for a ratio it could not calculate, which makes it
# indistinguishable from a real 0 and drags every mean and comparison toward
# zero (2023: 85% of trade companies "had" a 0 operating margin). A 0 is
# turned into NULL when it cannot be a real value:
# - the whole row has no ratios (no statement, or every ratio is 0);
# - the ratio's denominator in the row is 0 (sales, assets or equity);
# - the ratio has no real zero for an operating company (current ratio,
#   turnover, margins, days): among 2023 filers with sales, assets and equity
#   above 0, margen_operacional was 0 for 80%, per_med_cobranza for 85%.
# Ratios with a real zero (no long-term debt, no financial costs, a profit
# rounding to 0.00) keep it.
_RATIO_DENOMINATORS = {
    "ingresos_ventas": (
        "margen_bruto", "margen_operacional", "rent_neta_ventas",
        "per_med_cobranza", "impac_gasto_a_v", "impac_carga_finan",
        "rent_neta_activo", "rent_ope_activo",
    ),
    "activos": (
        "end_activo", "rot_ventas", "rent_neta_activo", "rent_ope_activo",
        "roa",
    ),
    "patrimonio": (
        "end_patrimonial", "apalancamiento", "end_patrimonial_ct",
        "end_patrimonial_nct", "rent_ope_patrimonio", "roe",
    ),
}
_ZERO_MEANS_MISSING = (
    "liquidez_corriente", "prueba_acida", "end_activo_fijo",
    "cobertura_interes", "apalancamiento", "apalancamiento_financiero",
    "rot_cartera", "rot_activo_fijo", "rot_ventas", "per_med_cobranza",
    "per_med_pago", "margen_bruto", "margen_operacional",
)
# Fewer filings than this in a sector and year give no quartiles: three or
# four companies are not a sector benchmark.
_MIN_SECTOR_FILINGS = 5

_COMPANIA_INT_COLUMNS = {"expediente"}
_COMPANIA_TEXT_COLUMNS = {"ruc", "nombre", "tipo", "pro_codigo", "provincia"}


def _years_to_keep() -> int | None:
    """Last N fiscal years to keep, or None for the full history."""
    value = (os.getenv(_YEARS_ENV) or "").strip().lower()
    if value in ("", "all"):
        return None
    if not value.isdigit() or int(value) < 1:
        raise ValueError(
            f"{_YEARS_ENV}={value!r} no es válido: usa un número de años (ej. 5) o 'all'"
        )
    return int(value)


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        verify=legacy_cipher_context(),
        timeout=_TIMEOUT,
        follow_redirects=True,
        proxy=proxy_for(_RESOURCES_BASE),
    )


# The whole export is ~356 MB today (bi_ranking.csv is most of it); a file
# past this is not the export but a redirect to an error page or a runaway
# response, and must not be allowed to fill the data volume.
_MAX_FILE_BYTES = 1024 * 1024 * 1024
# Room for the CSVs plus the SQLite file built from them, with headroom.
_MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024


def _download_to(
    client: httpx.Client, name: str, dest: Path, deadline: float
) -> None:
    url = _RESOURCES_BASE + name
    print(f"Descargando {name}...", flush=True)
    t0 = time.time()
    total = 0
    attempt = 0
    while True:
        try:
            total = _stream_once(client, name, url, dest, deadline, total)
            break
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # Recorded as the build's ultimo_error, which get_financials shows.
            raise RuntimeError(
                f"No se pudo conectar a {httpx.URL(url).host} "
                f"({type(exc).__name__}). " + unreachable_hint(url)
            ) from exc
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout) as exc:
            # Seen 2026-11-10 on the runner: the server closed bi_ranking.csv
            # at 274 of 374 MB. Resume from the bytes already written rather
            # than failing the whole 15-minute build.
            attempt += 1
            if attempt > _RESUME_ATTEMPTS:
                raise
            total = dest.stat().st_size if dest.exists() else 0
            print(
                f"  {name}: conexión cortada en {total / (1024 * 1024):.0f} MB "
                f"({type(exc).__name__}); reanudando ({attempt}/{_RESUME_ATTEMPTS})",
                flush=True,
            )
    print(f"  {name}: {total / (1024 * 1024):.1f} MB en {time.time() - t0:.0f}s", flush=True)


_RESUME_ATTEMPTS = 3


def _stream_once(
    client: httpx.Client, name: str, url: str, dest: Path, deadline: float, offset: int
) -> int:
    """Stream ``url`` into ``dest`` from byte ``offset``; return bytes written.

    A server that ignores the Range header answers 200 with the whole file,
    so the file is then rewritten from the start instead of appended to.
    """
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with client.stream("GET", url, headers=headers) as resp:
        resp.raise_for_status()
        if offset and resp.status_code != 206:
            offset = 0
        total = offset
        with open(dest, "ab" if offset else "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                if time.time() > deadline:
                    raise TimeoutError(
                        f"Descarga de {name} excedió el plazo total "
                        f"({_DOWNLOAD_DEADLINE_SECONDS // 60} min)"
                    )
                total += len(chunk)
                if total > _MAX_FILE_BYTES:
                    raise RuntimeError(
                        f"Descarga de {name} superó {_MAX_FILE_BYTES // (1024 * 1024)} MB; "
                        "no parece ser la exportación de Supercías"
                    )
                f.write(chunk)
                if total % (20 * 1024 * 1024) < len(chunk):
                    print(f"  {total / (1024 * 1024):.0f} MB...", flush=True)
    return total


def _column_type(name: str, int_cols: set[str], text_cols: set[str]) -> str:
    if name in int_cols:
        return "INTEGER"
    if name in text_cols:
        return "TEXT"
    return "REAL"


def _quote_ident(name: str) -> str:
    """Safely quote a SQL identifier that may come from an external CSV header."""
    return '"' + name.replace('"', '""') + '"'


def _convert(value: str, sql_type: str) -> object:
    value = value.strip()
    if not value:
        return None
    if sql_type == "TEXT":
        return value
    if _EU_DECIMAL_RE.match(value):
        value = _convert_eu_decimal(value)
    if sql_type != "INTEGER":
        try:
            return float(value)
        except ValueError:
            return None
    try:
        return int(value)
    except ValueError:
        # bi_ranking.csv ships n_empleados (an INTEGER column here) as a
        # decimal string ("2.00", "11547.00") like its REAL-typed
        # neighbors -- confirmed live 2026-09-21, this silently nulled out
        # every single n_empleados value (100% of 660k rows) before this
        # fallback existed, since int("2.00") raises ValueError directly.
        # Only whole numbers are accepted: "inf" would raise OverflowError
        # (aborting the whole load) and "2.5" would silently truncate.
        try:
            number = float(value)
        except ValueError:
            return None
        if not number.is_integer():
            return None
        return int(number)


def _load_csv_table(
    conn: sqlite3.Connection,
    csv_path: Path,
    table: str,
    int_cols: set[str],
    text_cols: set[str],
) -> list[str]:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        types = [_column_type(h, int_cols, text_cols) for h in header]

        cols_sql = ", ".join(
            f"{_quote_ident(h)} {t}" for h, t in zip(header, types, strict=True)
        )
        table_ident = _quote_ident(table)
        conn.execute(f"DROP TABLE IF EXISTS {table_ident}")
        conn.execute(f"CREATE TABLE {table_ident} ({cols_sql})")
        placeholders = ", ".join("?" for _ in header)
        insert_sql = f"INSERT INTO {table_ident} VALUES ({placeholders})"

        batch: list[tuple] = []
        n = 0
        skipped = 0
        for row in reader:
            if len(row) != len(header):
                skipped += 1
                continue
            batch.append(tuple(_convert(v, t) for v, t in zip(row, types, strict=True)))
            if len(batch) >= _BATCH_SIZE:
                conn.executemany(insert_sql, batch)
                n += len(batch)
                batch.clear()
        if batch:
            conn.executemany(insert_sql, batch)
            n += len(batch)
        conn.commit()
        print(f"  {table}: {n} filas cargadas, {skipped} omitidas", flush=True)
        if skipped > (n + skipped) * _MAX_SKIPPED_SHARE:
            raise RuntimeError(
                f"{csv_path.name}: {skipped} de {n + skipped} filas con número "
                "de columnas distinto al encabezado -- archivo probablemente "
                "truncado o corrupto"
            )
    return header


def _null_uncalculated_ratios(conn: sqlite3.Connection) -> None:
    """Store ratios Supercías could not calculate as NULL instead of 0.

    One UPDATE with a CASE per ratio, not one UPDATE per rule: each rule as
    its own statement rewrote the table ~17 times (2 minutes for 5 years).
    """
    present = _ranking_columns(conn)
    ratios = [col for col in supercias_financials.RATIO_COLUMNS if col in present]
    if not ratios:
        return
    no_ratios = "(" + " AND ".join(f"{col} = 0" for col in ratios) + ")"
    if "id_estado_financiero" in present:
        no_ratios = f"id_estado_financiero IS NULL OR {no_ratios}"
    assignments = []
    for col in ratios:
        conditions = [no_ratios]
        conditions += [
            f"COALESCE({denominator}, 0) = 0"
            for denominator, columns in _RATIO_DENOMINATORS.items()
            if col in columns and denominator in present
        ]
        if col in _ZERO_MEANS_MISSING:
            conditions.append(f"{col} = 0")
        assignments.append(
            f"{col} = CASE WHEN {' OR '.join(conditions)} THEN NULL ELSE {col} END"
        )
    # Years without ratios (before 2018) have nothing to clear.
    # The trailing NULL keeps COALESCE valid with a single ratio column.
    has_ratio = f"COALESCE({', '.join(ratios)}, NULL) IS NOT NULL"
    conn.execute(f"UPDATE ranking SET {', '.join(assignments)} WHERE {has_ratio}")
    conn.commit()


def _ranking_columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(ranking)")}


def _quartiles(values: list[float]) -> tuple[float, float, float]:
    """p25, median, p75 (linear interpolation between order statistics)."""
    p25, median, p75 = statistics.quantiles(values, n=4, method="inclusive")
    return p25, median, p75


def _build_sector_quartiles(conn: sqlite3.Connection) -> None:
    """Per-sector, per-year quartiles of every ratio, from the ranking itself.

    Replaces indicadores_sector.csv: Supercías' sector figures are plain
    means, which a handful of extreme filings dominate (manufacturing 2023:
    current ratio 23.7 against a median of 1.48, gross margin -1,245 against
    0.41). Runs after _null_uncalculated_ratios, so 0 placeholders don't
    count as filings. A single scan grouped by year and sector; each group
    (at most ~35k filings) is sorted in memory.
    """
    conn.execute("DROP TABLE IF EXISTS cuartiles_sector")
    conn.execute(
        "CREATE TABLE cuartiles_sector (anio INTEGER, ciiu_n1 TEXT, "
        "indicador TEXT, n INTEGER, p25 REAL, mediana REAL, p75 REAL)"
    )
    present = _ranking_columns(conn)
    ratios = [col for col in supercias_financials.RATIO_COLUMNS if col in present]
    rows: list[tuple] = []
    if ratios and "ciiu_n1" in present:
        cur = conn.execute(
            f"SELECT anio, ciiu_n1, {', '.join(ratios)} FROM ranking "
            f"WHERE ciiu_n1 IS NOT NULL AND COALESCE({', '.join(ratios)}, NULL) "
            "IS NOT NULL ORDER BY anio, ciiu_n1"
        )
        for (anio, ciiu_n1), group in itertools.groupby(cur, key=lambda r: r[:2]):
            filings = list(group)
            for i, col in enumerate(ratios, start=2):
                values = sorted(r[i] for r in filings if r[i] is not None)
                if len(values) < _MIN_SECTOR_FILINGS:
                    continue
                rows.append((anio, ciiu_n1, col, len(values), *_quartiles(values)))
    conn.executemany(
        "INSERT INTO cuartiles_sector VALUES (?, ?, ?, ?, ?, ?, ?)", rows
    )
    conn.execute(
        "CREATE INDEX idx_cuartiles_anio_ciiu ON cuartiles_sector(anio, ciiu_n1)"
    )
    conn.commit()
    print(f"  cuartiles_sector: {len(rows)} filas", flush=True)


def _check_not_shrunk(new_path: Path, previous_path: Path) -> None:
    """Reject a build whose ranking table shrank sharply vs. the live DB.

    Only years inside the new build's range are compared, so lowering
    ECUADOR_MCP_SUPERCIAS_YEARS is not mistaken for a truncated source file.
    """
    if not previous_path.exists():
        return
    conn = sqlite3.connect(f"file:{new_path.as_posix()}?mode=ro", uri=True)
    try:
        min_anio, new_rows = conn.execute(
            "SELECT MIN(anio), COUNT(*) FROM ranking"
        ).fetchone()
    finally:
        conn.close()
    try:
        conn = sqlite3.connect(f"file:{previous_path.as_posix()}?mode=ro", uri=True)
        try:
            previous_rows = conn.execute(
                "SELECT COUNT(*) FROM ranking WHERE anio >= ?", (min_anio,)
            ).fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return  # unreadable previous DB -- nothing meaningful to compare against
    if new_rows < previous_rows * _MIN_ROWS_VS_PREVIOUS:
        raise RuntimeError(
            f"'ranking' bajó de {previous_rows} a {new_rows} filas frente a la "
            "base anterior -- probablemente la fuente vino incompleta"
        )


_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


@contextlib.contextmanager
def _keep_awake() -> Iterator[None]:
    """On Windows, ask the system not to sleep from idleness during the build.

    A laptop that sleeps (Modern Standby) freezes the build with everything
    else: one build sat frozen for 17 minutes in its index step and was gone
    when the machine woke. This does not stop a closed lid or the power
    button from suspending it, which no process can prevent.
    """
    if sys.platform != "win32":
        yield
        return
    kernel32 = ctypes.windll.kernel32
    kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
    try:
        yield
    finally:
        kernel32.SetThreadExecutionState(_ES_CONTINUOUS)


def _acquire_lock() -> bool:
    """Create the cross-process build lock; False if another build holds it."""
    path = supercias_financials.lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Abandoned by a crashed/killed build: its PID is gone, or it is older
    # than the timeout. Re-reading the PID right before unlinking keeps a
    # concurrent build that just reclaimed the lock from losing it.
    stale_pid = supercias_financials.read_lock_pid()
    if supercias_financials.lock_is_stale():
        try:
            if supercias_financials.read_lock_pid() == stale_pid:
                path.unlink(missing_ok=True)
                if stale_pid is not None:
                    print(
                        f"El build anterior (PID {stale_pid}) no liberó el lock: "
                        "lo detuvieron desde fuera (cierre de sesión, suspensión "
                        "del equipo) o superó el tiempo máximo. Se reinicia.",
                        flush=True,
                    )
        except OSError:
            pass
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as f:
        f.write(str(os.getpid()))
    return True


def _record_outcome(started: float, error: BaseException | None) -> None:
    state = supercias_financials.read_build_state()
    now = datetime.now(UTC).isoformat()
    state["ultimo_intento"] = now
    state["ultimo_intento_ts"] = started
    if error is None:
        state.update(ultimo_exito=now, ultimo_error=None, fallos_consecutivos=0)
    else:
        # A bare httpx.ConnectTimeout stringifies to "", so fall back to repr.
        detail = str(error) or repr(error)
        state["ultimo_error"] = f"{type(error).__name__}: {detail}"[:500]
        state["fallos_consecutivos"] = int(state.get("fallos_consecutivos") or 0) + 1
    supercias_financials.write_build_state(state)


def _verify_build(db_path: Path) -> None:
    """Sanity-check a freshly built DB before it replaces the live one.

    Cheap checks only (structural integrity, non-empty required tables,
    expected columns) -- not a substitute for the row-level data-quality
    reporting a future pass could add (see ROADMAP), but enough to catch
    "the build silently produced garbage" before it overwrites a working DB.
    """
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise RuntimeError(f"PRAGMA integrity_check falló: {ok}")

        for table, required_cols in (
            ("ranking", {"anio", "expediente", "posicion_general", "n_empleados"}),
            ("companias", {"expediente", "ruc", "nombre"}),
            ("segmentos", {"id_segmento", "segmento"}),
            ("ciiu", {"ciiu", "descripcion"}),
            ("cuartiles_sector", {"anio", "ciiu_n1", "indicador", "mediana"}),
        ):
            cols = {
                row[1] for row in conn.execute(f"PRAGMA table_info({_quote_ident(table)})")
            }
            missing = required_cols - cols
            if missing:
                raise RuntimeError(f"Tabla '{table}' sin columnas {missing}")

        companias_rows = conn.execute("SELECT COUNT(*) FROM companias").fetchone()[0]
        if companias_rows == 0:
            raise RuntimeError(
                "La tabla 'companias' quedó vacía tras el build -- "
                "probablemente bi_compania.csv vino roto/truncado esta vez"
            )

        ranking_rows = conn.execute("SELECT COUNT(*) FROM ranking").fetchone()[0]
        if ranking_rows == 0:
            raise RuntimeError(
                "La tabla 'ranking' quedó vacía tras el build -- "
                "probablemente el CSV fuente vino roto/truncado esta vez"
            )
        # Guards against the int-conversion bug that once nulled out 100% of
        # n_empleados silently coming back.
        n_empleados_rows = conn.execute(
            "SELECT COUNT(n_empleados) FROM ranking"
        ).fetchone()[0]
        if n_empleados_rows == 0:
            raise RuntimeError(
                "La columna 'n_empleados' de 'ranking' quedó completamente vacía "
                "tras el build -- probablemente falló la conversión a entero"
            )
        min_anio, max_anio, n_anios = conn.execute(
            "SELECT MIN(anio), MAX(anio), COUNT(DISTINCT anio) FROM ranking"
        ).fetchone()
        # Supercías publishes every year from 2008 with no gaps; a year
        # missing in the middle means the export came back partial.
        if n_anios != max_anio - min_anio + 1:
            raise RuntimeError(
                f"La tabla 'ranking' tiene {n_anios} años entre {min_anio} y "
                f"{max_anio}: falta al menos un año -- probablemente la fuente "
                "vino incompleta"
            )
        print(
            f"  Verificación OK: {ranking_rows} filas en 'ranking' "
            f"({companias_rows} en 'companias'), años {min_anio}-{max_anio}",
            flush=True,
        )
    finally:
        conn.close()


def _build() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = DB_PATH.parent / "tmp_supercias_financials"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    # Built alongside the live DB (not under tmp_dir, which gets removed
    # below) so the final os.replace() is a same-filesystem rename, never a
    # cross-filesystem copy that could itself fail partway through.
    build_path = DB_PATH.parent / f"{DB_PATH.name}.building"

    free = shutil.disk_usage(DB_PATH.parent).free
    if free < _MIN_FREE_BYTES:
        raise RuntimeError(
            f"Espacio insuficiente en {DB_PATH.parent}: {free // (1024 * 1024)} MB libres, "
            f"se necesitan al menos {_MIN_FREE_BYTES // (1024 * 1024)} MB para el build"
        )

    # Read before downloading, so a typo in the setting fails in seconds.
    years_to_keep = _years_to_keep()

    ranking_csv = tmp_dir / "bi_ranking.csv"
    compania_csv = tmp_dir / "bi_compania.csv"
    segmento_csv = tmp_dir / "bi_segmento.csv"
    ciiu_csv = tmp_dir / "bi_ciiu.csv"
    deadline = time.time() + _DOWNLOAD_DEADLINE_SECONDS
    try:
        with _client() as client:
            for name, dest in (
                ("bi_ranking.csv", ranking_csv),
                ("bi_compania.csv", compania_csv),
                ("bi_segmento.csv", segmento_csv),
                ("bi_ciiu.csv", ciiu_csv),
            ):
                _download_to(client, name, dest, deadline)
    except BaseException:
        # A failed or interrupted download must not leave hundreds of MB of
        # partial CSVs behind on the data volume.
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    build_path.unlink(missing_ok=True)
    conn = sqlite3.connect(build_path)
    try:
        print("Cargando bi_ranking.csv a SQLite (tabla 'ranking')...", flush=True)
        _load_csv_table(conn, ranking_csv, "ranking", _RANKING_INT_COLUMNS, _RANKING_TEXT_COLUMNS)

        max_anio = conn.execute("SELECT MAX(anio) FROM ranking").fetchone()[0]
        cutoff = None
        if max_anio is not None and years_to_keep is not None:
            cutoff = max_anio - (years_to_keep - 1)
            deleted = conn.execute(
                "DELETE FROM ranking WHERE anio < ?", (cutoff,)
            ).rowcount
            conn.commit()
            print(
                f"  Recortado a anio >= {cutoff} ({_YEARS_ENV}={years_to_keep}); "
                f"{deleted} filas eliminadas",
                flush=True,
            )

        print("Cargando bi_compania.csv (tabla 'companias')...", flush=True)
        _load_csv_table(
            conn, compania_csv, "companias", _COMPANIA_INT_COLUMNS, _COMPANIA_TEXT_COLUMNS
        )

        print("Cargando bi_segmento.csv (tabla 'segmentos')...", flush=True)
        _load_csv_table(conn, segmento_csv, "segmentos", {"id_segmento"}, {"segmento"})

        print("Cargando bi_ciiu.csv (tabla 'ciiu')...", flush=True)
        _load_csv_table(conn, ciiu_csv, "ciiu", set(), {"ciiu", "descripcion"})

        print("Ratios no calculados por Supercías (0) -> NULL...", flush=True)
        _null_uncalculated_ratios(conn)

        print("Creando índices...", flush=True)
        conn.execute("CREATE INDEX idx_ranking_expediente ON ranking(expediente)")
        conn.execute("CREATE INDEX idx_ranking_anio ON ranking(anio)")
        conn.execute("CREATE INDEX idx_ranking_ciiu_anio ON ranking(ciiu_n1, anio)")
        conn.execute("CREATE INDEX idx_companias_expediente ON companias(expediente)")
        conn.execute("CREATE INDEX idx_companias_ruc ON companias(ruc)")

        print("Calculando cuartiles por sector (tabla 'cuartiles_sector')...", flush=True)
        _build_sector_quartiles(conn)
        conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
        conn.commit()

        print("VACUUM...", flush=True)
        conn.execute("VACUUM")
    except Exception:
        conn.close()
        build_path.unlink(missing_ok=True)
        raise
    else:
        conn.close()

    print("Verificando la base construida antes de reemplazar la anterior...", flush=True)
    try:
        _verify_build(build_path)
        _check_not_shrunk(build_path, DB_PATH)
    except Exception:
        build_path.unlink(missing_ok=True)
        raise

    # Same-filesystem rename (build_path lives next to DB_PATH), so a reader
    # opening DB_PATH sees either the old file or the new one, never a
    # half-written one, and a failed build never touches the previously
    # working database at all. On POSIX the replace also succeeds while a
    # reader has the old file open; on Windows it raises PermissionError
    # until that reader closes, so retry briefly instead of discarding a
    # 15-20 minute build because a get_financials call overlapped the rename.
    _replace_with_retry(build_path, DB_PATH)

    for f in (ranking_csv, compania_csv, segmento_csv, ciiu_csv):
        f.unlink(missing_ok=True)
    tmp_dir.rmdir()

    print(f"Listo: {DB_PATH} ({DB_PATH.stat().st_size / (1024 * 1024):.1f} MB)")


_REPLACE_ATTEMPTS = 20
_REPLACE_DELAY_SECONDS = 0.5


def _replace_with_retry(src: Path, dst: Path) -> None:
    """os.replace that tolerates a Windows reader holding `dst` open."""
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS:
                raise
            time.sleep(_REPLACE_DELAY_SECONDS)


def main() -> None:
    if not _acquire_lock():
        print("Otro build de Supercías está en curso (lock activo); se omite.", flush=True)
        return
    started = time.time()
    try:
        with _keep_awake():
            _build()
    except BaseException as e:
        _record_outcome(started, e)
        raise
    else:
        _record_outcome(started, None)
    finally:
        supercias_financials.lock_path().unlink(missing_ok=True)


if __name__ == "__main__":
    main()
