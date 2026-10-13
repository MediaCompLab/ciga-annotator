"""Save/autosave/restore behavior of the real annotator window, run offscreen.

Dialogs are replaced with scripted answers so nothing blocks. Media decoding is
disabled: these tests exercise project storage and widget input, not video codecs.
"""
import json
import csv
import os
import shutil
from copy import deepcopy

import pytest

pytest.importorskip("PySide6.QtMultimedia")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402
from PySide6.QtCore import Qt, QCoreApplication, QEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

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
    from PySide6.QtMultimedia import QMediaPlayer
    monkeypatch.setattr(QMediaPlayer, 'setSource', lambda *args: None)
    monkeypatch.setattr(QMediaPlayer, 'play', lambda *args: None)
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


@pytest.fixture
def coding_window(qapp, answers, media):
    window = _open(media=media)
    window.show()
    window.activateWindow()
    QTest.qWait(20)
    qapp.installEventFilter(window)
    yield window
    qapp.removeEventFilter(window)
    window.is_dirty = False
    _close(window)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _character_focus(window):
    focused = QApplication.focusWidget()
    return focused is window.character_table or (
        focused is not None and window.character_table.isAncestorOf(focused)
    )


def _edit_new_character(window):
    window.character_table.setFocus()
    window.focus_new_character_row()
    QApplication.processEvents()
    editor = QApplication.focusWidget()
    assert editor is not None and window.character_table.isAncestorOf(editor)
    return editor


def test_focus_video_click_exits_character_table_and_restores_coding(coding_window):
    window = coding_window
    window.right_tabs.setCurrentIndex(1)
    window.character_table.setCurrentCell(0, 0)
    window.character_table.setFocus()
    assert _character_focus(window)

    QTest.mouseClick(window.videoWidget, Qt.LeftButton)
    QTest.qWait(20)
    assert not _character_focus(window)
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_2, Qt.ControlModifier)
    assert window.active_role == 'listeners'
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_1, Qt.AltModifier)
    assert window.current_listeners == ['Sheldon']
    assert window.annotations[0]['listeners'] == ['Sheldon']


def test_focus_video_click_commits_name_without_queued_editor_stealing_focus(coding_window):
    window = coding_window
    editor = _edit_new_character(window)
    QTest.keyClicks(editor, 'Nate')
    assert window.current_subtitle_index == 0  # N must type into the editor.

    QTest.mouseClick(window.videoWidget, Qt.LeftButton)
    QTest.qWait(20)  # Allow the next-character timer to run.
    assert window.characters[-1]['name'] == 'Nate'
    assert not _character_focus(window)
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_3, Qt.AltModifier)
    assert window.current_speakers == ['Nate']


def test_focus_enter_keeps_bulk_character_entry_available(coding_window):
    window = coding_window
    editor = _edit_new_character(window)
    QTest.keyClicks(editor, 'Nate')
    QTest.keyClick(editor, Qt.Key_Return)
    QTest.qWait(20)
    assert window.characters[-1]['name'] == 'Nate'
    assert _character_focus(window)
    assert window.character_table.currentRow() == len(window.characters)


@pytest.mark.parametrize('field', ['speaker_summary', 'listener_summary', 'target_summary'])
def test_focus_readonly_role_panels_allow_coding_shortcuts(coding_window, field):
    window = coding_window
    summary = getattr(window, field)
    QTest.mouseClick(summary, Qt.LeftButton)
    assert QApplication.focusWidget() is summary
    QTest.keyClick(summary, Qt.Key_2, Qt.ControlModifier)
    assert window.active_role == 'listeners'
    QTest.keyClick(summary, Qt.Key_1, Qt.AltModifier)
    assert window.current_listeners == ['Sheldon']


@pytest.mark.parametrize('field', ['note_edit', 'search_edit'])
def test_focus_writable_fields_keep_text_input(coding_window, field):
    window = coding_window
    editor = getattr(window, field)
    editor.setFocus()
    QTest.keyClicks(editor, 'N')
    assert editor.text() == 'N'
    assert window.current_subtitle_index == 0
    QTest.keyClick(editor, Qt.Key_1, Qt.AltModifier)
    assert window.current_speakers == []


def test_real_keyboard_coding_marks_dirty_refreshes_row_and_autosaves(coding_window):
    window = coding_window
    window.videoWidget.setFocus()
    QTest.keyClick(window.videoWidget, Qt.Key_1, Qt.AltModifier)
    assert window.is_dirty
    assert window.subtitle_list.item(0, 4).text() == 'Sheldon'
    window.autosave_annotations()
    recovery = json.loads(open(window.autosave_path, encoding='utf-8').read())
    assert recovery['annotations']['0']['speakers'] == ['Sheldon']


def test_note_panel_changes_mark_dirty_and_update_note_export(coding_window, media):
    window = coding_window
    window.note_edit.setText('original')
    window.note_edit.setText('updated')
    assert window.is_dirty
    assert window.annotations[0]['Note'] == 'updated'
    assert window.subtitle_list.item(0, 7).text() == 'updated'
    path = media / 'notes.csv'
    window.export_csv(str(path))
    with path.open(encoding='utf-8-sig', newline='') as stream:
        assert list(csv.DictReader(stream))[0]['Note'] == 'updated'
    assert window.is_dirty


def test_csv_export_preserves_unsaved_project_changes(qapp, answers, media):
    vat = _saved_project(media)
    window = _open(vat)
    before = vat.read_bytes()
    window.current_speakers = ['Sheldon']
    window.record_annotation(0, clear_selections=False)
    window.export_csv(str(media / 'export.csv'))
    assert window.is_dirty
    assert vat.read_bytes() == before
    window.is_dirty = False
    _close(window)


def test_character_rename_updates_all_roles_and_existing_units(qapp, answers, media):
    window = _open(media=media)
    window.annotations = {0: {'speakers': ['Sheldon'], 'listeners': ['Penny'], 'targets': ['Sheldon']},
                          1: {'speakers': ['Penny'], 'listeners': ['Sheldon'], 'targets': []}}
    window.current_speakers = ['Sheldon']
    window.character_table.item(0, 0).setText('Sheldon Cooper')
    assert window.annotations[0]['speakers'] == ['Sheldon Cooper']
    assert window.annotations[0]['targets'] == ['Sheldon Cooper']
    assert window.annotations[1]['listeners'] == ['Sheldon Cooper']
    assert window.current_speakers == ['Sheldon Cooper']
    assert window.subtitle_list.item(1, 5).text() == 'Sheldon Cooper'
    window.is_dirty = False
    _close(window)


def test_mouse_coding_and_configured_confirmation(coding_window):
    window = coding_window
    QTest.mouseClick(window.role_buttons['listeners'], Qt.LeftButton)
    assert window.active_role == 'listeners'
    item = window.coding_characters.item(0)
    rect = window.coding_characters.visualItemRect(item)
    from PySide6.QtCore import QPoint
    QTest.mouseClick(window.coding_characters.viewport(), Qt.LeftButton, pos=QPoint(rect.left() + 8, rect.center().y()))
    assert window.annotations[0]['listeners'] == ['Sheldon']
    assert window.is_dirty
    assert window.get_annotation_status(0) == 'Needs check'
    assert not window.set_review_state('confirmed')
    window.apply_research_settings({'coder_id': 'coder-A', 'codebook_version': 'v1',
                                    'required_roles': ['speakers', 'listeners']})
    QTest.mouseClick(window.na_checks['speakers'], Qt.LeftButton)
    assert window.confirm_btn.isEnabled()
    window.right_tabs.setCurrentWidget(window.review_widget)
    QTest.mouseClick(window.confirm_btn, Qt.LeftButton)
    assert window.annotations[0]['review_state'] == 'confirmed'
    assert window.annotations[0]['confirmation']['coder_id'] == 'coder-A'
    assert window.current_subtitle_index == 1


def test_coding_edit_reopens_confirmation_and_undo_restores_it(coding_window):
    window = coding_window
    window.apply_research_settings({'required_roles': ['speakers']})
    window._toggle_role_name('speakers', 'Sheldon')
    window.record_annotation(0, False)
    assert window.set_review_state('confirmed')
    window._toggle_role_name('speakers', 'Penny')
    window.record_annotation(0, False)
    assert window.annotations[0]['review_state'] == 'needs_review'
    window.undo_coding()
    assert window.annotations[0]['review_state'] == 'confirmed'
    assert window.current_speakers == ['Sheldon']
    window.redo_coding()
    assert window.annotations[0]['review_state'] == 'needs_review'
    assert window.current_speakers == ['Sheldon', 'Penny']
    assert window.audit_log[-1]['action'].startswith('Redo')


def test_rule_change_invalidates_confirmation_but_coder_change_does_not(coding_window):
    window = coding_window
    window.apply_research_settings({'required_roles': []})
    assert window.set_review_state('confirmed')
    study = deepcopy(window.study)
    study['coder_id'] = 'B'
    window.apply_research_settings(study)
    assert window.annotations[0]['review_state'] == 'confirmed'
    study['definitions']['listeners'] = 'Study-specific listener definition'
    window.apply_research_settings(study)
    assert window.annotations[0]['review_state'] == 'needs_review'
    assert not window.history.undo_entries


def test_full_csv_preserves_states_and_confirmed_export_excludes_review(coding_window, media):
    window = coding_window
    window.apply_research_settings({'required_roles': []})
    window.set_not_applicable('speakers', True)
    assert window.set_review_state('confirmed')
    window.jump_to_subtitle(1)
    window.set_review_state('needs_review')
    analysis = media / 'analysis.csv'
    window.export_csv(str(analysis), confirmed_only=True)
    with analysis.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1 and rows[0]['position'] == '1'
    full = media / 'full.csv'
    window.export_csv(str(full), include_metadata=True)
    assert window.import_csv(str(full))
    assert window.annotations[0]['review_state'] == 'confirmed'
    assert window.annotations[0]['not_applicable'] == ['speakers']
    assert window.annotations[1]['review_state'] == 'needs_review'
    assert 'review_state' not in window.custom_columns


def test_failed_csv_import_preserves_all_existing_coding(coding_window, media):
    window = coding_window
    window.note_edit.setText('Important observation')
    before = deepcopy(window.annotations)
    path = media / 'wrong.csv'
    path.write_text('start_time,end_time,speakers\n00:10:00,000,00:10:01,000,Alice\n', encoding='utf-8')
    assert not window.import_csv(str(path))
    assert window.annotations == before
    assert not window.subtitle_list.signalsBlocked()


def test_character_identity_and_audit_survive_save_and_rename(qapp, answers, media):
    window = _open(media=media)
    identity = window.characters[0]['id']
    template_before = (media / 'chars.txt').read_bytes()
    window.current_speakers = ['Sheldon']
    window.record_annotation(0, False)
    window.character_table.item(0, 0).setText('Sheldon Cooper')
    assert window.characters[0]['id'] == identity
    assert window.annotations[0]['speakers_ids'] == [identity]
    assert (media / 'chars.txt').read_bytes() == template_before
    vat = media / 'research.vat'
    assert window._save_to(str(vat))
    _close(window)
    restored = _open(vat)
    assert restored.characters[0]['id'] == identity
    assert restored.characters[0]['aliases'] == ['Sheldon']
    assert restored.annotations[0]['speakers'] == ['Sheldon Cooper']
    assert any(event['action'] == 'Rename character' for event in restored.audit_log)
    assert restored.material['unit_ids'][0]
    _close(restored)


def test_referenced_character_cannot_be_deleted(coding_window, answers):
    window = coding_window
    window.current_speakers = ['Sheldon']
    window.record_annotation(0, False)
    window.character_table.selectRow(0)
    answers['question'] = QMessageBox.Yes
    window.delete_selected_character()
    assert window.characters[0]['name'] == 'Sheldon'
    assert 'referenced by 1' in answers['shown'][-1][1]


def test_pasted_setup_paths_are_used_and_invalid_path_disables_start(qapp, media):
    from src.ui.setup_window import MainWindow
    window = MainWindow()
    emitted = []
    window.start_annotation.connect(lambda *paths: emitted.append(paths))
    window.video_path_edit.setText(str(media / 'ep1.mp4'))
    window.srt_path_edit.setText(str(media / 'ep1.srt'))
    assert window.start_button.isEnabled()
    window.start_annotation_clicked()
    assert emitted[0][:2] == (str(media / 'ep1.mp4'), str(media / 'ep1.srt'))
    window.video_path_edit.clear()
    assert not window.start_button.isEnabled()
    window.close()


def test_adjudication_records_other_coder_and_requires_confirmation(coding_window):
    window = coding_window
    window.resolve_comparison(0, {'speakers': ['Penny']}, 'coder-b.vat', 'B', True)
    assert window.current_speakers == ['Penny']
    assert window.annotations[0]['review_state'] == 'needs_review'
    assert window.audit_log[-1]['source_coder'] == 'B'
    assert window.audit_log[-1]['decision'] == 'use_other'
    window.undo_coding()
    assert not window.annotations.get(0)


def test_end_of_last_subtitle_does_not_clear_coding(coding_window):
    window = coding_window
    window.jump_to_subtitle(1)
    window.current_speakers = ['Penny']
    window.record_annotation(1, False)
    window.paused_at_subtitle_end = True
    window.handle_spacebar()
    window.record_annotation(1, False)
    assert window.annotations[1]['speakers'] == ['Penny']
    assert window.current_speakers == ['Penny']


def test_inherited_suggestions_are_visible_and_can_be_undone(coding_window):
    window = coding_window
    window.current_listeners = ['Penny']
    window.record_annotation(0, False)
    window.app_settings.settings['inherit_listener'] = True
    window.jump_to_subtitle(1)
    assert window.annotations[1]['listeners'] == ['Penny']
    assert window.annotations[1]['review_state'] == 'in_progress'
    assert 'Inherited suggestions' in window.review_label.text()
    window.undo_coding()
    assert not window.annotations.get(1)
    assert window.current_listeners == []


def test_changed_material_is_rejected_without_writing_project(qapp, answers, media):
    window = _open(media=media)
    vat = media / 'research.vat'
    window._save_to(str(vat))
    _close(window)
    original = vat.read_bytes()
    (media / 'ep1.srt').write_text(SRT.replace('Hello', 'Changed'), encoding='utf-8')
    rejected = _open(vat)
    assert not rejected.ready
    assert vat.read_bytes() == original
    assert 'subtitles differ' in answers['shown'][-1][1]
    assert rejected.close()


def test_duplicate_character_name_is_rejected(coding_window, answers):
    window = coding_window
    window.character_table.item(0, 0).setText('Penny')
    assert window.characters[0]['name'] == 'Sheldon'
    assert 'already exists' in answers['shown'][-1][1]


def test_material_and_history_dialog_shows_audit_entries(coding_window):
    from src.ui.research_dialogs import ProjectHistoryDialog
    from PySide6.QtWidgets import QTableWidget, QTextEdit
    window = coding_window
    window.current_speakers = ['Penny']
    window.record_annotation(0, False)
    dialog = ProjectHistoryDialog(window)
    table = dialog.findChild(QTableWidget)
    assert table.rowCount() == 1
    table.setCurrentCell(0, 0)
    assert 'Edit coding' in dialog.findChild(QTextEdit).toPlainText()
    dialog.close()


def test_compare_checks_actual_video_content_before_showing_differences(coding_window, media, monkeypatch, answers):
    window = coding_window
    other = deepcopy(window._project_data(str(media / 'other.vat')))
    other['video_file'] = 'different.mp4'
    (media / 'different.mp4').write_bytes(b'different video')
    path = media / 'other.vat'
    path.write_text(json.dumps(other), encoding='utf-8')
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', staticmethod(lambda *args: (str(path), '')))
    before = deepcopy(window.annotations)
    window.compare_project_dialog()
    assert window.annotations == before
    assert 'Video content differs' in answers['shown'][-1][1]


def test_comparison_dialog_resolves_selected_difference(coding_window):
    from src.ui.research_dialogs import ComparisonDialog
    window = coding_window
    dialog = ComparisonDialog(window, [(0, {}, {'speakers': ['Penny']})], 'b.vat', 'B')
    dialog.resolve(True)
    assert window.annotations[0]['speakers'] == ['Penny']
    assert window.annotations[0]['review_state'] == 'needs_review'
    assert dialog.table.rowCount() == 0
    dialog.close()


def test_customizable_hotkey_conflicts_are_blocked(qapp, tmp_path, monkeypatch):
    from src.core.app_settings import AppSettings
    from src.ui.settings_dialog import SettingsDialog
    from PySide6.QtGui import QKeySequence
    import src.core.app_settings as module
    monkeypatch.setattr(module, 'SETTINGS_FILE', str(tmp_path / 'settings.json'))
    settings = AppSettings()
    dialog = SettingsDialog(None, settings)
    dialog.shortcut_edits['next_uncoded'].setKeySequence(QKeySequence('Ctrl+S'))
    shown = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: shown.append(args[2]))
    dialog.save_settings()
    assert shown
    assert settings.get_hotkey('next_uncoded') == 'N'
    assert not (tmp_path / 'settings.json').exists()
    dialog.close()


def test_failed_import_with_ambiguous_character_names_preserves_registry(coding_window, media):
    window = coding_window
    before = deepcopy(window.characters)
    annotations = deepcopy(window.annotations)
    path = media / 'ambiguous-names.csv'
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['start_time', 'end_time', 'speakers'])
        writer.writeheader()
        writer.writerow({'start_time': '00:00:01,000', 'end_time': '00:00:02,000', 'speakers': 'New character'})
        writer.writerow({'start_time': '00:00:03,000', 'end_time': '00:00:04,000', 'speakers': 'PENNY'})
    assert not window.import_csv(str(path))
    assert window.characters == before
    assert window.annotations == annotations


def test_original_keyboard_sequence_advances_without_review_or_extra_keys(coding_window):
    window = coding_window
    window.videoWidget.setFocus()
    assert not window.confirm_btn.isVisible()
    assert not window.review_label.isVisible()
    # Original workflow: select a speaker, then Space at the subtitle boundary.
    QTest.keyClick(window.videoWidget, Qt.Key_1, Qt.AltModifier)
    assert window.get_annotation_status(0) == 'Needs check'  # Two required roles missing.
    assert window.annotations[0]['review_state'] == 'in_progress'
    window.paused_at_subtitle_end = True
    QTest.keyClick(window.videoWidget, Qt.Key_Space)
    assert window.current_subtitle_index == 1
    assert window.right_tabs.currentIndex() == 0
    QTest.keyClick(window.videoWidget, Qt.Key_2, Qt.AltModifier)
    window.paused_at_subtitle_end = True
    QTest.keyClick(window.videoWidget, Qt.Key_Space)
    assert window.annotations[0]['speakers'] == ['Sheldon']
    assert window.annotations[1]['speakers'] == ['Penny']
    assert all('confirmation' not in annotation for annotation in window.annotations.values())
    assert 'Coded 2/2' in window.progress_label.text()
    assert 'Reviewed 0/2' in window.progress_label.text()
    # N no longer loops through the written but unreviewed lines.
    QTest.keyClick(window.videoWidget, Qt.Key_N)
    assert window.current_subtitle_index == 1
    assert 'No uncoded unit remains' in window.statusBar().currentMessage()


def test_n_skips_written_and_flagged_units_and_finds_uncoded(qapp, answers, media):
    (media / 'ep1.srt').write_text(SRT + '\n3\n00:00:05,000 --> 00:00:06,000\nThird\n', encoding='utf-8')
    window = _open(media=media)
    window.show()
    qapp.installEventFilter(window)
    try:
        window.current_speakers = ['Sheldon']
        window.record_annotation(0, False)
        window.commit_annotation(1, {'speakers': ['Penny'], 'review_state': 'needs_review'}, invalidate=False)
        window.videoWidget.setFocus()
        QTest.keyClick(window.videoWidget, Qt.Key_N)
        assert window.current_subtitle_index == 2
        assert window.annotations[0]['review_state'] == 'in_progress'
        assert window.annotations[1]['review_state'] == 'needs_review'
    finally:
        qapp.removeEventFilter(window)
        window.is_dirty = False
        _close(window)


def test_manual_review_uses_separate_queue_and_preserves_mode_when_watching(coding_window):
    window = coding_window
    window.apply_research_settings({'required_roles': ['speakers']})
    window.current_speakers = ['Sheldon']
    window.record_annotation(0, False)
    window.commit_annotation(1, {'speakers': ['Penny']})
    window.right_tabs.setCurrentWidget(window.review_widget)
    assert window.confirm_btn.isVisible()
    assert window.confirm_review_action.isEnabled()
    assert 'Speaker: Sheldon' in window.review_summary.toPlainText()
    QTest.mouseClick(window.videoWidget, Qt.LeftButton)
    assert window.is_review_mode()
    QTest.keyClick(window.videoWidget, Qt.Key_Return, Qt.ControlModifier)
    assert window.annotations[0]['review_state'] == 'confirmed'
    assert window.current_subtitle_index == 1  # Still coded, but waiting for review.
    assert window.is_review_mode()
    QTest.keyClick(window.videoWidget, Qt.Key_Return, Qt.ControlModifier)
    assert window.annotations[1]['review_state'] == 'confirmed'
    assert 'Reviewed 2/2' in window.progress_label.text()


def test_manual_approval_shortcut_is_disabled_during_coding(coding_window):
    window = coding_window
    window.apply_research_settings({'required_roles': ['speakers']})
    window.current_speakers = ['Sheldon']
    window.record_annotation(0, False)
    assert not window.confirm_review_action.isEnabled()
    window.videoWidget.setFocus()
    QTest.keyClick(window.videoWidget, Qt.Key_Return, Qt.ControlModifier)
    assert window.annotations[0]['review_state'] == 'in_progress'
    assert window.current_subtitle_index == 0


def test_review_queue_does_not_inherit_or_modify_uncoded_units(coding_window):
    window = coding_window
    window.current_listeners = ['Penny']
    window.record_annotation(0, False)
    window.app_settings.settings['inherit_listener'] = True
    window.videoWidget.setFocus()
    QTest.keyClick(window.videoWidget, Qt.Key_N, Qt.ControlModifier | Qt.ShiftModifier)
    assert window.is_review_mode()
    assert window.current_subtitle_index == 1
    assert window.current_listeners == []
    assert 1 not in window.annotations
    assert not window.confirm_btn.isEnabled()


def test_row_feedback_colors_all_columns_without_blocking_coding(coding_window):
    from PySide6.QtGui import QColor
    window = coding_window
    window.current_speakers = ['Sheldon']
    window.record_annotation(0, False)
    for column in range(window.subtitle_list.columnCount()):
        assert window.subtitle_list.item(0, column).background().color() == QColor(255, 193, 7, 65)
    assert 'Missing: Listener, Target' in window.subtitle_list.item(0, 3).toolTip()
    window.apply_research_settings({'required_roles': ['speakers']})
    assert window.get_annotation_status(0) == 'Unreviewed'
    assert window.subtitle_list.item(0, 3).background().color() == QColor(40, 120, 220, 40)
    assert window.set_review_state('confirmed')
    assert window.subtitle_list.item(0, 3).background().color() == QColor(40, 167, 69, 50)
    window._toggle_role_name('speakers', 'Penny')
    window.record_annotation(0, False)
    assert window.get_annotation_status(0) == 'Needs review'
    assert window.subtitle_list.item(0, 3).background().color() == QColor(255, 193, 7, 65)


def test_coding_and_review_filters_are_independent(coding_window):
    window = coding_window
    window.current_speakers = ['Sheldon']
    window.record_annotation(0, False)
    window.review_filter.setCurrentIndex(window.review_filter.findData('attention'))
    assert not window.subtitle_list.isRowHidden(0)
    assert window.subtitle_list.isRowHidden(1)
    window.review_filter.setCurrentIndex(0)
    window.app_settings.settings['only_uncoded'] = True
    window.apply_subtitle_filters()
    assert window.subtitle_list.isRowHidden(0)
    assert not window.subtitle_list.isRowHidden(1)


def test_separate_progress_stays_correct_after_review_undo_rules_and_exclusion(coding_window):
    window = coding_window
    window.current_speakers = ['Sheldon']
    window.record_annotation(0, False)
    assert 'Coded 1/2' in window.progress_label.text()
    assert 'Check 1' in window.progress_label.text()
    window.apply_research_settings({'required_roles': ['speakers']})
    assert 'Check 0' in window.progress_label.text()
    window.set_review_state('confirmed')
    assert 'Reviewed 1/2' in window.progress_label.text()
    window.undo_coding()
    assert 'Reviewed 0/2' in window.progress_label.text()
    window.redo_coding()
    assert 'Reviewed 1/2' in window.progress_label.text()
    window.set_review_state('excluded', 'Outside the research scope')
    assert 'Coded 0/1' in window.progress_label.text()
    assert 'Excluded 1' in window.progress_label.text()
    window.undo_coding()
    assert 'Coded 1/2' in window.progress_label.text()
    assert 'Reviewed 1/2' in window.progress_label.text()
    rules = deepcopy(window.study)
    rules['required_roles'] = ['speakers', 'listeners']
    window.apply_research_settings(rules)
    assert 'Reviewed 0/2' in window.progress_label.text()
    assert 'Check 1' in window.progress_label.text()


def test_csv_replacement_updates_progress_even_when_annotation_count_is_unchanged(coding_window, media):
    window = coding_window
    window.apply_research_settings({'required_roles': ['speakers']})
    window.current_speakers = ['Sheldon']
    window.record_annotation(0, False)
    window.set_review_state('confirmed')
    path = media / 'replace.csv'
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['position', 'start_time', 'end_time', 'speakers'])
        writer.writeheader()
        writer.writerow({'position': 2, 'start_time': '00:00:03,000', 'end_time': '00:00:04,000', 'speakers': 'Penny'})
    assert window.import_csv(str(path))
    assert 'Coded 1/2' in window.progress_label.text()
    assert 'Reviewed 0/2' in window.progress_label.text()
    assert 'Check 0' in window.progress_label.text()


def test_clearing_filters_reveals_rows_hidden_by_review_filter(coding_window):
    window = coding_window
    window.current_speakers = ['Sheldon']
    window.record_annotation(0, False)
    window.review_filter.setCurrentIndex(window.review_filter.findData('attention'))
    assert window.subtitle_list.isRowHidden(1)
    window.clear_subtitle_filters()
    assert not window.subtitle_list.isRowHidden(0)
    assert not window.subtitle_list.isRowHidden(1)
