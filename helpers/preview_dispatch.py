"""Single kind -> preview_* dispatch shared by the resource-reading tools.

preview_resource_data, investigate_dataset and detect_series_pattern each
kept their own copy of this table and the copies drifted (detect_series_pattern
never gained ODS). Add new previewable kinds here only.
"""

import httpx

from helpers.csv_reader import (
    preview_csv,
    preview_json,
    preview_ods,
    preview_targz,
    preview_xls,
    preview_xlsb,
    preview_xlsx,
    preview_zip,
)

PREVIEW_DISPATCH = {
    "TARGZ": preview_targz,
    "ZIP": preview_zip,
    "XLS": preview_xls,
    "XLSB": preview_xlsb,
    "XLSX": preview_xlsx,
    "ODS": preview_ods,
    "JSON": preview_json,
    "CSV": preview_csv,
}

PREVIEWABLE_KINDS = frozenset(PREVIEW_DISPATCH)


async def preview_by_kind(
    kind: str,
    url: str,
    max_rows: int,
    session: httpx.AsyncClient | None = None,
) -> dict:
    """Run the preview function for `kind`; ValueError if there is none."""
    func = PREVIEW_DISPATCH.get(kind)
    if func is None:
        raise ValueError(f"formato '{kind}' no soportado")
    if session is None:
        return await func(url, max_rows=max_rows)
    return await func(url, max_rows=max_rows, session=session)
