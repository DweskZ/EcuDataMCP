import uvicorn

import main


def test_http_server_limits_how_long_it_waits_for_open_connections(monkeypatch):
    # 2026-11-20 on the Oracle VM: a client holding a connection open kept the
    # stop in "Waiting for connections to close" for the full 90 s systemd
    # allows, then SIGKILL; new connections were refused the whole time.
    captured: dict = {}
    monkeypatch.setattr(main, "ensure_financials_db_fresh", lambda: None)
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: captured.update(kwargs))

    main.main(["--transport", "http", "--host", "127.0.0.1"])

    assert captured["timeout_graceful_shutdown"] == main._GRACEFUL_SHUTDOWN_SECONDS
    assert 0 < main._GRACEFUL_SHUTDOWN_SECONDS < 90
