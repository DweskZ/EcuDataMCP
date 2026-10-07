import asyncio
import io
import os
import ssl
import time

import httpx
import openpyxl
import pytest

from helpers import supercias_client
from helpers.cache import TtlCache
from helpers.geo_proxy import proxy_for

_HEADER = (
    "No. FILA", "EXPEDIENTE", "RUC", "NOMBRE", "SITUACIÓN LEGAL",
    "FECHA_CONSTITUCION", "TIPO", "PAÍS", "REGIÓN", "PROVINCIA", "CANTÓN",
    "CIUDAD", "CALLE", "NÚMERO", "INTERSECCIÓN", "BARRIO", "TELÉFONO",
    "REPRESENTANTE", "CARGO", "CAPITAL SUSCRITO", "CIIU NIVEL 1",
    "CIIU NIVEL 6", "ÚLTIMO BALANCE", "PRESENTÓ BALANCE INICIAL",
    "FECHA PRESENTACIÓN BALANCE INICIAL",
)

_ROW_1 = (
    1, "1", "1790013731001", "ACEITES TROPICALES SOCIEDAD ANONIMA ATSA",
    "ACTIVA", "20/07/1951", "ANÓNIMA", "ECUADOR", "SIERRA", "PICHINCHA",
    "QUITO", "QUITO", "VIA QUININDE KM 37", "SN", "SN", "", "022762426",
    "ACOSTA LLERENA JUAN CARLOS", "GERENTE GENERAL", "48.200,00", "A",
    "A0126.01", "2025", "NO APLICA", "NO APLICA",
)
_ROW_2 = (
    2, "2", "1790004724001", "ACERIA DEL ECUADOR CA ADELCA.", "ACTIVA",
    "17/12/1963", "ANÓNIMA", "ECUADOR", "SIERRA", "GUAYAS", "GUAYAQUIL",
    "GUAYAQUIL", "PANAMERICANA NORTE", "S/N", "S/N", "", "023801321",
    "DIRECACERO DIRECCION DE EMPRESAS DEL ACERO S.A.", "PRESIDENTE EJECUTIVO",
    "125.500.000,00", "C", "C2410.25", "2025", "NO APLICA", "NO APLICA",
)


def _build_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(("SUPERINTENDENCIA DE COMPAÑÍAS, VALORES Y SEGUROS",))
    ws.append(("DIRECTORIO DE COMPAÑÍAS",))
    ws.append(("No. DE FILAS: 2",))
    ws.append(("FECHA DE ACTUALIZACION: 13/08/2026 00:53:11",))
    ws.append(_HEADER)
    ws.append(_ROW_1)
    ws.append(_ROW_2)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_xlsx_with_duplicate_ruc() -> bytes:
    dup_row = (
        3, "3", "1790013731001", "ACEITES TROPICALES (EXPEDIENTE DUPLICADO)",
        "ACTIVA", "20/07/1951", "ANÓNIMA", "ECUADOR", "SIERRA", "PICHINCHA",
        "QUITO", "QUITO", "VIA QUININDE KM 37", "SN", "SN", "", "022762426",
        "OTRO REPRESENTANTE", "GERENTE GENERAL", "48.200,00", "A",
        "A0126.01", "2025", "NO APLICA", "NO APLICA",
    )
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(("SUPERINTENDENCIA DE COMPAÑÍAS, VALORES Y SEGUROS",))
    ws.append(("DIRECTORIO DE COMPAÑÍAS",))
    ws.append(("No. DE FILAS: 3",))
    ws.append(("FECHA DE ACTUALIZACION: 13/08/2026 00:53:11",))
    ws.append(_HEADER)
    ws.append(_ROW_1)
    ws.append(_ROW_2)
    ws.append(dup_row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_AUDITORES_HEADER = (
    "RNAE", "IDENTIFICACIÓN", "NOMBRE", "NÚMERO DE RESOLUCIÓN",
    "FECHA DE RESOLUCIÓN", "NACIONALIDAD", "PROVINCIA", "CANTÓN",
    "DIRECCIÓN", "TELÉFONO", "CORREO ELECTRÓNICO",
)

_AUDITOR_ROW_1 = (
    "1379", "1792904471001", "'ACG' ATTESTING & CONSULTING GROUP C.L.",
    "35791", "25/10/2019", "ECUADOR", "PICHINCHA", "QUITO",
    "AV. SOLANDA S24-37", "025129335", "info@acg-ec.com",
)
_AUDITOR_ROW_2 = (
    "1424", "0993226475001", "'ADVANCED AUDIT ECUADOR' AAE CIA.LTDA.",
    "11854", "15/06/2026", "ECUADOR", "GUAYAS", "GUAYAQUIL",
    "AV. FRANCISCO DE ORELLANA", "042443199", "corellana@advanced.ec",
)


def _build_auditores_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(("SUPERINTENDENCIA DE COMPAÑÍAS, VALORES Y SEGUROS",))
    ws.append(("LISTADO DE AUDITORES EXTERNOS",))
    ws.append(("No. DE FILAS: 2",))
    ws.append(("FECHA DE ACTUALIZACION: 15/08/2026 00:05:14",))
    ws.append(_AUDITORES_HEADER)
    ws.append(_AUDITOR_ROW_1)
    ws.append(_AUDITOR_ROW_2)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _reset_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("ECUADOR_MCP_GEO_PROXY", raising=False)
    supercias_client._companias_cache = TtlCache(ttl_seconds=60)
    supercias_client._ruc_index_state = None
    supercias_client._download_task = None
    supercias_client._auditores_cache = TtlCache(ttl_seconds=60)
    supercias_client._identificacion_index_state = None
    yield


def test_col_index():
    assert supercias_client._col_index("A1") == 0
    assert supercias_client._col_index("Z12") == 25
    assert supercias_client._col_index("AA1") == 26


def test_normalize_header():
    assert supercias_client._normalize_header("SITUACIÓN LEGAL") == "situacion_legal"
    assert supercias_client._normalize_header("No. FILA") == "no_fila"
    assert supercias_client._normalize_header("CIIU NIVEL 1") == "ciiu_nivel_1"


def test_parse_xlsx_skips_title_rows_and_detects_header():
    fields, rows = supercias_client._parse_xlsx(_build_xlsx())

    assert fields[2] == "ruc"
    assert fields[3] == "nombre"
    assert len(rows) == 2
    assert rows[0][fields.index("ruc")] == "1790013731001"
    assert rows[0][fields.index("nombre")] == "ACEITES TROPICALES SOCIEDAD ANONIMA ATSA"
    assert rows[1][fields.index("provincia")] == "GUAYAS"


def test_parse_xlsx_raises_without_header():
    only_titles = io.BytesIO()
    wb = openpyxl.Workbook()
    ws = wb.active
    for _ in range(25):
        ws.append(("no header here",))
    wb.save(only_titles)

    with pytest.raises(ValueError, match="encabezado"):
        supercias_client._parse_xlsx(only_titles.getvalue())


async def test_search_companias_by_name_and_ruc(httpx_mock):
    httpx_mock.add_response(url=supercias_client._EXCEL_URL, content=_build_xlsx())

    by_name = await supercias_client.search_companias(query="aceria")
    assert by_name["total"] == 1
    assert by_name["companias"][0]["ruc"] == "1790004724001"

    by_ruc = await supercias_client.search_companias(query="1790013731001")
    assert by_ruc["total"] == 1
    assert by_ruc["companias"][0]["nombre"].startswith("ACEITES TROPICALES")


async def test_search_companias_filters_by_provincia_and_situacion(httpx_mock):
    httpx_mock.add_response(url=supercias_client._EXCEL_URL, content=_build_xlsx())

    result = await supercias_client.search_companias(
        provincia="guayas", situacion_legal="activa"
    )
    assert result["total"] == 1
    assert result["companias"][0]["provincia"] == "GUAYAS"


async def test_search_companias_uses_cache_across_calls(httpx_mock):
    httpx_mock.add_response(url=supercias_client._EXCEL_URL, content=_build_xlsx())

    await supercias_client.search_companias(query="aceria")
    # A second call must not trigger another network request (httpx_mock
    # would fail the test on an unexpected/unmatched extra request).
    await supercias_client.search_companias(query="aceites")


async def test_get_compania_by_ruc_found_and_not_found(httpx_mock):
    httpx_mock.add_response(url=supercias_client._EXCEL_URL, content=_build_xlsx())

    found = await supercias_client.get_compania_by_ruc("1790013731001")
    assert found is not None
    assert found["representante"] == "ACOSTA LLERENA JUAN CARLOS"

    missing = await supercias_client.get_compania_by_ruc("0000000000000")
    assert missing is None


async def test_get_compania_by_expediente_found_and_not_found(httpx_mock):
    httpx_mock.add_response(url=supercias_client._EXCEL_URL, content=_build_xlsx())

    found = await supercias_client.get_compania_by_expediente("1")
    assert found is not None
    assert found["nombre"] == "ACEITES TROPICALES SOCIEDAD ANONIMA ATSA"
    assert found["ruc"] == "1790013731001"

    missing = await supercias_client.get_compania_by_expediente("999999")
    assert missing is None


def test_parse_xlsx_raises_when_data_row_exceeds_header_width():
    # Simulate a header row whose last cell is blank (dropped from the row's
    # XML entirely) by writing the real header minus its last column, while
    # a data row still has a value in that trailing column.
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(("SUPERINTENDENCIA DE COMPAÑÍAS, VALORES Y SEGUROS",))
    ws.append(("DIRECTORIO DE COMPAÑÍAS",))
    ws.append(("No. DE FILAS: 1",))
    ws.append(("FECHA DE ACTUALIZACION: 13/08/2026 00:53:11",))
    ws.append(_HEADER[:-1])
    ws.append(_ROW_1)
    buf = io.BytesIO()
    wb.save(buf)

    with pytest.raises(ValueError, match="incompleto"):
        supercias_client._parse_xlsx(buf.getvalue())


async def test_duplicate_ruc_keeps_last_row_and_logs_warning(httpx_mock, caplog):
    httpx_mock.add_response(
        url=supercias_client._EXCEL_URL, content=_build_xlsx_with_duplicate_ruc()
    )

    with caplog.at_level("WARNING"):
        found = await supercias_client.get_compania_by_ruc("1790013731001")

    assert found is not None
    assert found["nombre"] == "ACEITES TROPICALES (EXPEDIENTE DUPLICADO)"
    assert any("duplicado" in rec.message for rec in caplog.records)


async def test_ruc_index_is_cached_across_lookups(httpx_mock):
    httpx_mock.add_response(url=supercias_client._EXCEL_URL, content=_build_xlsx())

    await supercias_client.get_compania_by_ruc("1790013731001")
    state_after_first = supercias_client._ruc_index_state
    assert state_after_first is not None

    # A second lookup (and an unrelated search) must reuse the same index
    # object rather than rebuilding it, since the underlying rows haven't
    # changed.
    await supercias_client.get_compania_by_ruc("1790004724001")
    await supercias_client.search_companias(query="aceria")
    assert supercias_client._ruc_index_state is state_after_first


async def test_download_full_retries_insecurely_on_cert_failure(monkeypatch):
    # CKAN_INSECURE_TLS defaults to off (post-cert-renewal); opt in explicitly
    # to exercise the retry path itself.
    monkeypatch.setenv("CKAN_INSECURE_TLS", "1")
    calls: list[bool] = []

    async def fake_download_once(url: str, verify: bool = True) -> bytes:
        calls.append(verify)
        if verify:
            exc = httpx.ConnectError("cert failure")
            exc.__context__ = ssl.SSLCertVerificationError("bad cert")
            raise exc
        return b"ok"

    monkeypatch.setattr(supercias_client, "_download_once", fake_download_once)

    result = await supercias_client._download_full(supercias_client._EXCEL_URL)

    assert result == b"ok"
    assert calls == [True, False]


async def test_download_full_does_not_retry_non_cert_connect_errors(monkeypatch):
    async def fake_download_once(url: str, verify: bool = True) -> bytes:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(supercias_client, "_download_once", fake_download_once)

    with pytest.raises(RuntimeError, match="ConnectError"):
        await supercias_client._download_full(supercias_client._EXCEL_URL)


async def test_download_full_names_host_on_bare_connect_timeout(monkeypatch):
    # A bare ConnectTimeout stringifies to "", which used to reach the tool
    # layer as an empty error message.
    async def fake_download_once(url: str, verify: bool = True) -> bytes:
        raise httpx.ConnectTimeout("")

    monkeypatch.setattr(supercias_client, "_download_once", fake_download_once)

    with pytest.raises(RuntimeError) as excinfo:
        await supercias_client._download_full(supercias_client._EXCEL_URL)

    assert "mercadodevalores.supercias.gob.ec" in str(excinfo.value)
    assert "ConnectTimeout" in str(excinfo.value)
    assert "ECUADOR_MCP_GEO_PROXY" in str(excinfo.value)


def test_directory_download_goes_through_geo_proxy(monkeypatch):
    monkeypatch.setenv("ECUADOR_MCP_GEO_PROXY", "socks5://127.0.0.1:1080")

    assert proxy_for(supercias_client._EXCEL_URL) == "socks5://127.0.0.1:1080"


async def test_download_is_saved_and_reused_after_restart(httpx_mock):
    # Built once: openpyxl stamps the current time into each file, so two
    # builds differ whenever a second boundary falls between them.
    export = _build_xlsx()
    httpx_mock.add_response(url=supercias_client._EXCEL_URL, content=export)

    await supercias_client.search_companias(query="aceria")
    assert supercias_client._directory_path().read_bytes() == export

    # A new process starts with an empty memory cache; the saved copy must
    # be parsed without another download (pytest-httpx fails on extra calls).
    supercias_client._companias_cache = TtlCache(ttl_seconds=60)
    result = await supercias_client.search_companias(query="aceria")

    assert result["total"] == 1


async def test_cold_call_returns_quickly_while_download_continues(monkeypatch):
    release = asyncio.Event()

    async def slow_download(url: str) -> bytes:
        await release.wait()
        return _build_xlsx()

    monkeypatch.setattr(supercias_client, "_download_full", slow_download)
    monkeypatch.setattr(supercias_client, "_INLINE_WAIT_SECONDS", 0.05)

    with pytest.raises(supercias_client.DirectorioEnDescarga):
        await supercias_client.search_companias(query="aceria")

    release.set()
    await supercias_client._download_task
    result = await supercias_client.search_companias(query="aceria")

    assert result["total"] == 1


async def test_stale_copy_is_served_while_refreshing(monkeypatch):
    export = _build_xlsx()
    path = supercias_client._directory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(export)
    old = time.time() - supercias_client._DISK_MAX_AGE_SECONDS - 60
    os.utime(path, (old, old))
    downloads: list[str] = []

    async def failing_download(url: str) -> bytes:
        downloads.append(url)
        raise RuntimeError("No se pudo conectar")

    monkeypatch.setattr(supercias_client, "_download_full", failing_download)

    result = await supercias_client.search_companias(query="aceria")
    with pytest.raises(RuntimeError):
        await supercias_client._download_task

    assert result["total"] == 1
    assert downloads == [supercias_client._EXCEL_URL]
    assert path.read_bytes() == export


async def test_unreadable_saved_copy_is_replaced(httpx_mock):
    path = supercias_client._directory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a zip")
    export = _build_xlsx()
    httpx_mock.add_response(url=supercias_client._EXCEL_URL, content=export)

    result = await supercias_client.search_companias(query="aceria")

    assert result["total"] == 1
    assert path.read_bytes() == export


def test_parse_xlsx_uses_identificacion_header_marker_for_auditores():
    fields, rows = supercias_client._parse_xlsx(
        _build_auditores_xlsx(), header_markers=("identificacion", "nombre")
    )

    assert "identificacion" in fields
    assert "nombre" in fields
    assert len(rows) == 2
    assert rows[0][fields.index("identificacion")] == "1792904471001"


async def test_search_auditores_by_name_and_identificacion(httpx_mock):
    httpx_mock.add_response(
        url=supercias_client._AUDITORES_EXCEL_URL, content=_build_auditores_xlsx()
    )

    by_name = await supercias_client.search_auditores(query="advanced")
    assert by_name["total"] == 1
    assert by_name["auditores"][0]["identificacion"] == "0993226475001"

    by_id = await supercias_client.search_auditores(query="1792904471001")
    assert by_id["total"] == 1
    assert "ACG" in by_id["auditores"][0]["nombre"]


async def test_search_auditores_filters_by_provincia(httpx_mock):
    httpx_mock.add_response(
        url=supercias_client._AUDITORES_EXCEL_URL, content=_build_auditores_xlsx()
    )

    result = await supercias_client.search_auditores(provincia="guayas")
    assert result["total"] == 1
    assert result["auditores"][0]["provincia"] == "GUAYAS"


async def test_get_auditor_info_found_and_not_found(httpx_mock):
    httpx_mock.add_response(
        url=supercias_client._AUDITORES_EXCEL_URL, content=_build_auditores_xlsx()
    )

    found = await supercias_client.get_auditor_info("1792904471001")
    assert found is not None
    assert found["rnae"] == "1379"

    missing = await supercias_client.get_auditor_info("0000000000000")
    assert missing is None


async def test_auditores_and_companias_caches_are_independent(httpx_mock):
    httpx_mock.add_response(url=supercias_client._EXCEL_URL, content=_build_xlsx())
    httpx_mock.add_response(
        url=supercias_client._AUDITORES_EXCEL_URL, content=_build_auditores_xlsx()
    )

    companias = await supercias_client.search_companias(query="aceria")
    auditores = await supercias_client.search_auditores(query="advanced")

    assert companias["total"] == 1
    assert auditores["total"] == 1
