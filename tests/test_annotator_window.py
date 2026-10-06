"""Save/autosave/restore behavior of the real annotator window, run offscreen.

Dialogs are replaced with scripted answers so nothing blocks; the video file is an
empty placeholder, which only makes the media player report an error.
"""
import json
import csv
import os
import shutil

import pytest

pytest.importorskip("PySide6.QtMultimedia")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from src.core.project import AUTOSAVE_OF_KEY  # noqa: E402
from src.ui.annotator_window import VideoAnnotator  # noqa: E402

SRT = "1\n00:00:01,000 --> 00:00:02,000\nHello\n\n2\n00:00:03,000 --> 00:00:04,000\nWorld\n"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def answers(monkeypatch):
    """Scripted dialog answers; tests set answers['question'] etc. as needed."""
    script = {"question": QMessageBox.No, "save_path": ""}
    shown = []
    for name in ("critical", "warning", "information"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, _n=name, **k: shown.append((_n, a[2] if len(a) > 2 else ""))))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: script["question"]))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (script["save_path"], "")))
    script["shown"] = shown
    return script


@pytest.fixture
def media(tmp_path):
    (tmp_path / "ep1.srt").write_text(SRT, encoding="utf-8")
    (tmp_path / "ep1.mp4").write_bytes(b"")
    (tmp_path / "chars.txt").write_text("Sheldon,1\nPenny,2\n", encoding="utf-8")
    return tmp_path


def _saved_project(media):
    vat = media / "study.vat"
    vat.write_text(json.dumps({
        "video_file": "ep1.mp4", "srt_file": "ep1.srt", "char_file": "chars.txt",
        "characters": [{"name": "Sheldon", "key": "1"}], "custom_columns": ["Note"],
        "annotations": {},
    }), encoding="utf-8")
    return vat


def _open(vat="", media=None):
    if vat:
        return VideoAnnotator("", "", "", str(vat))
    return VideoAnnotator(str(media / "ep1.mp4"), str(media / "ep1.srt"), str(media / "chars.txt"), "")


def _code_current_line(window, speaker="Sheldon"):
    window.current_speakers = [speaker]
    window.is_dirty = True


def _close(window):
    window.close()
    window.deleteLater()


def test_autosave_never_touches_the_project_file(qapp, answers, media):
    vat = _saved_project(media)
    before = vat.read_text(encoding="utf-8")
    window = _open(vat)
    _code_current_line(window)

    window.autosave_annotations()

    autosave = media / ".study.vat.autosave.vat"
    assert vat.read_text(encoding="utf-8") == before
    data = json.loads(autosave.read_text(encoding="utf-8"))
    assert data[AUTOSAVE_OF_KEY] == str(vat.absolute())
    assert data["annotations"]["0"]["speakers"] == ["Sheldon"]
    window.is_dirty = False
    _close(window)


def test_saving_writes_the_project_and_removes_the_autosave(qapp, answers, media):
    vat = _saved_project(media)
    window = _open(vat)
    _code_current_line(window)
    window.autosave_annotations()

    assert window.save_project() is True

    assert json.loads(vat.read_text(encoding="utf-8"))["annotations"]["0"]["speakers"] == ["Sheldon"]
    assert not (media / ".study.vat.autosave.vat").exists()
    assert window.is_dirty is False
    _close(window)


def test_declining_to_save_on_close_discards_changes_and_autosave(qapp, answers, media):
    vat = _saved_project(media)
    before = vat.read_text(encoding="utf-8")
    window = _open(vat)
    _code_current_line(window)
    window.autosave_annotations()
    answers["question"] = QMessageBox.No

    assert window.close() is True

    assert vat.read_text(encoding="utf-8") == before
    assert not (media / ".study.vat.autosave.vat").exists()


def test_cancelling_close_keeps_the_window_and_autosave(qapp, answers, media):
    window = _open(media=media)
    _code_current_line(window)
    window.autosave_annotations()
    answers["question"] = QMessageBox.Cancel

    assert window.close() is False
    assert (media / ".ep1.srt.autosave.vat").exists()
    window.is_dirty = False
    _close(window)


def test_failed_save_as_keeps_the_window_open(qapp, answers, media):
    window = _open(media=media)
    _code_current_line(window)
    answers["question"] = QMessageBox.Yes
    answers["save_path"] = ""  # user cancels the Save As dialog

    assert window.close() is False
    window.is_dirty = False
    _close(window)


def test_recovered_session_saves_to_its_project_not_the_autosave(qapp, answers, media):
    vat = _saved_project(media)
    window = _open(vat)
    _code_current_line(window)
    window.autosave_annotations()
    window.is_dirty = False  # simulate a crash: the window never got to save
    window.deleteLater()
    autosave = media / ".study.vat.autosave.vat"

    recovered = _open(autosave)

    assert recovered.vat_file == str(vat.absolute())
    assert recovered.is_dirty is True
    assert recovered.annotations[0]["speakers"] == ["Sheldon"]
    assert recovered.save_project() is True
    assert json.loads(vat.read_text(encoding="utf-8"))["annotations"]["0"]["speakers"] == ["Sheldon"]
    assert not autosave.exists()
    _close(recovered)


def test_unsaved_session_autosave_sits_next_to_the_subtitles(qapp, answers, media):
    window = _open(media=media)
    _code_current_line(window)

    window.autosave_annotations()

    data = json.loads((media / ".ep1.srt.autosave.vat").read_text(encoding="utf-8"))
    assert data[AUTOSAVE_OF_KEY] == ""
    window.is_dirty = False
    _close(window)
    assert not (media / ".ep1.srt.autosave.vat").exists()


def test_character_names_with_commas_are_rejected(qapp, answers, media):
    window = _open(media=media)
    table = window.character_table
    new_row = len(window.characters)
    names_before = [c["name"] for c in window.characters]

    table.item(new_row, 0).setText("Cooper, Sheldon")

    assert [c["name"] for c in window.characters] == names_before
    assert any(kind == "warning" for kind, _ in answers["shown"])
    _close(window)


def test_autosave_copied_from_another_project_is_not_offered(qapp, answers, media, monkeypatch):
    original = _saved_project(media)
    window = _open(original)
    _code_current_line(window)
    window.autosave_annotations()
    window.is_dirty = False
    window.deleteLater()
    # Copy the project folder, hidden autosave included, then open the copy.
    copy_dir = media.parent / "copied_project"
    shutil.copytree(media, copy_dir)
    copy_vat = copy_dir / "study.vat"
    os.utime(copy_vat, (1000, 1000))
    offered = []
    answers["question"] = QMessageBox.Yes
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: offered.append(a[2]) or QMessageBox.Yes))

    copied = _open(copy_vat)
    requested = []
    copied.request_open_project.connect(requested.append)
    copied.try_restore_autosave()

    assert offered == [] and requested == []
    copied.is_dirty = False
    _close(copied)


def test_opening_a_mismatched_autosave_never_targets_the_other_project(qapp, answers, media):
    original = _saved_project(media)
    window = _open(original)
    _code_current_line(window)
    window.autosave_annotations()
    window.is_dirty = False
    window.deleteLater()
    copy_dir = media.parent / "copied_project2"
    shutil.copytree(media, copy_dir)

    recovered = _open(copy_dir / ".study.vat.autosave.vat")

    assert recovered.vat_file == ""  # unsaved: Save asks where, instead of writing the original
    recovered.is_dirty = False
    _close(recovered)


def test_csv_export_has_original_numeric_subtitle_position_and_round_trips(qapp, answers, media):
    window = _open(media=media)
    window.annotations = {1: {'speakers': ['Sheldon'], 'listeners': ['Penny'], 'targets': ['Penny'], 'Note': 'greeting'}}
    path = media / 'annotations.csv'
    window.export_csv(str(path))
    with path.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]['position'] == '2'
    assert rows[0]['start_time'] == '00:00:03,000'
    window.import_csv(str(path))
    assert 'position' not in window.custom_columns
    assert window.annotations[1]['speakers'] == ['Sheldon']
    assert window.annotations[1]['listeners'] == ['Penny']
    assert window.annotations[1]['Note'] == 'greeting'
    window.is_dirty = False
    _close(window)


def test_empty_csv_export_keeps_the_same_schema(qapp, answers, media):
    window = _open(media=media)
    path = media / 'empty.csv'
    window.export_csv(str(path))
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ['line', 'position', 'start_time', 'end_time', 'speakers', 'listeners', 'targets', 'Note']
        assert list(reader) == []
    _close(window)


def test_repeated_csv_import_does_not_duplicate_edit_callbacks(qapp, answers, media, monkeypatch):
    edits = []
    original = VideoAnnotator.on_subtitle_item_changed

    def record_edit(self, item):
        if not self._updating_table and item.column() >= 7:
            edits.append((item.row(), item.column()))
        return original(self, item)

    monkeypatch.setattr(VideoAnnotator, 'on_subtitle_item_changed', record_edit)
    window = _open(media=media)
    path = media / 'annotations.csv'
    window.annotations = {1: {'speakers': ['Sheldon'], 'listeners': ['Penny'], 'Note': 'greeting'}}
    window.export_csv(str(path))
    window.import_csv(str(path))
    window.import_csv(str(path))
    assert edits == []
    assert not window.subtitle_list.signalsBlocked()
    window.subtitle_list.item(1, 7).setText('updated')
    assert edits == [(1, 7)]
    assert window.annotations[1]['Note'] == 'updated'
    assert window.annotations[1]['note'] == 'updated'
    window.is_dirty = False
    _close(window)


def test_failed_csv_import_restores_table_edit_signals(qapp, answers, media):
    window = _open(media=media)
    window.import_csv(str(media / 'missing.csv'))
    assert not window.subtitle_list.signalsBlocked()
    window.subtitle_list.item(0, 7).setText('still editable')
    assert window.annotations[0]['Note'] == 'still editable'
    window.is_dirty = False
    _close(window)
