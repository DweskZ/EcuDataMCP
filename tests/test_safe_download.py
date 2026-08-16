import socket

import httpx
import pytest

from helpers.safe_download import UnsafeUrlError, assert_public_url, safe_stream


def _fake_getaddrinfo(ip: str):
    def _inner(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return _inner


def test_assert_public_url_accepts_public_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    assert_public_url("https://example.com/file.csv")  # must not raise


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # RFC1918 private
        "192.168.1.1",  # RFC1918 private
        "172.16.0.1",  # RFC1918 private
        "169.254.169.254",  # link-local / cloud metadata endpoint
        "224.0.0.1",  # multicast
        "0.0.0.0",  # unspecified
    ],
)
def test_assert_public_url_rejects_non_public_ips(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(ip))
    with pytest.raises(UnsafeUrlError):
        assert_public_url("https://attacker-controlled.example/x")


def test_assert_public_url_rejects_bad_scheme():
    with pytest.raises(UnsafeUrlError, match="Esquema"):
        assert_public_url("file:///etc/passwd")


def test_assert_public_url_rejects_unresolvable_host(monkeypatch):
    def _raise(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", _raise)
    with pytest.raises(UnsafeUrlError, match="resolver"):
        assert_public_url("https://this-does-not-resolve.invalid/x")


async def test_safe_stream_follows_redirect_to_public_host(monkeypatch, httpx_mock):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    httpx_mock.add_response(
        url="https://example.com/redirect",
        status_code=302,
        headers={"location": "https://example.com/final"},
    )
    httpx_mock.add_response(url="https://example.com/final", content=b"hola")

    async with (
        httpx.AsyncClient() as session,
        safe_stream(session, "https://example.com/redirect") as resp,
    ):
        body = await resp.aread()
    assert body == b"hola"


async def test_safe_stream_rejects_redirect_to_private_ip(monkeypatch, httpx_mock):
    # First hop resolves publicly; the redirect target resolves privately.
    calls = {"n": 0}

    def getaddrinfo(host, port, *args, **kwargs):
        calls["n"] += 1
        ip = "93.184.216.34" if calls["n"] == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    httpx_mock.add_response(
        url="https://example.com/redirect",
        status_code=302,
        headers={"location": "http://internal.example/secret"},
    )

    async with httpx.AsyncClient() as session:
        with pytest.raises(UnsafeUrlError):
            async with safe_stream(session, "https://example.com/redirect") as resp:
                await resp.aread()


async def test_safe_stream_caps_redirect_count(monkeypatch, httpx_mock):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    # max_redirects=3 below means hops 0-3 get requested (the 4th hop's
    # response, still a redirect, is where the cap kicks in) -- hop4+ must
    # never be requested, so only registering up to hop3 doubles as a
    # regression guard against following one hop too many.
    for i in range(4):
        httpx_mock.add_response(
            url=f"https://example.com/hop{i}",
            status_code=302,
            headers={"location": f"https://example.com/hop{i + 1}"},
        )

    async with httpx.AsyncClient() as session:
        with pytest.raises(UnsafeUrlError, match="redirecciones"):
            async with safe_stream(
                session, "https://example.com/hop0", max_redirects=3
            ) as resp:
                await resp.aread()
