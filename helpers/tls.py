import ssl


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
