from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QCheckBox,
                              QFormLayout, QDialogButtonBox, QTableWidget,
                              QTableWidgetItem, QPushButton, QHBoxLayout, QAbstractItemView)
from PySide6.QtWidgets import QTextEdit
import json
from src.core.research import ROLES, ROLE_LABELS, STATES, review_state


class ResearchSettingsDialog(QDialog):
    def __init__(self, parent, study):
        super().__init__(parent)
        self.setWindowTitle('Project coding rules')
        self.resize(550, 400)
        layout = QVBoxLayout(self)
        explanation = QLabel('These rules belong to this project. Confirmation requires a selection or explicit N/A for each required role. Changing the codebook or rules sends confirmed units back for review.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        form = QFormLayout()
        self.coder = QLineEdit(study['coder_id'])
        self.version = QLineEdit(study['codebook_version'])
        self.coder.setPlaceholderText('Researcher or anonymized coder ID')
        self.version.setPlaceholderText('e.g. study-A / 2026-10 revision 1')
        form.addRow('Coder ID', self.coder)
        form.addRow('Codebook version', self.version)
        self.required = {}
        self.definitions = {}
        for role in ROLES:
            checkbox = QCheckBox(f'{ROLE_LABELS[role]} is required')
            checkbox.setChecked(role in study['required_roles'])
            edit = QTextEdit()
            edit.setPlainText(study['definitions'][role])
            edit.setMaximumHeight(80)
            edit.setPlaceholderText('Operational definition, examples and ambiguous cases')
            self.required[role], self.definitions[role] = checkbox, edit
            form.addRow(checkbox)
            form.addRow(f'{ROLE_LABELS[role]} definition / examples', edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self):
        return {'coder_id': self.coder.text().strip(), 'codebook_version': self.version.text().strip(),
                'required_roles': [role for role in ROLES if self.required[role].isChecked()],
                'definitions': {role: self.definitions[role].toPlainText().strip() for role in ROLES}}


class ProjectHistoryDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Material and coding history')
        self.resize(850, 650)
        layout = QVBoxLayout(self)
        material = QLabel(f"Video: {parent.video_file}\nSubtitles: {parent.srt_file}\n"
                          f"Coder: {parent.study['coder_id'] or 'not set'} · Codebook: {parent.study['codebook_version'] or 'not set'}\n"
                          f"Subtitle content SHA-256: {parent.material['subtitle_sha256']}\n"
                          f"Video content SHA-256: {parent.material.get('video_sha256', 'not verified yet; verified when comparing coder projects')}")
        material.setWordWrap(True)
        material.setTextFormat(Qt.PlainText)
        material.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(material)
        self.events = list(reversed(parent.audit_log))
        table = QTableWidget(len(self.events), 4)
        table.setHorizontalHeaderLabels(['Time (UTC)', 'Coder', 'Unit', 'Action'])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for row, event in enumerate(self.events):
            for col, text in enumerate((event['at'], event.get('coder_id') or 'not set',
                                        str(event.get('unit_position', 'Project')), event['action'])):
                table.setItem(row, col, QTableWidgetItem(text))
        table.setColumnWidth(0, 245)
        table.setColumnWidth(1, 115)
        table.setColumnWidth(2, 65)
        table.setColumnWidth(3, 320)
        layout.addWidget(table)
        details = QTextEdit()
        details.setReadOnly(True)
        details.setPlaceholderText('Select a history entry to inspect its recorded changes.')
        table.currentCellChanged.connect(lambda row, *_: details.setPlainText(json.dumps(self.events[row], ensure_ascii=False, indent=2)) if row >= 0 else None)
        layout.addWidget(details)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)


class ComparisonDialog(QDialog):
    def __init__(self, parent, differences, source, coder):
        super().__init__(parent)
        self.setWindowTitle('Compare independent coding')
        self.resize(960, 550)
        self.differences = differences
        self.source = source
        self.coder = coder
        self.owner = parent
        layout = QVBoxLayout(self)
        info = QLabel(f'Other coder: {coder or "not set"} — {source}\nResolve each difference explicitly. Resolved units remain “Needs review” until you confirm them.')
        info.setWordWrap(True)
        layout.addWidget(info)
        self.table = QTableWidget(len(differences), 4)
        self.table.setHorizontalHeaderLabels(['Unit', 'Subtitle', 'Current coding', 'Other coding'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for row, (index, left, right) in enumerate(differences):
            def describe(annotation):
                roles = '\n'.join(f'{ROLE_LABELS[role]}: ' + (', '.join(annotation.get(role, [])) or ('N/A' if role in annotation.get('not_applicable', []) else '—')) for role in ROLES)
                custom = '\n'.join(f'{field}: {annotation.get(field, "")}' for field in parent.custom_columns if field != 'Note')
                return roles + f'\n{STATES[review_state(annotation)]}\n' + annotation.get('note', annotation.get('Note', '')) + '\n' + annotation.get('exclusion_reason', '') + '\n' + custom
            for col, text in enumerate((str(index + 1), parent.subtitles[index]['text'], describe(left), describe(right))):
                self.table.setItem(row, col, QTableWidgetItem(text))
        self.table.setColumnWidth(0, 55)
        for col in range(1, 4):
            self.table.setColumnWidth(col, 270)
        self.table.resizeRowsToContents()
        self.table.itemDoubleClicked.connect(self.show_unit)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        for label, callback in [('Show unit', self.show_unit), ('Keep current', lambda: self.resolve(False)),
                                ('Use other', lambda: self.resolve(True)), ('Close', self.accept)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        if differences:
            self.table.selectRow(0)

    def show_unit(self, *_):
        row = self.table.currentRow()
        if row >= 0:
            self.owner.jump_to_subtitle(self.differences[row][0], inherit=False)

    def resolve(self, use_other):
        row = self.table.currentRow()
        if row < 0:
            return
        index, left, right = self.differences[row]
        self.owner.resolve_comparison(index, right if use_other else left, self.source, self.coder, use_other)
        self.table.removeRow(row)
        del self.differences[row]
        if self.differences:
            self.table.selectRow(min(row, len(self.differences) - 1))
