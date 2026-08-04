import ssl

from helpers.tls import (
    host_allows_insecure_tls,
    is_cert_verification_error,
    should_retry_insecure,
)


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


def test_should_retry_insecure(monkeypatch):
    monkeypatch.setenv("CKAN_INSECURE_TLS", "1")
    exc = ssl.SSLCertVerificationError("bad")
    assert (
        should_retry_insecure(exc, "https://www.datosabiertos.gob.ec/resource.csv")
        is True
    )
    assert should_retry_insecure(exc, "https://cdn.other.org/x.csv") is False
