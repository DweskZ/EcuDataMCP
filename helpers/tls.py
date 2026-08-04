import os
import ssl
from urllib.parse import urlparse

# Portal domains known to ship an expired/broken cert. Keep this narrow so
# third-party resource hosts are never silently downgraded.
_INSECURE_TLS_HOST_SUFFIXES = (
    "datosabiertos.gob.ec",
    "datosabiertos.presidencia.gob.ec",
)


def insecure_tls_enabled() -> bool:
    """Allow insecure TLS retry. Default on until the portal renews its cert."""
    raw = os.getenv("CKAN_INSECURE_TLS", "1").strip().lower()
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
