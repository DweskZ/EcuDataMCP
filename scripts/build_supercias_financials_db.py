"""Build/refresh data/supercias_financials.sqlite3 from the Supercías ranking export.

Downloads bi_ranking.csv (~356 MB, ~9M rows, 2008-present) plus the small
lookup tables (bi_compania.csv, bi_segmento.csv, bi_ciiu.csv,
indicadores_sector.csv) from
https://appscvsmovil.supercias.gob.ec/ranking/reporte.html, loads them into a
local SQLite database, then prunes `ranking`/`indicadores_sector` down to the
last 5 fiscal years present in the data (not a hardcoded year, so this
self-adjusts every year without a code change).

Not run automatically by the MCP server: this takes several minutes (the
356 MB download dominates), too slow for a single request/response cycle.
Run it manually before deploying, or on a periodic schedule (the underlying
filings change far less often than the daily company directory) --
helpers/supercias_financials.py refuses to serve data older than 7 days.

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
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from helpers.tls import legacy_cipher_context
from helpers.user_agent import USER_AGENT

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "supercias_financials.sqlite3"
_RESOURCES_BASE = "https://appscvsmovil.supercias.gob.ec/ranking/recursos/"
_TIMEOUT = 300.0
_YEARS_TO_KEEP = 5
_BATCH_SIZE = 5000

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


def _download_to(client: httpx.Client, name: str, dest: Path) -> None:
    url = _RESOURCES_BASE + name
    print(f"Descargando {name}...", flush=True)
    t0 = time.time()
    total = 0
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
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


def _convert(value: str, sql_type: str) -> object:
    value = value.strip()
    if not value:
        return None
    if sql_type == "TEXT":
        return value
    try:
        return int(value) if sql_type == "INTEGER" else float(value)
    except ValueError:
        return None


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

        cols_sql = ", ".join(f'"{h}" {t}' for h, t in zip(header, types, strict=True))
        conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.execute(f'CREATE TABLE "{table}" ({cols_sql})')
        placeholders = ", ".join("?" for _ in header)
        insert_sql = f'INSERT INTO "{table}" VALUES ({placeholders})'

        batch: list[tuple] = []
        n = 0
        for row in reader:
            if len(row) != len(header):
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
        print(f"  {table}: {n} filas cargadas", flush=True)
    return header


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
            ("ranking", {"anio", "expediente", "posicion_general"}),
            ("companias", {"expediente", "ruc", "nombre"}),
            ("segmentos", {"id_segmento", "segmento"}),
            ("ciiu", {"ciiu", "descripcion"}),
            ("indicadores_sector", {"anio", "ciiu_n1"}),
        ):
            cols = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
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


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = DB_PATH.parent / "tmp_supercias_financials"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    # Built alongside the live DB (not under tmp_dir, which gets removed
    # below) so the final os.replace() is a same-filesystem rename, never a
    # cross-filesystem copy that could itself fail partway through.
    build_path = DB_PATH.parent / f"{DB_PATH.name}.building"

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
            _download_to(client, name, dest)

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


if __name__ == "__main__":
    main()
