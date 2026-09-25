"""Build/refresh data/supercias_financials.sqlite3 from the Supercías ranking export.

Downloads bi_ranking.csv (~356 MB, ~1.7M rows, 2008-present) plus the small
lookup tables (bi_compania.csv, bi_segmento.csv, bi_ciiu.csv,
indicadores_sector.csv) from
https://appscvsmovil.supercias.gob.ec/ranking/reporte.html, loads them into a
local SQLite database, then prunes `ranking`/`indicadores_sector` down to the
last 5 fiscal years present in the data (not a hardcoded year, so this
self-adjusts every year without a code change).

Launched automatically as a background subprocess by
helpers/supercias_financials.py (`_trigger_background_build`), both at
server startup and whenever a query hits a missing/stale DB -- an operator
never needs to run this by hand, though it is safe to run directly for a
manual/CI refresh. A lock file next to the DB (`supercias_build.lock`)
makes a second concurrent build -- from another server, the maintenance
container or a manual run -- exit immediately instead of racing this one;
a lock older than BUILD_TIMEOUT_SECONDS is treated as abandoned. Every run
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
~226k rows is cheap (a few MB) next to the ~180 MB this DB already is, and
makes this module fully self-contained.

Usage:
    uv run python scripts/build_supercias_financials_db.py
"""

from __future__ import annotations

import csv
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpers import supercias_financials
from helpers.csv_reader import _EU_DECIMAL_RE, _convert_eu_decimal
from helpers.supercias_financials import BUILD_TIMEOUT_SECONDS, SCHEMA_VERSION
from helpers.tls import legacy_cipher_context
from helpers.user_agent import USER_AGENT

DB_PATH = supercias_financials.DB_PATH
_RESOURCES_BASE = "https://appscvsmovil.supercias.gob.ec/ranking/recursos/"
_TIMEOUT = 300.0
_YEARS_TO_KEEP = 5
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

_SECTOR_INT_COLUMNS = {"anio"}
_SECTOR_TEXT_COLUMNS = {"ciiu_n1", "descripcion"}

_COMPANIA_INT_COLUMNS = {"expediente"}
_COMPANIA_TEXT_COLUMNS = {"ruc", "nombre", "tipo", "pro_codigo", "provincia"}


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        verify=legacy_cipher_context(),
        timeout=_TIMEOUT,
        follow_redirects=True,
    )


def _download_to(
    client: httpx.Client, name: str, dest: Path, deadline: float
) -> None:
    url = _RESOURCES_BASE + name
    print(f"Descargando {name}...", flush=True)
    t0 = time.time()
    total = 0
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                if time.time() > deadline:
                    raise TimeoutError(
                        f"Descarga de {name} excedió el plazo total "
                        f"({_DOWNLOAD_DEADLINE_SECONDS // 60} min)"
                    )
                f.write(chunk)
                total += len(chunk)
                if total % (20 * 1024 * 1024) < len(chunk):
                    print(f"  {total / (1024 * 1024):.0f} MB...", flush=True)
    print(f"  {name}: {total / (1024 * 1024):.1f} MB en {time.time() - t0:.0f}s", flush=True)


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


def _check_not_shrunk(new_path: Path, previous_path: Path) -> None:
    """Reject a build whose ranking table shrank sharply vs. the live DB."""
    if not previous_path.exists():
        return
    try:
        conn = sqlite3.connect(f"file:{previous_path.as_posix()}?mode=ro", uri=True)
        try:
            previous_rows = conn.execute("SELECT COUNT(*) FROM ranking").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return  # unreadable previous DB -- nothing meaningful to compare against
    conn = sqlite3.connect(f"file:{new_path.as_posix()}?mode=ro", uri=True)
    try:
        new_rows = conn.execute("SELECT COUNT(*) FROM ranking").fetchone()[0]
    finally:
        conn.close()
    if new_rows < previous_rows * _MIN_ROWS_VS_PREVIOUS:
        raise RuntimeError(
            f"'ranking' bajó de {previous_rows} a {new_rows} filas frente a la "
            "base anterior -- probablemente la fuente vino incompleta"
        )


def _acquire_lock() -> bool:
    """Create the cross-process build lock; False if another build holds it."""
    path = supercias_financials.lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if time.time() - path.stat().st_mtime > BUILD_TIMEOUT_SECONDS:
            path.unlink(missing_ok=True)  # abandoned by a crashed/killed build
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
        state["ultimo_error"] = f"{type(error).__name__}: {error}"[:500]
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
            ("indicadores_sector", {"anio", "ciiu_n1"}),
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
        min_anio, max_anio = conn.execute(
            "SELECT MIN(anio), MAX(anio) FROM ranking"
        ).fetchone()
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

    deadline = time.time() + _DOWNLOAD_DEADLINE_SECONDS
    with _client() as client:
        ranking_csv = tmp_dir / "bi_ranking.csv"
        compania_csv = tmp_dir / "bi_compania.csv"
        segmento_csv = tmp_dir / "bi_segmento.csv"
        ciiu_csv = tmp_dir / "bi_ciiu.csv"
        sector_csv = tmp_dir / "indicadores_sector.csv"
        for name, dest in (
            ("bi_ranking.csv", ranking_csv),
            ("bi_compania.csv", compania_csv),
            ("bi_segmento.csv", segmento_csv),
            ("bi_ciiu.csv", ciiu_csv),
            ("indicadores_sector.csv", sector_csv),
        ):
            _download_to(client, name, dest, deadline)

    build_path.unlink(missing_ok=True)
    conn = sqlite3.connect(build_path)
    try:
        print("Cargando bi_ranking.csv a SQLite (tabla 'ranking')...", flush=True)
        _load_csv_table(conn, ranking_csv, "ranking", _RANKING_INT_COLUMNS, _RANKING_TEXT_COLUMNS)

        max_anio = conn.execute("SELECT MAX(anio) FROM ranking").fetchone()[0]
        if max_anio is not None:
            cutoff = max_anio - (_YEARS_TO_KEEP - 1)
            deleted = conn.execute(
                "DELETE FROM ranking WHERE anio < ?", (cutoff,)
            ).rowcount
            conn.commit()
            print(
                f"  Recortado a anio >= {cutoff} "
                f"(mantiene los últimos {_YEARS_TO_KEEP} años); {deleted} filas eliminadas",
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

        print("Cargando indicadores_sector.csv (tabla 'indicadores_sector')...", flush=True)
        _load_csv_table(
            conn, sector_csv, "indicadores_sector", _SECTOR_INT_COLUMNS, _SECTOR_TEXT_COLUMNS
        )
        if max_anio is not None:
            conn.execute(
                "DELETE FROM indicadores_sector WHERE anio < ?", (max_anio - (_YEARS_TO_KEEP - 1),)
            )
            conn.commit()

        print("Creando índices...", flush=True)
        conn.execute("CREATE INDEX idx_ranking_expediente ON ranking(expediente)")
        conn.execute("CREATE INDEX idx_ranking_anio ON ranking(anio)")
        conn.execute("CREATE INDEX idx_ranking_ciiu_anio ON ranking(ciiu_n1, anio)")
        conn.execute(
            "CREATE INDEX idx_sector_anio_ciiu ON indicadores_sector(anio, ciiu_n1)"
        )
        conn.execute("CREATE INDEX idx_companias_expediente ON companias(expediente)")
        conn.execute("CREATE INDEX idx_companias_ruc ON companias(ruc)")
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

    # Atomic on both POSIX and Windows, and same-filesystem (build_path
    # lives next to DB_PATH) so this can't fail partway through the way a
    # plain unlink()-then-write to DB_PATH directly could -- a reader
    # opening DB_PATH mid-build would either see the old file or the new
    # one, never a half-written one, and a failed build never touches the
    # previously-working database at all.
    os.replace(build_path, DB_PATH)

    for f in (ranking_csv, compania_csv, segmento_csv, ciiu_csv, sector_csv):
        f.unlink(missing_ok=True)
    tmp_dir.rmdir()

    print(f"Listo: {DB_PATH} ({DB_PATH.stat().st_size / (1024 * 1024):.1f} MB)")


def main() -> None:
    if not _acquire_lock():
        print("Otro build de Supercías está en curso (lock activo); se omite.", flush=True)
        return
    started = time.time()
    try:
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
