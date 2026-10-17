import pytest

from helpers import env_config
from helpers.env_config import get_base_url


@pytest.mark.parametrize("api_name", sorted(env_config._API_URLS))
def test_get_base_url_defaults_without_override(monkeypatch, api_name):
    monkeypatch.delenv(env_config._ENV_OVERRIDES[api_name], raising=False)
    assert get_base_url(api_name) == env_config._API_URLS[api_name]


def test_get_base_url_honours_override(monkeypatch):
    api_name = next(iter(env_config._API_URLS))
    monkeypatch.setenv(env_config._ENV_OVERRIDES[api_name], "https://espejo.example/api")
    assert get_base_url(api_name) == "https://espejo.example/api"


def test_get_base_url_falls_back_when_override_is_empty(monkeypatch):
    # A compose file with `VAR=${UNSET}` renders the variable present but
    # empty; that must not turn the base URL into "".
    api_name = next(iter(env_config._API_URLS))
    monkeypatch.setenv(env_config._ENV_OVERRIDES[api_name], "")
    assert get_base_url(api_name) == env_config._API_URLS[api_name]


def test_get_base_url_rejects_unknown_api():
    with pytest.raises(KeyError):
        get_base_url("no-existe")
