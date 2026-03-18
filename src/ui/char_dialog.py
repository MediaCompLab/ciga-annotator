from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QPushButton, QDialogButtonBox, QHeaderView
)

class ManageCharactersDialog(QDialog):
    def __init__(self, characters, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Characters & Shortcuts")
        self.resize(300, 400)
        self.characters = characters.copy()
        
        self.layout = QVBoxLayout(self)
        self.table = QTableWidget(len(self.characters), 2)
        self.table.setHorizontalHeaderLabels(["Name", "Shortcut (e.g. 1, Q)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        for row, char in enumerate(self.characters):
            self.table.setItem(row, 0, QTableWidgetItem(char['name']))
            self.table.setItem(row, 1, QTableWidgetItem(char.get('key', '')))
            
        self.layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add New Row")
        self.add_btn.clicked.connect(self.add_row)
        self.del_btn = QPushButton("Delete Selected Row")
        self.del_btn.clicked.connect(self.delete_row)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.del_btn)
        self.layout.addLayout(btn_layout)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)

    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(""))
        self.table.setItem(row, 1, QTableWidgetItem(""))

    def delete_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def get_data(self):
        data = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            key_item = self.table.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            key = key_item.text().strip().upper() if key_item else ""
            if len(key) > 1:
                key = key[0]
            if name:
                data.append({'name': name, 'key': key if key else None})
        return data
