from functools import partial

import httpx
from mcp.server.fastmcp import FastMCP

from helpers import ckan_client
from helpers.csv_reader import (
    preview_csv,
    preview_json,
    preview_targz,
    preview_xls,
    preview_xlsx,
    preview_zip,
    sniff_content_type,
)
from helpers.format_out import render_output
from helpers.logging import log_tool
from helpers.text_utils import strip_accents
from tools.list_dataset_resources import detect_periodic_series, period_sort_key
from tools.preview_resource_data import (
    classify_from_content_type,
    classify_resource_format,
)

_ANALYZE_MAX_ROWS = 500

_PERIOD_KEYWORDS = (
    "fecha",
    "date",
    "periodo",
    "ano",
    "anio",
    "year",
    "mes",
    "month",
    "semana",
    "week",
    "trimestre",
    "quarter",
)

# Coverage thresholds for classifying the newer file's period set against the
# older file's: how much of the older file's periods reappear in the newer
# one. High overlap -> the newer file already carries the older one's data
# (cumulative). Near-zero overlap -> the files cover distinct periods
# (incremental, must be combined). Anything in between is genuinely
# ambiguous and left for a human/model to inspect.
_CUMULATIVE_COVERAGE = 0.8
_INCREMENTAL_COVERAGE = 0.2


_strip_accents = partial(strip_accents, lower=False)


def _find_period_columns(headers: list[str]) -> list[int]:
    idxs = []
    for i, header in enumerate(headers):
        normalized = _strip_accents(header).strip().lower()
        if any(kw in normalized for kw in _PERIOD_KEYWORDS):
            idxs.append(i)
    return idxs


_MAX_BANNER_ROWS = 5


def _locate_header_row(
    headers: list[str], rows: list[list[str]]
) -> tuple[list[str], list[list[str]]]:
    """Find the real header row when row 0 doesn't have a period column.

    Confirmed live against IESS's Seguro de Desempleo resources: several
    lead with 1-3 title/banner rows ("Monto pagado y numero de beneficiarios
    2026", blank rows) before the actual column headers. preview_csv/_xlsx
    always treat row 0 as the header, so a period column further down would
    otherwise be invisible to _period_keys. Scans the next few rows for one
    that both looks like a header (2+ non-empty cells) and contains a period
    keyword; if found, that row becomes the header and everything after it
    the data. Falls back to (headers, rows) unchanged if row 0 already
    matches or nothing better turns up within the scan window.
    """
    if _find_period_columns(headers):
        return headers, rows
    for i, candidate in enumerate(rows[:_MAX_BANNER_ROWS]):
        non_empty = sum(1 for c in candidate if c.strip())
        if non_empty >= 2 and _find_period_columns(candidate):
            return candidate, rows[i + 1 :]
    return headers, rows


def _normalize_header_set(headers: list[str]) -> set[str]:
    return {_strip_accents(h).strip().lower() for h in headers if h and h.strip()}


def _schema_mismatch(headers_old: list[str], headers_new: list[str]) -> bool:
    """Whether the two files look like genuinely different report formats.

    Confirmed live against IESS's Seguro de Desempleo dataset: resources
    matching the exact same name template across consecutive months can
    silently switch schema (a monthly cumulative-totals table one month --
    "Mes, Monto pagado, ..." with month names -- a per-province/gender
    detail table the next -- "Mes, Tipo Pago, Provincia, Genero, ..." with
    numeric month codes). Both had a period-like "Mes" column, so period
    overlap alone came back a confident-looking 0% ("incremental") for a
    comparison that was never valid to begin with. Less than half the
    non-empty header names in common is a strong enough signal that this
    isn't the same report shape, regardless of what the period overlap says.
    """
    old_set = _normalize_header_set(headers_old)
    new_set = _normalize_header_set(headers_new)
    if not old_set or not new_set:
        return False
    overlap = old_set & new_set
    return (len(overlap) / min(len(old_set), len(new_set))) < 0.5


def _period_keys(headers: list[str], rows: list[list[str]]) -> tuple[set[str], list[str]] | None:
    """Distinct period values found across the period-like column(s).

    Returns (keys, column_names), or None if no period-like column exists.
    A row with values in more than one matched column (e.g. separate "mes"
    and "ano" columns) gets a composite key so year/month pairs aren't
    confused with each other.
    """
    idxs = _find_period_columns(headers)
    if not idxs:
        return None
    keys: set[str] = set()
    for row in rows:
        parts = [row[i].strip() for i in idxs if i < len(row) and row[i]]
        if parts:
            keys.add("|".join(parts))
    if not keys:
        return None
    return keys, [headers[i] for i in idxs]


async def _fetch_table(res: dict, session: httpx.AsyncClient) -> dict:
    """Download and parse a resource the same way preview_resource_data does.

    Raises ValueError with a message safe to surface to the caller when the
    resource can't be read as a table (unsupported/unknown format, download
    failure, etc).
    """
    url = res.get("url")
    if not url:
        raise ValueError("este recurso no tiene URL de descarga")

    fmt = (res.get("format") or "").upper()
    kind = classify_resource_format(fmt, url)
    if kind == "UNKNOWN":
        content_type = await sniff_content_type(url, session=session)
        kind = classify_from_content_type(content_type)

    if kind == "RAR":
        raise ValueError("es un .rar, no previsualizable como tabla todavía")
    if kind == "UNKNOWN":
        raise ValueError(f"formato no soportado ('{fmt or 'desconocido'}')")

    dispatch = {
        "TARGZ": preview_targz,
        "ZIP": preview_zip,
        "XLS": preview_xls,
        "XLSX": preview_xlsx,
        "JSON": preview_json,
        "CSV": preview_csv,
    }
    return await dispatch[kind](url, max_rows=_ANALYZE_MAX_ROWS, session=session)


def _pick_pair(resources: list[dict]) -> tuple[dict, dict] | None:
    """Pick the two most recent resources from the largest periodic-name group."""
    names = detect_periodic_series(resources)
    if len(names) < 2:
        return None
    group = [r for r in resources if r.get("name") in names]

    def sort_key(r: dict) -> tuple:
        # period_sort_key (year/month parsed from the name) comes first --
        # confirmed live that CKAN's last_modified/created can't be trusted
        # to track the period a resource covers. Only falls back to the
        # timestamp to break ties within the same extracted period.
        return (period_sort_key(r.get("name") or ""), r.get("last_modified") or r.get("created") or "")

    group.sort(key=sort_key, reverse=True)
    return group[0], group[1]


def register_detect_series_pattern_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    @log_tool
    async def detect_series_pattern(
        dataset_id: str,
        resource_id_new: str | None = None,
        resource_id_old: str | None = None,
        source: str = "nacional",
        format: str = "text",
    ) -> str:
        """
        Tell whether a dataset's periodic files (one per week/month/etc) replace
        each other (cumulative -- only the newest file matters) or complement
        each other (incremental -- every file must be combined) before you
        aggregate or sum values across them.

        Downloads the two most recent files from the dataset's periodic-name
        group (see list_dataset_resources's possible_periodic_series), finds a
        date/period-like column in each (matched by header name: fecha, mes,
        ano, periodo, semana, ...), and compares which period values appear in
        both. High overlap means the newer file already contains the older
        file's periods (cumulative); near-zero overlap means each file covers
        its own distinct period (incremental). This is a heuristic over a
        sample of up to 500 rows per file -- confirm with preview_resource_data
        if the result is close to the threshold or comes back indeterminado.

        Args:
            dataset_id: The dataset ID or slug
            resource_id_new: Optional -- newer resource ID to compare (auto-detected
                from the dataset's periodic-name group if omitted)
            resource_id_old: Optional -- older resource ID to compare (auto-detected
                if omitted). Both resource_id_new/resource_id_old must be given
                together, or neither.
            source: "nacional" (default) or "cuenca" (Cuenca municipal portal)
            format: text | json
        """
        if bool(resource_id_new) != bool(resource_id_old):
            return render_output(
                {"error": "faltan_ids"},
                format,
                text_builder=lambda _: (
                    "Error: pasa resource_id_new y resource_id_old juntos, o "
                    "ninguno de los dos (para autodetectar el par)."
                ),
            )

        session = httpx.AsyncClient()
        try:
            if resource_id_new and resource_id_old:
                try:
                    res_new = await ckan_client.get_resource(
                        resource_id_new, source=source, session=session
                    )
                    res_old = await ckan_client.get_resource(
                        resource_id_old, source=source, session=session
                    )
                except Exception as e:
                    return render_output(
                        {"error": str(e)},
                        format,
                        text_builder=lambda d: f"Error al obtener los recursos: {d['error']}",
                    )
            else:
                try:
                    dataset = await ckan_client.get_dataset(
                        dataset_id, source=source, session=session
                    )
                except Exception as e:
                    return render_output(
                        {"error": str(e)},
                        format,
                        text_builder=lambda d: f"Error al obtener el dataset: {d['error']}",
                    )
                pair = _pick_pair(dataset.get("resources", []))
                if pair is None:
                    return render_output(
                        {"error": "sin_serie_detectada", "dataset_id": dataset_id},
                        format,
                        text_builder=lambda d: (
                            "No se detectó un grupo de 3+ recursos con nombres de serie "
                            "periódica en este dataset. Usa list_dataset_resources para "
                            "revisar los recursos, o pasa resource_id_new/resource_id_old "
                            "explícitamente."
                        ),
                    )
                res_new, res_old = pair

            try:
                table_new = await _fetch_table(res_new, session)
            except (ValueError, httpx.HTTPError) as e:
                return render_output(
                    {"error": f"recurso_nuevo_no_legible: {e}"},
                    format,
                    text_builder=lambda d: f"Error: recurso más reciente {d['error']}",
                )
            try:
                table_old = await _fetch_table(res_old, session)
            except (ValueError, httpx.HTTPError) as e:
                return render_output(
                    {"error": f"recurso_viejo_no_legible: {e}"},
                    format,
                    text_builder=lambda d: f"Error: recurso más antiguo {d['error']}",
                )
        finally:
            await session.aclose()

        headers_new, rows_new = _locate_header_row(table_new["headers"], table_new["rows"])
        headers_old, rows_old = _locate_header_row(table_old["headers"], table_old["rows"])
        periods_new = _period_keys(headers_new, rows_new)
        periods_old = _period_keys(headers_old, rows_old)

        payload = {
            "dataset_id": dataset_id,
            "resource_new": {"id": res_new.get("id"), "name": res_new.get("name")},
            "resource_old": {"id": res_old.get("id"), "name": res_old.get("name")},
            "truncated_new": table_new.get("truncated", False),
            "truncated_old": table_old.get("truncated", False),
        }

        payload["schema_mismatch"] = _schema_mismatch(headers_old, headers_new)

        if periods_new is None or periods_old is None:
            payload["classification"] = "indeterminado"
            payload["reason"] = "sin_columna_periodo_detectada"
        elif payload["schema_mismatch"]:
            payload["classification"] = "indeterminado"
            payload["reason"] = "esquema_distinto_entre_archivos"
            payload["headers_old"] = headers_old
            payload["headers_new"] = headers_new
        else:
            keys_new, cols_new = periods_new
            keys_old, cols_old = periods_old
            overlap = keys_old & keys_new
            coverage = len(overlap) / len(keys_old) if keys_old else 0.0

            if coverage >= _CUMULATIVE_COVERAGE and len(keys_new) >= len(keys_old):
                classification = "acumulado"
            elif coverage <= _INCREMENTAL_COVERAGE:
                classification = "incremental"
            else:
                classification = "indeterminado"

            payload["classification"] = classification
            payload["period_columns_new"] = cols_new
            payload["period_columns_old"] = cols_old
            payload["periods_new_count"] = len(keys_new)
            payload["periods_old_count"] = len(keys_old)
            payload["overlap_count"] = len(overlap)
            payload["coverage"] = round(coverage, 2)

        def to_text(data: dict) -> str:
            parts = [
                f"Comparando serie periódica del dataset {data['dataset_id']}:",
                f"  Más reciente: {data['resource_new']['name']} ({data['resource_new']['id']})",
                f"  Más antiguo:  {data['resource_old']['name']} ({data['resource_old']['id']})",
                "",
            ]
            classification = data["classification"]
            if classification == "indeterminado" and data.get("reason") == "sin_columna_periodo_detectada":
                parts.append(
                    "Clasificación: INDETERMINADO -- no se encontró una columna de "
                    "fecha/período reconocible en alguno de los dos archivos. Revisa "
                    "manualmente con preview_resource_data."
                )
            elif classification == "indeterminado" and data.get("reason") == "esquema_distinto_entre_archivos":
                parts.append(
                    "Clasificación: INDETERMINADO -- estos dos archivos no parecen tener "
                    "el mismo formato interno (columnas muy distintas), aunque ambos "
                    "tengan un nombre casi idéntico. Compararlos por período no es válido; "
                    "puede que el dataset haya cambiado de formato entre estas fechas. "
                    f"Columnas archivo antiguo: {', '.join(data['headers_old']) or '(vacío)'}. "
                    f"Columnas archivo nuevo: {', '.join(data['headers_new']) or '(vacío)'}. "
                    "Revisa manualmente con preview_resource_data."
                )
            else:
                parts.append(
                    f"Columna(s) de período: {', '.join(data['period_columns_new'])}"
                )
                parts.append(
                    f"Períodos en el archivo más antiguo: {data['periods_old_count']}"
                )
                parts.append(
                    f"Períodos en el archivo más reciente: {data['periods_new_count']}"
                )
                parts.append(
                    f"Solapamiento: {data['overlap_count']} "
                    f"({data['coverage'] * 100:.0f}% de los períodos del archivo antiguo "
                    "también están en el nuevo)"
                )
                parts.append("")
                if classification == "acumulado":
                    parts.append(
                        "Clasificación: ACUMULADO -- el archivo más reciente ya incluye "
                        "los períodos del anterior. Probablemente basta con leer el más "
                        "reciente, no hace falta sumar entre archivos."
                    )
                elif classification == "incremental":
                    parts.append(
                        "Clasificación: INCREMENTAL -- los períodos casi no se solapan. "
                        "Cada archivo probablemente cubre un período distinto; hay que "
                        "combinarlos todos para tener la serie completa."
                    )
                else:
                    parts.append(
                        "Clasificación: INDETERMINADO -- el solapamiento no es lo "
                        "bastante alto ni bajo para decidir con confianza. Revisa "
                        "manualmente con preview_resource_data."
                    )
            if data.get("truncated_new") or data.get("truncated_old"):
                parts.append(
                    "\n⚠ Al menos uno de los dos archivos se truncó en la descarga o "
                    f"supera las {_ANALYZE_MAX_ROWS} filas analizadas -- la clasificación "
                    "puede estar incompleta."
                )
            return "\n".join(parts)

        return render_output(payload, format, text_builder=to_text)
