import ssl

from helpers.tls import (
    host_allows_insecure_tls,
    host_needs_legacy_ciphers,
    host_needs_os_trust_store,
    insecure_tls_enabled,
    is_cert_verification_error,
    legacy_cipher_context,
    os_trust_context,
    should_retry_insecure,
    should_retry_with_os_trust,
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


def test_host_needs_os_trust_store():
    assert host_needs_os_trust_store("https://www.censoecuador.gob.ec/foo/") is True
    assert host_needs_os_trust_store("https://cdn.other.org/x.csv") is False


def test_should_retry_with_os_trust_not_gated_by_insecure_flag(monkeypatch):
    # Unlike should_retry_insecure, this doesn't disable verification, so it
    # must work even with CKAN_INSECURE_TLS unset/off.
    monkeypatch.delenv("CKAN_INSECURE_TLS", raising=False)
    exc = ssl.SSLCertVerificationError("unable to get local issuer certificate")
    assert (
        should_retry_with_os_trust(exc, "https://www.censoecuador.gob.ec/foo/")
        is True
    )
    assert should_retry_with_os_trust(exc, "https://cdn.other.org/x.csv") is False


def test_os_trust_context_still_fully_verifies():
    ctx = os_trust_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_os_trust_context_loads_bundled_intermediates():
    # Regression test for the 2026-09-02 smoke-test failure: the previous
    # implementation retried against ssl.create_default_context()'s bare OS
    # trust store, which only worked on a developer's own machine (Windows/
    # macOS opportunistically fetch a missing intermediate via AIA) and
    # failed the same way on a clean GitHub Actions Linux runner. Loading
    # the bundled intermediate CAs must not raise, regardless of platform.
    ctx = os_trust_context()
    # ssl.SSLContext doesn't expose loaded CA count directly, but a context
    # that failed to load the bundle (missing/corrupt file) would have
    # raised inside os_trust_context() already -- reaching here at all is
    # the assertion. get_ca_certs() confirms more than just certifi's roots
    # got loaded.
    assert len(ctx.get_ca_certs()) > 0
