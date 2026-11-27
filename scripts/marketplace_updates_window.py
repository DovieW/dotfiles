"""Review and stage available marketplace updates."""
import hashlib
import json

from PyQt6.QtCore import QProcess, QSettings, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QHeaderView, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from marketplace_window import open_chrome


KINDS = {"skills": "Skill", "mcp": "MCP server", "plugins": "Plugin"}


class UpdatesWindow(QDialog):
    def __init__(self, window, backend, hosts):
        super().__init__(window)
        self.setWindowTitle("Marketplace updates")
        self.resize(1010, 620)
        self.backend = backend
        self.scope = window.target
        self.hosts = hosts
        self.stage_updates = window.stage_updates
        self.preferences = QSettings("DovieW", "AI Customization")
        self.process = QProcess(self)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.failed)

        self.items = QTreeWidget()
        self.items.setRootIsDecorated(False)
        self.items.setAlternatingRowColors(True)
        self.items.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.items.setHeaderLabels(["Update", "Item", "Type", "Computer", "Installed", "Available"])
        self.items.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column in (0, 2, 3, 4, 5):
            self.items.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.items.currentItemChanged.connect(self.show_preview)
        self.items.itemChanged.connect(self.save_choice)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select an item to review its changes.")
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.items)
        split.addWidget(self.preview)
        split.setSizes([255, 220])

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.recheck = QPushButton("Check again")
        self.recheck.clicked.connect(self.check)
        self.open_source = QPushButton("Open source in Chrome")
        self.open_source.setEnabled(False)
        self.open_source.clicked.connect(self.open_details)
        self.stage = QPushButton("Stage selected updates")
        self.stage.setEnabled(False)
        self.stage.clicked.connect(self.stage_selected)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        footer = QHBoxLayout()
        for button in (self.recheck, self.open_source):
            footer.addWidget(button)
        footer.addStretch()
        footer.addWidget(self.stage)
        footer.addWidget(close)
        layout = QVBoxLayout(self)
        layout.addWidget(split, 1)
        layout.addWidget(self.status)
        layout.addLayout(footer)
        self.check()

    def check(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.items.clear()
        self.preview.clear()
        self.recheck.setEnabled(False)
        self.stage.setEnabled(False)
        self.status.setText(f"Checking {self.hosts[self.scope]}…")
        self.process.start(str(self.backend), ["marketplace-updates", "--target", self.scope])
        self.process.closeWriteChannel()

    def failed(self, _error):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.recheck.setEnabled(True)
            self.status.setText("Could not run the marketplace update check.")

    def finished(self, code, _status):
        self.recheck.setEnabled(True)
        if code:
            self.status.setText("The update check could not finish. Try again.")
            return
        try:
            result = json.loads(bytes(self.process.readAllStandardOutput()))
        except ValueError:
            self.status.setText("The update check returned an invalid response.")
            return
        self.items.blockSignals(True)
        rows = sorted(result["items"], key=lambda row: ("value" not in row, row["group"], row["name"], row["profile"]))
        for row in rows:
            item = QTreeWidgetItem(["", row["name"], KINDS[row["group"]], self.hosts[row["profile"]], row.get("current", "—"),
                                    row.get("available", "—")])
            item.setData(0, Qt.ItemDataRole.UserRole, row)
            item.setToolTip(1, row.get("note", row["name"]))
            if "value" in row:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                picked = self.preferences.value(self.preference_key(row), False, type=bool)
                item.setCheckState(0, Qt.CheckState.Checked if picked else Qt.CheckState.Unchecked)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self.items.addTopLevelItem(item)
        self.items.blockSignals(False)
        ready = sum("value" in row for row in rows)
        summary = f"{ready} available · {result['current']} current · {len(rows) - ready} need attention"
        self.status.setText("  ·  ".join([summary, *result["warnings"]]))
        self.items.setCurrentItem(self.items.topLevelItem(0))
        self.stage.setEnabled(bool(self.selected_updates()))

    def preference_key(self, row):
        identity = "\0".join(row[key] for key in ("group", "name", "profile"))
        return "marketplace-updates/" + hashlib.sha256(identity.encode()).hexdigest()

    def save_choice(self, item, column):
        row = item.data(0, Qt.ItemDataRole.UserRole)
        if column == 0 and row and "value" in row:
            self.preferences.setValue(self.preference_key(row), item.checkState(0) == Qt.CheckState.Checked)
            self.preferences.sync()
            self.stage.setEnabled(bool(self.selected_updates()))

    def show_preview(self, current, _previous):
        row = current.data(0, Qt.ItemDataRole.UserRole) if current else {}
        self.preview.setPlainText(row.get("preview", row.get("note", "")))
        self.open_source.setEnabled(bool(row.get("url")))

    def open_details(self):
        item = self.items.currentItem()
        if item and not open_chrome(item.data(0, Qt.ItemDataRole.UserRole).get("url", "")):
            self.status.setText("Could not open the source in Chrome.")

    def selected_updates(self):
        rows = [self.items.topLevelItem(index) for index in range(self.items.topLevelItemCount())]
        return [item.data(0, Qt.ItemDataRole.UserRole) for item in rows
                if item.checkState(0) == Qt.CheckState.Checked and item.flags() & Qt.ItemFlag.ItemIsUserCheckable]

    def stage_selected(self):
        message = self.stage_updates(self.selected_updates())
        if message:
            self.status.setText(message)
        else:
            self.accept()

    def done(self, result):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
        super().done(result)
