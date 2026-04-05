"""Regression tests for Settings loading, especially the HA addon path.

These tests guard against silent breakage when validation_alias is combined
with populate_by_name. Without populate_by_name=True, aliased fields become
EXCLUSIVE: explicit kwargs passed to the constructor get ignored and the
field falls back to its default, breaking Settings.from_ha_options() which
passes kwargs by field name.
"""
import json

import pytest

from app.config import Settings


def _isolate_env(monkeypatch, tmp_path):
    """Strip Picnic env vars and isolate cwd so no .env file is picked up."""
    for key in ("PICNIC_MAIL", "PICNIC_EMAIL", "PICNIC_PASSWORD", "PICNIC_COUNTRY_CODE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)


def test_explicit_picnic_email_kwarg_is_respected(monkeypatch, tmp_path):
    """The HA addon path passes picnic_email by field name to Settings(...);
    without populate_by_name=True this was silently ignored."""
    _isolate_env(monkeypatch, tmp_path)

    s = Settings(
        picnic_email="user@example.com",
        picnic_password="secret",
    )

    assert s.picnic_email == "user@example.com"
    assert s.picnic_password == "secret"


def test_from_ha_options_reads_credentials(monkeypatch, tmp_path):
    """End-to-end: simulate /data/options.json, call Settings.from_ha_options()."""
    _isolate_env(monkeypatch, tmp_path)

    options_file = tmp_path / "options.json"
    options_file.write_text(
        json.dumps(
            {
                "anthropic_api_key": "anthropic-key",
                "openai_api_key": "openai-key",
                "picnic_email": "ha@example.com",
                "picnic_password": "ha-secret",
                "picnic_country_code": "DE",
            }
        )
    )

    s = Settings.from_ha_options(options_path=options_file)

    assert s.picnic_email == "ha@example.com"
    assert s.picnic_password == "ha-secret"
    assert s.anthropic_api_key == "anthropic-key"
    assert s.openai_api_key == "openai-key"
    assert s.picnic_country_code == "DE"


def test_from_ha_options_accepts_legacy_picnic_mail_key(monkeypatch, tmp_path):
    """Older users may still have picnic_mail (the legacy key); from_ha_options
    should fall back to it when picnic_email is absent."""
    _isolate_env(monkeypatch, tmp_path)

    options_file = tmp_path / "options.json"
    options_file.write_text(
        json.dumps({"picnic_mail": "legacy@example.com", "picnic_password": "pw"})
    )

    s = Settings.from_ha_options(options_path=options_file)

    assert s.picnic_email == "legacy@example.com"
    assert s.picnic_password == "pw"


def test_env_var_alias_still_works(monkeypatch, tmp_path):
    """populate_by_name must not break the existing PICNIC_MAIL env var alias."""
    _isolate_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PICNIC_MAIL", "env@example.com")
    monkeypatch.setenv("PICNIC_PASSWORD", "env-secret")

    s = Settings()

    assert s.picnic_email == "env@example.com"
    assert s.picnic_password == "env-secret"


def test_picnic_email_env_var_alias_also_works(monkeypatch, tmp_path):
    """PICNIC_EMAIL (the canonical name) should work alongside PICNIC_MAIL."""
    _isolate_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PICNIC_EMAIL", "canonical@example.com")
    monkeypatch.setenv("PICNIC_PASSWORD", "pw")

    s = Settings()

    assert s.picnic_email == "canonical@example.com"


def test_missing_credentials_default_to_empty(monkeypatch, tmp_path):
    _isolate_env(monkeypatch, tmp_path)

    s = Settings()

    assert s.picnic_email == ""
    assert s.picnic_password == ""
