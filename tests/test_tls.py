import ssl

from helpers.tls import (
    host_allows_insecure_tls,
    host_needs_legacy_ciphers,
    insecure_tls_enabled,
    is_cert_verification_error,
    legacy_cipher_context,
    should_retry_insecure,
)


def test_insecure_tls_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CKAN_INSECURE_TLS", raising=False)
    assert insecure_tls_enabled() is False


def test_is_cert_verification_error_walks_context():
    root = ssl.SSLCertVerificationError("expired")
    wrapped = ConnectionError("connect failed")
    wrapped.__context__ = root
    assert is_cert_verification_error(wrapped) is True


def test_is_cert_verification_error_ignores_other_errors():
    assert is_cert_verification_error(ConnectionError("refused")) is False


def test_host_allowlist(monkeypatch):
    monkeypatch.setenv("CKAN_INSECURE_TLS", "1")
    assert host_allows_insecure_tls("https://www.datosabiertos.gob.ec/api") is True
    assert host_allows_insecure_tls("https://evil.example/file.csv") is False


def test_host_allowlist_can_be_disabled(monkeypatch):
    monkeypatch.setenv("CKAN_INSECURE_TLS", "0")
    assert host_allows_insecure_tls("https://www.datosabiertos.gob.ec/api") is False


def test_host_allowlist_includes_supercias(monkeypatch):
    monkeypatch.setenv("CKAN_INSECURE_TLS", "1")
    assert (
        host_allows_insecure_tls(
            "https://mercadodevalores.supercias.gob.ec/reportes/excel/x.xlsx"
        )
        is True
    )


def test_should_retry_insecure(monkeypatch):
    monkeypatch.setenv("CKAN_INSECURE_TLS", "1")
    exc = ssl.SSLCertVerificationError("bad")
    assert (
        should_retry_insecure(exc, "https://www.datosabiertos.gob.ec/resource.csv")
        is True
    )
    assert should_retry_insecure(exc, "https://cdn.other.org/x.csv") is False


def test_host_needs_legacy_ciphers():
    assert (
        host_needs_legacy_ciphers(
            "https://appscvsmovil.supercias.gob.ec/ranking/recursos/bi_ranking.csv"
        )
        is True
    )
    assert host_needs_legacy_ciphers("https://cdn.other.org/x.csv") is False


def test_legacy_cipher_context_sets_seclevel_1():
    ctx = legacy_cipher_context()
    assert isinstance(ctx, ssl.SSLContext)
    # Still verifies certificates -- this only relaxes cipher strength, not
    # verification, unlike should_retry_insecure's verify=False fallback.
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
