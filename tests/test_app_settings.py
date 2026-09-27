import json

import pytest

import src.core.app_settings as app_settings


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(app_settings, "SETTINGS_FILE", str(path))
    return path


def test_rebinding_a_hotkey_leaves_the_defaults_untouched(settings_file):
    settings = app_settings.AppSettings()

    settings.set_hotkey("play_pause", "P")

    assert settings.get_hotkey("play_pause") == "P"
    assert app_settings.DEFAULT_SETTINGS["hotkeys"]["play_pause"] == "Space"


def test_loading_a_settings_file_leaves_the_defaults_untouched(settings_file):
    settings_file.write_text(json.dumps({"auto_pause": False, "hotkeys": {"next_uncoded": "M"}}), encoding="utf-8")

    settings = app_settings.AppSettings()

    assert settings.get("auto_pause") is False
    assert settings.get_hotkey("next_uncoded") == "M"
    assert settings.get_hotkey("play_pause") == "Space"
    assert app_settings.DEFAULT_SETTINGS["hotkeys"]["next_uncoded"] == "N"
    assert app_settings.DEFAULT_SETTINGS["auto_pause"] is True


def test_settings_persist_between_instances(settings_file):
    app_settings.AppSettings().set("inherit_listener", True)

    assert app_settings.AppSettings().get("inherit_listener") is True
