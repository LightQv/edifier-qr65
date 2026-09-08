import pytest


@pytest.fixture
def xdg_dirs(tmp_path, monkeypatch: pytest.MonkeyPatch):
    config = tmp_path / "config"
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    return config, state
