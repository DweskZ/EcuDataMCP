import os
import ssl
from urllib.parse import urlparse

# Portal domains known to ship an expired/broken cert. Keep this narrow so
# third-party resource hosts are never silently downgraded.
_INSECURE_TLS_HOST_SUFFIXES = (
    "datosabiertos.gob.ec",
    "datosabiertos.presidencia.gob.ec",
    "mercadodevalores.supercias.gob.ec",
)


def insecure_tls_enabled() -> bool:
    """Allow insecure TLS retry, opt-in only.

    The portal's cert was expired 2026-07-28 through early August; this
    defaulted on during that window. Renewed 2026-08-07 (valid through
    2026-11-05), so the fallback now defaults off. Set CKAN_INSECURE_TLS=1
    if the portal's cert breaks again before the code is updated.
    """
    raw = os.getenv("CKAN_INSECURE_TLS", "0").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def host_allows_insecure_tls(url: str) -> bool:
    """Return True only for government open-data hosts on the allowlist."""
    if not insecure_tls_enabled():
        return False
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in _INSECURE_TLS_HOST_SUFFIXES)


def is_cert_verification_error(exc: BaseException) -> bool:
    """Walk an exception's cause/context chain for ssl.SSLCertVerificationError.

    httpx/httpcore re-wrap the raw ssl error as they propagate it, and only
    preserve it via __context__ (implicit chaining), not __cause__ — so both
    have to be checked to tell a real cert failure apart from other connect
    errors (DNS, refused connection, etc.) that must not be silently retried
    without verification.
    """
    seen: set[int] = set()
    stack = [exc]
    while stack:
        e = stack.pop()
        if e is None or id(e) in seen:
            continue
        seen.add(id(e))
        if isinstance(e, ssl.SSLCertVerificationError):
            return True
        stack.append(e.__cause__)
        stack.append(e.__context__)
    return False


def should_retry_insecure(exc: BaseException, url: str) -> bool:
    """True when a cert failure on an allowlisted host may be retried insecurely."""
    return host_allows_insecure_tls(url) and is_cert_verification_error(exc)


# Hosts that fail the TLS handshake outright under OpenSSL 3's default
# SECLEVEL=2 (SSLV3_ALERT_HANDSHAKE_FAILURE) because they only offer legacy
# cipher suites — a different failure mode than an expired/invalid cert
# (should_retry_insecure, above). Verified against
# appscvsmovil.supercias.gob.ec: default httpx/OpenSSL settings fail the
# handshake before a certificate is ever presented; lowering the cipher
# security level to 1 connects fine and still verifies the certificate
# normally. Keep this list separate from _INSECURE_TLS_HOST_SUFFIXES — the
# two are not interchangeable and must not be merged into one allowlist.
_LEGACY_CIPHER_HOST_SUFFIXES = ("appscvsmovil.supercias.gob.ec",)


def host_needs_legacy_ciphers(url: str) -> bool:
    """Return True only for hosts known to require SECLEVEL=1 to negotiate TLS."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(
        host == suffix or host.endswith("." + suffix)
        for suffix in _LEGACY_CIPHER_HOST_SUFFIXES
    )


def legacy_cipher_context() -> ssl.SSLContext:
    """SSLContext accepting legacy cipher suites, for hosts with old TLS configs.

    Unlike the insecure-retry fallback above, this does not skip certificate
    verification — it only lowers OpenSSL's minimum cipher strength
    requirement (SECLEVEL) so the handshake with an old server config
    completes at all. Build fresh per use; ssl.SSLContext is not guaranteed
    safe to share/reuse across concurrent connections.
    """
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    return ctx
