import io
import ipaddress
import zipfile

import pytest

from helpers import ckan_client, csv_reader, safe_download, tls
from helpers.pdf_reader import _parse_pages


def test_decode_text_tolerates_truncated_multibyte_tail():
    raw = ("nombre,valor\n" + "ñandú,1\n" * 50).encode()[:-1]  # cut inside 'ú'

    text = csv_reader._decode_text(raw, truncated=True)

    assert text.startswith("nombre,valor\nñandú,1")


def test_decode_text_prefers_cp1252_over_latin1():
    assert csv_reader._decode_text("x “q” €".encode("cp1252")) == "x “q” €"


def test_parse_pages_clamps_huge_range():
    indices, _ = _parse_pages("1-99999999999", total_pages=3)

    assert indices == [0, 1, 2]


def test_eu_decimal_only_converts_cells_that_match_the_pattern():
    headers = ["valor"]
    rows = [["1,5"], ["2,5"], ["3,5"], ["4,5"], ["5,5"], ["7.5"], ["1.234,5"]]

    new_rows, converted = csv_reader.normalize_eu_decimal_columns(headers, rows)

    assert converted == ["valor"]
    assert [r[0] for r in new_rows][-2:] == ["7.5", "1234.5"]


def test_pick_member_skips_macos_resource_forks():
    names = ["__MACOSX/._data.csv", "data.csv"]

    assert csv_reader._pick_member(names) == "data.csv"


def test_zip_container_size_guard_rejects_expanding_archives():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/sharedStrings.xml", b"a" * (210 * 1024 * 1024))

    with pytest.raises(ValueError, match="se expande"):
        csv_reader._check_zip_container_size(buf.getvalue(), ".xlsx")


@pytest.mark.parametrize("value", ["", "maybe", "0", "false"])
def test_insecure_tls_requires_explicit_opt_in(monkeypatch, value):
    monkeypatch.setenv("CKAN_INSECURE_TLS", value)

    assert tls.insecure_tls_enabled() is False


def test_insecure_tls_opt_in(monkeypatch):
    monkeypatch.setenv("CKAN_INSECURE_TLS", "1")

    assert tls.insecure_tls_enabled() is True


@pytest.mark.parametrize(
    ("ip", "public"),
    [
        ("93.184.216.34", True),
        ("100.64.0.1", False),  # CGNAT / tailnet
        ("10.0.0.1", False),
        ("64:ff9b::808:808", False),  # NAT64
        ("::ffff:127.0.0.1", False),
    ],
)
def test_is_public_ip(ip, public):
    assert safe_download._is_public_ip(ipaddress.ip_address(ip)) is public


def test_solr_quote_neutralises_filter_syntax():
    assert ckan_client._solr_quote('a b") OR x:(') == '"a b\\") OR x:("'


@pytest.mark.asyncio
async def test_sgr_arcgis_error_body_raises(httpx_mock):
    from helpers import sgr_client

    httpx_mock.add_response(
        url="https://example.test/q", json={"error": {"code": 400, "message": "bad"}}
    )

    with pytest.raises(RuntimeError, match="SGR"):
        await sgr_client._get_json("https://example.test/q")


def test_sgr_object_id_sorts_numerically():
    from helpers import sgr_client

    assert sgr_client._object_id({"OBJECTID": "10"}) > sgr_client._object_id({"OBJECTID": "9"})
    assert sgr_client._object_id({}) == 0
