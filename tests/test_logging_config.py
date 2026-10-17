import logging

import pytest

from helpers.logging import log_level, uvicorn_log_level, uvicorn_logging_config


def test_uvicorn_loggers_follow_log_level(monkeypatch):
    # LOG_LEVEL used to change only the app logger while uvicorn (and its
    # access log) stayed hard-coded at INFO.
    monkeypatch.setenv("LOG_LEVEL", "warning")

    config = uvicorn_logging_config()

    assert log_level() == logging.WARNING
    assert uvicorn_log_level() == "warning"
    assert {lg["level"] for lg in config["loggers"].values()} == {"WARNING"}


def test_debug_log_level_reaches_access_log(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert uvicorn_logging_config()["loggers"]["uvicorn.access"]["level"] == "DEBUG"
    assert uvicorn_log_level() == "debug"


@pytest.mark.parametrize("value", ["", "ruidoso", "15"])
def test_unknown_log_level_falls_back_to_info(monkeypatch, value):
    monkeypatch.setenv("LOG_LEVEL", value)
    assert log_level() == logging.INFO
    assert uvicorn_log_level() == "info"


def test_log_level_aliases_map_to_uvicorn_names(monkeypatch):
    # uvicorn only accepts critical/error/warning/info/debug.
    monkeypatch.setenv("LOG_LEVEL", "WARN")
    assert uvicorn_log_level() == "warning"
    monkeypatch.setenv("LOG_LEVEL", "FATAL")
    assert uvicorn_log_level() == "critical"
