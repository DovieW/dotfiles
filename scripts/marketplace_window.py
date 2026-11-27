"""Marketplace discovery and preview dialog for AI Customization."""
import json
from pathlib import Path
import shlex
from urllib.parse import urlsplit

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget,
)


SOURCES = {
    "skills": ("Skills · skills.sh", "https://skills.sh/"),
    "mcp": ("MCP · Official Registry", "https://registry.modelcontextprotocol.io/"),
    "plugins": ("Plugins · Codex", "https://chatgpt.com/plugins"),
}


class MarketplaceWindow(QDialog):
    def __init__(self, window, catalog, combo_type, backend, peer):
        super().__init__(window)
        self.setWindowTitle("Marketplace")
        self.resize(850, 550)
        self.backend = backend
        self.peer = peer
        self.stage_item = window.stage_marketplace
        self.skill_link_parents = window.skill_link_parents
        self.results = []
        self.cursor = None
        self.loaded_query = ""
        self.preview = None
        self.request = None
        self.process = QProcess(self)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_failed)

        self.source = combo_type()
        for key, (name, _) in SOURCES.items():
            self.source.addItem(name, key)
        self.source.setCurrentIndex(self.source.findData(catalog))
        self.source.currentIndexChanged.connect(self.reset_catalog)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search marketplace")
        self.query.returnPressed.connect(self.search)
        self.go = QPushButton("Search")
        self.go.clicked.connect(self.search)
        self.paste = QPushButton("Paste skill link…")
        self.paste.clicked.connect(self.paste_link)
        self.paste.setVisible(self.catalog == "skills")
        self.more = QPushButton("More results")
        self.more.setEnabled(False)
        self.more.clicked.connect(lambda: self.search(append=True))
        top = QHBoxLayout()
        for item in (self.source, self.query, self.go, self.paste):
            top.addWidget(item, 1 if item is self.query else 0)

        self.items = QListWidget()
        self.items.currentRowChanged.connect(self.select)
        self.items.itemDoubleClicked.connect(self.load_preview)
        self.inspect = QPushButton("Preview")
        self.inspect.setEnabled(False)
        self.inspect.clicked.connect(self.load_preview)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select an item to preview.")
        self.methods = combo_type()
        self.methods.currentIndexChanged.connect(self.show_preview)
        self.methods.hide()
        self.mode = combo_type()
        self.mode.addItem("Manual only", "manual")
        self.mode.addItem("Automatic", "automatic")
        self.mode.hide()
        self.link_skill = QCheckBox("Link from another skill")
        self.link_skill.setToolTip("Add a reference to this guide in an enabled custom dotfiles skill.")
        self.link_skill.hide()
        self.parent_skill = combo_type()
        self.parent_skill.hide()
        self.link_skill.toggled.connect(self.parent_skill.setVisible)
        self.browser = QPushButton("Open in Chrome")
        self.browser.clicked.connect(self.open_details)
        self.stage = QPushButton("Stage install")
        self.stage.clicked.connect(self.stage_selected)
        self.stage.setEnabled(False)
        self.status = QLabel(f"Install scope · {window.scope.currentText()}")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.items)
        left_layout.addWidget(self.more)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.details)
        right_layout.addWidget(self.methods)
        right_layout.addWidget(self.mode)
        link_options = QHBoxLayout()
        link_options.addWidget(self.link_skill)
        link_options.addWidget(self.parent_skill, 1)
        right_layout.addLayout(link_options)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([310, 480])
        footer = QHBoxLayout()
        footer.addWidget(self.inspect)
        footer.addWidget(self.browser)
        footer.addStretch()
        footer.addWidget(self.stage)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(split, 1)
        layout.addWidget(self.status)
        layout.addLayout(footer)
        self.status.setToolTip("Changes install when you choose Apply & Sync in AI Customization.")
        if self.catalog != "skills":
            self.search()

    @property
    def catalog(self):
        return self.source.currentData()

    def reset_catalog(self):
        self.paste.setVisible(self.catalog == "skills")
        self.items.clear()
        self.results = []
        self.cursor = None
        self.clear_preview()
        self.search()

    def clear_preview(self):
        self.preview = None
        self.details.clear()
        self.methods.hide()
        self.mode.hide()
        self.link_skill.setChecked(False)
        self.link_skill.hide()
        self.parent_skill.clear()
        self.stage.setEnabled(False)

    def search(self, append=False):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        query = self.query.text().strip()
        if self.catalog == "skills" and len(query) < 2:
            self.status.setText("Search with at least two characters or paste a skills.sh link.")
            return
        if not append:
            self.results = []
            self.items.clear()
            self.cursor = None
            self.clear_preview()
            self.loaded_query = query
        self.call({"action": "search", "query": self.loaded_query, "cursor": self.cursor if append else None})

    def paste_link(self):
        link, accepted = QInputDialog.getText(self, "Preview a skill", "skills.sh link")
        if accepted and link.strip():
            self.call({"action": "preview", "id": link.strip()})

    def select(self, row):
        self.clear_preview()
        self.inspect.setEnabled(row >= 0 and self.process.state() == QProcess.ProcessState.NotRunning)

    def load_preview(self):
        row = self.items.currentRow()
        if row >= 0:
            self.call({"action": "preview", "id": self.results[row]["id"]})

    def call(self, request):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.request = request["action"]
        self.stage.setEnabled(False)
        self.source.setEnabled(False)
        self.items.setEnabled(False)
        self.go.setEnabled(False)
        self.paste.setEnabled(False)
        self.inspect.setEnabled(False)
        self.more.setEnabled(False)
        self.status.setText("Searching…" if self.request == "search" else "Preparing preview…")
        self.process.start(str(self.backend), ["marketplace"])
        self.process.write(json.dumps({**request, "catalog": self.catalog,
                                      "peer": self.peer and self.catalog == "plugins"}).encode())
        self.process.closeWriteChannel()

    def ready(self):
        self.source.setEnabled(True)
        self.items.setEnabled(True)
        self.go.setEnabled(True)
        self.paste.setEnabled(True)
        self.inspect.setEnabled(self.items.currentRow() >= 0)
        self.more.setEnabled(bool(self.cursor))

    def process_failed(self, _error):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.ready()
            self.status.setText("Could not start marketplace discovery.")

    def finished(self, code, _status):
        self.ready()
        if code:
            self.status.setText(bytes(self.process.readAllStandardError()).decode(errors="replace").strip()
                                or "The marketplace is unavailable.")
            return
        try:
            result = json.loads(bytes(self.process.readAllStandardOutput()))
        except ValueError:
            self.status.setText("The marketplace returned an invalid response.")
            return
        if self.request == "search":
            self.cursor = result.get("cursor")
            self.more.setEnabled(bool(self.cursor))
            for entry in result["items"]:
                self.results.append(entry)
                item = QListWidgetItem(entry["title"] + "\n" + entry["source"])
                item.setToolTip(entry.get("description", ""))
                self.items.addItem(item)
            self.status.setText(f"{len(self.results)} results" if self.results else "No matching entries.")
        else:
            self.preview = result
            self.methods.blockSignals(True)
            self.methods.clear()
            for method in result.get("choices", []):
                self.methods.addItem(method["label"], method)
            self.methods.blockSignals(False)
            self.methods.setVisible(self.methods.count() > 0)
            self.mode.setVisible(self.catalog == "skills")
            self.mode.setCurrentIndex(0)
            parents = self.skill_link_parents(result["name"]) if self.catalog == "skills" else []
            self.link_skill.setChecked(False)
            self.parent_skill.clear()
            self.parent_skill.addItems(parents)
            self.link_skill.setVisible(bool(parents))
            self.show_preview()
            self.status.setText("Review the details, then stage the install.")

    def show_preview(self):
        if not self.preview:
            return
        item = self.preview
        lines = [item["title"], item["source"], "", item.get("description", ""), "", *item.get("details", [])]
        if item.get("installed"):
            lines.append("Installed on the computer browsing this catalog.")
        choice = self.methods.currentData()
        available = self.catalog != "mcp" or bool(choice)
        if choice:
            if choice["kind"] == "https":
                lines.extend(["", f"Server URL: {choice['url']}"])
                if choice.get("headers"):
                    lines.extend(["", "Required headers from local environment",
                                  *(f"{key}: {name}" for key, name in choice["headers"].items()),
                                  "An absent value leaves the server disabled on that computer."])
                if choice.get("optional_headers"):
                    lines.append("Advertised optional headers: " + ", ".join(choice["optional_headers"]))
            else:
                name, version = choice["package"], choice["version"]
                command = (["npx", "--yes", "--", f"{name}@{version}"] if choice["kind"] == "npm"
                           else ["uvx", "--from", f"{name}=={version}", name])
                lines.extend(["", "Launch command", shlex.join([*command, *choice["arguments"]])])
                if choice["env_vars"]:
                    lines.extend(["", "Required local environment: " + ", ".join(choice["env_vars"]),
                                  "An absent value leaves the server disabled on that computer."])
        if not available:
            lines.extend(["", "This entry needs a setup that the marketplace installer cannot prepare."])
        self.details.setPlainText("\n".join(lines))
        self.stage.setEnabled(available)

    def open_details(self):
        row = self.items.currentRow()
        url = (self.preview or (self.results[row] if row >= 0 else {})).get("url") or SOURCES[self.catalog][1]
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None:
            return
        # An explicit click opens the listing in the computer's Chrome session.
        launcher = Path.home() / ".local/bin/google-chrome-stable"
        chrome = str(launcher) if launcher.is_file() else "/usr/bin/google-chrome-stable"
        if not QProcess.startDetached(chrome, [url])[0]:
            self.status.setText("Could not open Chrome.")

    def stage_selected(self):
        if not self.preview:
            return
        parent = self.parent_skill.currentText() if self.link_skill.isChecked() else None
        message = self.stage_item(self.catalog, self.preview, self.methods.currentData(), self.mode.currentData(), parent)
        self.status.setText(message)

    def done(self, result):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
        super().done(result)
