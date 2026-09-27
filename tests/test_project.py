import json
import os
from pathlib import Path

import pytest

from src.core import project


def test_autosave_of_an_unsaved_session_sits_next_to_the_subtitles(tmp_path):
    srt = tmp_path / "ep1.srt"

    assert Path(project.autosave_path_for("", str(srt))) == tmp_path / ".ep1.srt.autosave.vat"


def test_autosave_of_a_saved_project_sits_next_to_the_project(tmp_path):
    vat = tmp_path / "work" / "study.vat"

    path = project.autosave_path_for(str(vat), str(tmp_path / "ep1.srt"))

    assert Path(path) == tmp_path / "work" / ".study.vat.autosave.vat"
    assert Path(path) != vat


def test_write_then_read_round_trips(tmp_path):
    target = tmp_path / "nested" / "p.vat"
    data = {"annotations": {"0": {"speakers": ["A"]}}, "characters": []}

    project.write_project_file(str(target), data)

    assert project.read_project_file(str(target)) == data


def test_failed_write_keeps_the_previous_file_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "p.vat"
    project.write_project_file(str(target), {"version": 1})

    with pytest.raises(TypeError):
        project.write_project_file(str(target), {"bad": object()})

    assert json.loads(target.read_text(encoding="utf-8")) == {"version": 1}
    assert sorted(os.listdir(tmp_path)) == ["p.vat"]


def test_autosave_newer_than_project(tmp_path):
    vat, autosave = tmp_path / "p.vat", tmp_path / ".p.vat.autosave.vat"
    vat.write_text("{}")
    autosave.write_text("{}")
    os.utime(vat, (1000, 1000))
    os.utime(autosave, (2000, 2000))

    assert project.autosave_is_recoverable(str(autosave), str(vat))
    assert not project.autosave_is_recoverable(str(vat), str(autosave))


def test_autosave_without_a_project_is_recoverable(tmp_path):
    autosave = tmp_path / ".ep1.srt.autosave.vat"
    autosave.write_text("{}")

    assert project.autosave_is_recoverable(str(autosave), "")
    assert not project.autosave_is_recoverable(str(tmp_path / "missing"), "")


def test_remove_file_quietly(tmp_path):
    path = tmp_path / "x"
    path.write_text("x")

    project.remove_file_quietly(str(path))
    project.remove_file_quietly(str(path))

    assert not path.exists()


def test_recovery_target_accepts_matching_metadata(tmp_path):
    vat = tmp_path / "study.vat"
    srt = tmp_path / "ep1.srt"
    autosave = project.autosave_path_for(str(vat), str(srt))

    assert project.recovery_target(autosave, {project.AUTOSAVE_OF_KEY: str(vat)}, str(srt)) == str(vat)


def test_recovery_target_accepts_an_unsaved_session(tmp_path):
    srt = tmp_path / "ep1.srt"
    autosave = project.autosave_path_for("", str(srt))

    assert project.recovery_target(autosave, {project.AUTOSAVE_OF_KEY: ""}, str(srt)) == ""


def test_recovery_target_rejects_an_autosave_pointing_at_another_project(tmp_path):
    # A copied project folder carries an autosave whose metadata still names the
    # original project; saving there would overwrite the wrong project.
    original = tmp_path / "original" / "study.vat"
    copy = tmp_path / "copy" / "study.vat"
    srt = tmp_path / "copy" / "ep1.srt"
    autosave_in_copy = project.autosave_path_for(str(copy), str(srt))

    assert project.recovery_target(autosave_in_copy, {project.AUTOSAVE_OF_KEY: str(original)}, str(srt)) is None


@pytest.mark.parametrize("data", [{}, {project.AUTOSAVE_OF_KEY: None}, {project.AUTOSAVE_OF_KEY: 3}, []])
def test_recovery_target_rejects_malformed_metadata(tmp_path, data):
    srt = tmp_path / "ep1.srt"

    assert project.recovery_target(project.autosave_path_for("", str(srt)), data, str(srt)) is None
