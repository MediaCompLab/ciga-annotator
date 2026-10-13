"""Research workflow shared by mouse controls, shortcuts and project storage."""
from copy import deepcopy
from pathlib import Path
import hashlib
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (QHBoxLayout, QPushButton, QCheckBox, QLabel,
                              QListWidget, QListWidgetItem, QComboBox, QMessageBox,
                              QFileDialog, QInputDialog, QApplication, QProgressDialog)
from src.core.project import read_project_file
from src.core.research import (ROLES, ROLE_LABELS, STATES, CodingHistory,
                               study_settings, material_identity, ensure_character_ids,
                               normalize_annotation, missing_roles, review_state, now,
                               compare_projects)
from src.ui.research_dialogs import ResearchSettingsDialog, ComparisonDialog, ProjectHistoryDialog


class ResearchWorkflow:
    def init_research(self, project_data):
        self.study = study_settings(project_data.get('study'))
        self.material = material_identity(self.subtitles)
        self.material['video_name'] = Path(self.video_file).name
        self.material['video_size'] = Path(self.video_file).stat().st_size if Path(self.video_file).is_file() else None
        recorded = project_data.get('material', {})
        if recorded.get('subtitle_sha256') and recorded['subtitle_sha256'] != self.material['subtitle_sha256']:
            raise ValueError('The subtitles differ from this project’s recorded material. Restore the original subtitle file to protect coding-unit alignment.')
        if recorded.get('video_size') is not None and recorded['video_size'] != self.material['video_size']:
            raise ValueError('The video size differs from the recorded material. Restore the original video to protect coding context.')
        if recorded.get('video_sha256'):
            self.material['video_sha256'] = recorded['video_sha256']
        if any(index < 0 or index >= len(self.subtitles) for index in self.annotations):
            raise ValueError('A coding unit falls outside the subtitle material.')
        ensure_character_ids(self.characters)
        # Preserve legacy/imported names even if the old character list is incomplete.
        names = {character['name'] for character in self.characters}
        for annotation in self.annotations.values():
            for role in ROLES:
                for name in annotation.get(role, []):
                    if name not in names:
                        self.characters.append({'name': name, 'key': None})
                        names.add(name)
        ensure_character_ids(self.characters)
        self.annotations = {index: normalize_annotation(annotation, self.characters)
                            for index, annotation in self.annotations.items()}
        self.audit_log = project_data.get('audit_log', [])
        self.history = CodingHistory()
        self.last_autosave = ''
        self._note_audit_coalesce = False
        if self.vat_file and project_data.get('schema_version', 1) < 2:
            self.is_dirty = True

    def add_character_controls(self, layout):
        bar = QHBoxLayout()
        for label, callback in [('Add', self.focus_new_character_row), ('Rename', self.rename_selected_character),
                                ('Delete', self.delete_selected_character)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            bar.addWidget(button)
        layout.addWidget(QLabel('Characters · double-click to edit name or shortcut'))
        layout.addLayout(bar)

    def add_coding_controls(self, layout):
        bar = QHBoxLayout()
        self.role_buttons = {}
        self.na_checks = {}
        for role in ROLES:
            button = QPushButton(ROLE_LABELS[role])
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, role=role: self.set_active_role(role))
            bar.addWidget(button)
            self.role_buttons[role] = button
        layout.addLayout(bar)
        self.role_definition = QLabel()
        self.role_definition.setWordWrap(True)
        self.role_definition.setTextFormat(Qt.PlainText)
        layout.addWidget(self.role_definition)
        self.coding_characters = QListWidget()
        self.coding_characters.setMaximumHeight(110)
        self.coding_characters.setAccessibleName('Characters for the active coding role')
        self.coding_characters.itemChanged.connect(self.on_character_checked)
        layout.addWidget(self.coding_characters)
        na_bar = QHBoxLayout()
        for role in ROLES:
            checkbox = QCheckBox(f'{ROLE_LABELS[role]} N/A')
            checkbox.toggled.connect(lambda checked, role=role: self.set_not_applicable(role, checked))
            self.na_checks[role] = checkbox
            na_bar.addWidget(checkbox)
        layout.addLayout(na_bar)

    def add_review_controls(self, layout):
        self.review_label = QLabel()
        self.review_label.setWordWrap(True)
        self.review_label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.review_label)
        bar = QHBoxLayout()
        self.confirm_btn = QPushButton('Confirm && next')
        self.confirm_btn.clicked.connect(self.confirm_current)
        bar.addWidget(self.confirm_btn)
        review = QPushButton('Needs review')
        review.clicked.connect(lambda: self.set_review_state('needs_review'))
        bar.addWidget(review)
        exclude = QPushButton('Exclude…')
        exclude.clicked.connect(self.exclude_current)
        bar.addWidget(exclude)
        layout.addLayout(bar)
        self.project_rules_btn = QPushButton('Project coding rules…')
        self.project_rules_btn.clicked.connect(self.show_research_settings)
        layout.addWidget(self.project_rules_btn)

    def add_review_filter(self, bar):
        self.review_filter = QComboBox()
        self.review_filter.addItem('All coding states', 'all')
        self.review_filter.addItem('Unfinished', 'unfinished')
        for state, label in STATES.items():
            self.review_filter.addItem(label, state)
        self.review_filter.currentIndexChanged.connect(self.apply_subtitle_filters)
        bar.addWidget(self.review_filter)

    def sync_research_controls(self):
        if not hasattr(self, 'coding_characters'):
            return
        annotation = self.annotations.get(self.current_subtitle_index, {})
        self.unit_label.setText(f'Coding unit {self.current_subtitle_index + 1} of {len(self.subtitles)}')
        coder = self.study['coder_id'] or 'not set'
        codebook = self.study['codebook_version'] or 'not set'
        self.study_label.setText(f'Coder: {coder[:20]} · Codebook: {codebook[:24]}')
        self.study_label.setToolTip(f'Coder: {coder}\nCodebook: {codebook}')
        with QSignalBlocker(self.coding_characters):
            selected = getattr(self, f'current_{self.active_role}')
            names = [character['name'] for character in self.characters]
            listed = [self.coding_characters.item(index).data(Qt.UserRole) for index in range(self.coding_characters.count())]
            if names != listed:
                self.coding_characters.clear()
                for name in names:
                    item = QListWidgetItem()
                    item.setData(Qt.UserRole, name)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    self.coding_characters.addItem(item)
            for index, character in enumerate(self.characters):
                item = self.coding_characters.item(index)
                item.setText(character['name'] + (f"  (Alt+{character['key']})" if character.get('key') else ''))
                item.setCheckState(Qt.Checked if character['name'] in selected else Qt.Unchecked)
        for role in ROLES:
            self.role_buttons[role].setChecked(role == self.active_role)
            with QSignalBlocker(self.na_checks[role]):
                self.na_checks[role].setChecked(role in annotation.get('not_applicable', []))
        definition = self.study['definitions'][self.active_role]
        self.role_definition.setText((definition[:170] + '…' if len(definition) > 170 else definition)
                                    or 'Choose characters or mark N/A. Configure definitions in Project rules.')
        self.role_definition.setToolTip(definition)
        state = review_state(annotation)
        missing = missing_roles(annotation, self.study)
        message = STATES[state]
        if annotation.get('inherited_from'):
            message += ' · Inherited suggestions: verify before confirming'
        if state == 'excluded':
            message += ' · ' + annotation.get('exclusion_reason', '')
        elif missing:
            message += ' · Still required: ' + ', '.join(ROLE_LABELS[role] for role in missing)
        elif state != 'confirmed':
            message += ' · Ready for explicit confirmation'
        self.review_label.setText(message)
        self.confirm_btn.setEnabled(not missing)
        self.confirm_btn.setToolTip('Select characters or N/A for every required role.' if missing else 'Confirm this unit under the project’s rules and move to the next unfinished unit.')
        self.project_rules_btn.setText('Project coding rules…')
        self.project_rules_btn.setToolTip(f"Coder: {self.study['coder_id'] or 'not set'}\nCodebook: {self.study['codebook_version'] or 'not set'}")
        if hasattr(self, 'undo_action'):
            self.undo_action.setEnabled(bool(self.history.undo_entries))
            self.redo_action.setEnabled(bool(self.history.redo_entries))

    def on_character_checked(self, item):
        name = item.data(Qt.UserRole)
        self._toggle_role_name(self.active_role, name)
        self.record_annotation(self.current_subtitle_index, clear_selections=False)

    def set_not_applicable(self, role, checked):
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        annotation = deepcopy(self.annotations.get(self.current_subtitle_index, {}))
        na = set(annotation.get('not_applicable', []))
        if checked:
            na.add(role)
            annotation[role] = []
            setattr(self, f'current_{role}', [])
        else:
            na.discard(role)
        annotation['not_applicable'] = [role for role in ROLES if role in na]
        self.commit_annotation(self.current_subtitle_index, annotation, 'Set N/A')
        self.refresh_role_summary()

    def audit(self, action, index=None, before=None, after=None, **extra):
        event = {'at': now(), 'coder_id': self.study['coder_id'], 'codebook_version': self.study['codebook_version'],
                 'action': action, **extra}
        if index is not None:
            event['unit_id'] = self.material['unit_ids'][index]
            event['unit_position'] = index + 1
        if before is not None:
            event['before'] = deepcopy(before)
        if after is not None:
            event['after'] = deepcopy(after)
        # A note entry records the final text of a continuous edit, not each keystroke.
        if action == 'Edit note' and self._note_audit_coalesce and self.audit_log:
            last = self.audit_log[-1]
            if last.get('action') == action and last.get('unit_id') == event.get('unit_id') and last.get('coder_id') == event['coder_id']:
                last['after'], last['at'] = event['after'], event['at']
                return
        self.audit_log.append(event)
        self._note_audit_coalesce = action == 'Edit note'

    def break_note_edit(self):
        self.history.break_group()
        self._note_audit_coalesce = False

    def commit_annotation(self, index, annotation, action='Edit coding', invalidate=True, refresh=True, **provenance):
        before = deepcopy(self.annotations.get(index, {}))
        after = normalize_annotation(annotation, self.characters)
        for role in ROLES:
            if after[role] and role in after['not_applicable']:
                after['not_applicable'].remove(role)
        if after == before:
            return False
        if invalidate:
            state = review_state(before)
            after['review_state'] = 'needs_review' if state in ('confirmed', 'excluded', 'needs_review') else 'in_progress'
            after.pop('confirmation', None)
            after.pop('exclusion_reason', None)
        self.history.push(index, before, after, action, coalesce=(action == 'Edit note'))
        self.audit(action, index, before, after, **provenance)
        self.annotations[index] = after
        self.is_dirty = True
        self.refresh_subtitle_row(index)
        if refresh:
            self.apply_subtitle_filters()
            self.update_progress_status()
        return True

    def set_review_state(self, state, reason=''):
        if state == 'excluded' and not reason.strip():
            self.statusBar().showMessage('Enter a reason before excluding this unit.', 8000)
            return False
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        index = self.current_subtitle_index
        annotation = deepcopy(self.annotations.get(index, {}))
        if state == 'confirmed':
            missing = missing_roles(annotation, self.study)
            if missing:
                self.statusBar().showMessage('Still required: ' + ', '.join(ROLE_LABELS[role] for role in missing), 8000)
                return False
            annotation['confirmation'] = {'at': now(), 'coder_id': self.study['coder_id'],
                                          'codebook_version': self.study['codebook_version']}
            annotation.pop('inherited_from', None)
        else:
            annotation.pop('confirmation', None)
        annotation['review_state'] = state
        if state == 'excluded':
            annotation['exclusion_reason'] = reason
        else:
            annotation.pop('exclusion_reason', None)
        self.commit_annotation(index, annotation, f'Mark {STATES[state]}', invalidate=False)
        return True

    def confirm_current(self):
        if self.set_review_state('confirmed'):
            self.jump_to_next_uncoded()

    def exclude_current(self):
        reason, ok = QInputDialog.getText(self, 'Exclude coding unit', 'Reason for excluding this unit (kept in project):')
        if ok and reason.strip():
            self.set_review_state('excluded', reason.strip())

    def show_research_settings(self):
        dialog = ResearchSettingsDialog(self, self.study)
        if dialog.exec():
            self.apply_research_settings(dialog.value())

    def apply_research_settings(self, value):
        before = deepcopy(self.study)
        after = study_settings(value)
        if before == after:
            return
        self.study = after
        self.audit('Change project rules', before=before, after=after)
        if any(before[key] != after[key] for key in ('required_roles', 'definitions', 'codebook_version')):
            for index, annotation in list(self.annotations.items()):
                if review_state(annotation) == 'confirmed':
                    changed = deepcopy(annotation)
                    changed['review_state'] = 'needs_review'
                    changed.pop('confirmation', None)
                    self.commit_annotation(index, changed, 'Review after rule change', invalidate=False, refresh=False)
        # Undo patches made under previous rules cannot restore stale confirmations.
        self.history = CodingHistory()
        self.is_dirty = True
        self.sync_research_controls()
        self.apply_subtitle_filters()
        self.update_progress_status()

    def undo_coding(self):
        self.apply_history(False)

    def redo_coding(self):
        self.apply_history(True)

    def apply_history(self, redo):
        result = self.history.redo() if redo else self.history.undo()
        if result is None:
            return
        index, restored, action = result
        before = deepcopy(self.annotations.get(index, {}))
        if restored:
            self.annotations[index] = restored
        else:
            self.annotations.pop(index, None)
        self.audit(('Redo ' if redo else 'Undo ') + action, index, before, restored)
        self.is_dirty = True
        self.refresh_subtitle_row(index)
        self.jump_to_subtitle(index, inherit=False)
        self.apply_subtitle_filters()
        self.sync_research_controls()

    def rename_selected_character(self):
        row = self.character_table.currentRow()
        if 0 <= row < len(self.characters):
            self.right_tabs.setCurrentIndex(1)
            self.character_table.setCurrentCell(row, 0)
            self.character_table.editItem(self.character_table.item(row, 0))

    def export_analysis_dialog(self):
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        count = sum(review_state(annotation) == 'confirmed' for annotation in self.annotations.values())
        if not count:
            QMessageBox.information(self, 'No confirmed coding', 'Confirm at least one unit before exporting for analysis.')
            return
        path, _ = QFileDialog.getSaveFileName(self, f'Export {count} confirmed units', 'confirmed-coding.csv', 'CSV Files (*.csv)')
        if path:
            self.export_csv(path, confirmed_only=True)

    def export_characters_dialog(self):
        from src.core.characters import save_characters
        path, _ = QFileDialog.getSaveFileName(self, 'Export character template', 'characters.txt', 'Text Files (*.txt)')
        if path:
            try:
                save_characters(path, self.characters)
                self.statusBar().showMessage(f'Character template exported to {path}', 8000)
            except OSError as error:
                QMessageBox.warning(self, 'Export failed', str(error))

    def compare_project_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Compare another coder’s project', '', 'VAT Projects (*.vat)')
        if not path:
            return
        try:
            other = read_project_file(path)
            # Check subtitles/rules first, before potentially lengthy video reads.
            compare_projects(self._project_data(self.vat_file or self.srt_file), other)
            current_digest = self.video_digest(self.video_file)
            if current_digest is None:
                return
            if self.material.get('video_sha256') and self.material['video_sha256'] != current_digest:
                raise ValueError('The current video content has changed since its recorded verification.')
            other_video = Path(other.get('video_file', ''))
            if not other_video.is_absolute():
                other_video = Path(path).parent / other_video
            other_digest = self.video_digest(other_video)
            if other_digest is None:
                return
            if other.get('material', {}).get('video_sha256') and other['material']['video_sha256'] != other_digest:
                raise ValueError('The other project’s video content has changed since its recorded verification.')
            if current_digest != other_digest:
                raise ValueError('Video content differs between these projects.')
            if self.material.get('video_sha256') != current_digest:
                self.material['video_sha256'] = current_digest
                self.audit('Verify video material', after={'video_sha256': current_digest})
                self.is_dirty = True
                self.update_progress_status()
            other['material']['video_sha256'] = other_digest
            differences = compare_projects(self._project_data(self.vat_file or self.srt_file), other)
            if not differences:
                QMessageBox.information(self, 'Comparison', 'No differences in roles, N/A, review state or notes.')
                return
            ComparisonDialog(self, differences, path, study_settings(other.get('study'))['coder_id']).exec()
        except (OSError, ValueError, KeyError, TypeError) as error:
            QMessageBox.warning(self, 'Cannot compare', str(error))

    def video_digest(self, path):
        path = Path(path)
        size = path.stat().st_size
        progress = QProgressDialog(f'Verifying video material: {path.name}', 'Cancel', 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(300)
        digest = hashlib.sha256()
        read = 0
        try:
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                    digest.update(chunk)
                    read += len(chunk)
                    progress.setValue(min(99, int(read * 100 / size)))
                    QApplication.processEvents()
                    if progress.wasCanceled():
                        return None
            return digest.hexdigest()
        finally:
            progress.close()

    def show_project_history(self):
        ProjectHistoryDialog(self).exec()

    def resolve_comparison(self, index, annotation, source, coder, use_other):
        annotation = deepcopy(annotation)
        annotation['review_state'] = 'needs_review'
        annotation.pop('confirmation', None)
        self.commit_annotation(index, annotation, 'Resolve coder difference', invalidate=False,
                               source_project=str(source), source_coder=coder,
                               decision='use_other' if use_other else 'keep_current')
        self.jump_to_subtitle(index)
