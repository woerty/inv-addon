from __future__ import annotations

from pathlib import Path

from app.config import Settings, get_settings
from app.services.picnic.client import _token_path


def test_token_path_default_is_data_dir():
    # The field default must stay /data so production (HA addon) is unaffected.
    # Checked .env-independently via the field default, not get_settings().
    assert Settings.model_fields["picnic_token_path"].default == "/data/picnic_token.json"


def test_token_path_honors_env_override(monkeypatch, tmp_path):
    target = tmp_path / ".picnic_token.json"
    monkeypatch.setenv("PICNIC_TOKEN_PATH", str(target))
    get_settings.cache_clear()
    try:
        assert _token_path() == target
    finally:
        get_settings.cache_clear()
