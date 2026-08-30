import asyncio

from helpers.http_security import with_http_security


async def _call(app, path="/mcp", headers=()):
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    scope = {"type": "http", "path": path, "headers": list(headers)}
    await app(scope, receive, send)
    return messages


async def _ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def test_mcp_requires_bearer_token_when_configured():
    app = with_http_security(_ok_app, auth_token="secret")

    messages = await _call(app)

    assert messages[0]["status"] == 401
    assert (b"www-authenticate", b"Bearer") in messages[0]["headers"]

    messages = await _call(app, headers=[(b"authorization", b"Bearer secret")])
    assert messages[0]["status"] == 204


async def test_health_and_other_paths_are_not_blocked_by_mcp_auth():
    app = with_http_security(_ok_app, auth_token="secret")

    assert (await _call(app, path="/health"))[0]["status"] == 204
    assert (await _call(app, path="/unknown"))[0]["status"] == 204


async def test_mcp_rejects_work_when_concurrency_limit_is_reached():
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocking_app(scope, receive, send):
        started.set()
        await release.wait()
        await _ok_app(scope, receive, send)

    app = with_http_security(blocking_app, max_concurrent_requests=1)
    first = asyncio.create_task(_call(app))
    await started.wait()

    second = await _call(app)
    assert second[0]["status"] == 503

    release.set()
    assert (await first)[0]["status"] == 204
