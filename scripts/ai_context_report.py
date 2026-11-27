"""Context report for the customization window."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHeaderView, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QSplitter,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)


KINDS = {"Instructions": "Instructions", "Skill": "Skills", "App": "Apps",
         "MCP server": "MCP servers", "Plugin": "Plugins"}


def number(value):
    return "—" if value is None else f"{value:,}"


class ContextItem(QTreeWidgetItem):
    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        value = self.data(column, Qt.ItemDataRole.UserRole)
        other_value = other.data(column, Qt.ItemDataRole.UserRole)
        if type(value) is int or type(other_value) is int:
            return (value is not None, value or 0) < (other_value is not None, other_value or 0)
        return super().__lt__(other)


class ContextReport(QWidget):
    def __init__(self, combo_type):
        super().__init__()
        self.metadata = QLabel()
        self.summary = QLabel()
        self.explanation = QLabel("Based on saved settings for a fresh session. A running conversation also "
                                  "accumulates messages and tool results.")
        for label in (self.metadata, self.summary, self.explanation):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
        font = self.summary.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 3)
        self.summary.setFont(font)
        self.capacity = QProgressBar()
        self.capacity.setRange(0, 1000)
        self.capacity.setTextVisible(False)
        self.capacity.setMaximumHeight(8)

        self.overview = self.tree(("Source", "Tokens", "Share of startup"))
        self.overview.setRootIsDecorated(True)
        overview_panel = self.detail_panel(self.overview, "Select a source or expand it to see its components.")

        self.items = self.tree(("Item", "Type", "Upfront", "Fully loaded", "Additional", "References"))
        self.items.setRootIsDecorated(False)
        self.kind = combo_type()
        self.kind.addItem("All items")
        for kind, name in KINDS.items():
            self.kind.addItem(name, kind)
        self.kind.currentIndexChanged.connect(self.filter_items)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search items")
        self.search.textChanged.connect(self.filter_items)
        tools = QHBoxLayout()
        tools.addWidget(self.search, 1)
        tools.addWidget(self.kind)
        item_panel = QWidget()
        items_layout = QVBoxLayout(item_panel)
        items_layout.addLayout(tools)
        items_layout.addWidget(self.detail_panel(self.items, "Select an item to see its counts and details."), 1)
        self.items.setSortingEnabled(True)
        self.items.sortItems(2, Qt.SortOrder.DescendingOrder)

        tabs = QTabWidget()
        tabs.addTab(overview_panel, "Overview")
        tabs.addTab(item_panel, "Items")
        layout = QVBoxLayout(self)
        layout.addWidget(self.metadata)
        layout.addWidget(self.summary)
        layout.addWidget(self.capacity)
        layout.addWidget(tabs, 1)
        layout.addWidget(self.explanation)
        self.show_result({}, "")

    @staticmethod
    def tree(headers):
        tree = QTreeWidget()
        tree.setHeaderLabels(headers)
        tree.setAlternatingRowColors(True)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(headers)):
            tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        return tree

    @staticmethod
    def detail_panel(tree, prompt):
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlaceholderText(prompt)
        tree.currentItemChanged.connect(lambda item, _: details.setPlainText(item.toolTip(0) if item else ""))
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(tree)
        split.addWidget(details)
        split.setSizes([380, 130])
        return split

    def show_result(self, result, metadata, waiting=""):
        self.overview.clear()
        self.items.clear()
        self.metadata.setText(metadata)
        report = result.get("report", {})
        total = report.get("startup")
        window = report.get("window") or {}
        limit = window.get("tokens")
        self.capacity.setVisible(total is not None and bool(limit))
        if total is None:
            self.summary.setText(waiting or "Measure context to see the startup breakdown.")
        else:
            headline = f"{number(total)} estimated startup tokens"
            if limit:
                percent = total / limit * 100
                headline += f" · {percent:.1f}% of a {number(limit)}-token window"
                self.capacity.setValue(min(1000, round(percent * 10)))
                self.capacity.setToolTip(window["source"])
            self.summary.setText(headline)
        self.fill_overview(result, report)
        self.fill_items(result)

    def fill_overview(self, result, report):
        total = report.get("startup")
        if total is None:
            return
        startup = QTreeWidgetItem(self.overview, ["Rendered startup", number(total)])
        startup.setToolTip(0, "Text blocks and tool definitions returned by Codex’s startup renderer. "
                           "The count excludes request framing and content outside the renderer.")
        instructions = next((row for row in result.get("rows", []) if row["kind"] == "Instructions"), {})
        for group in report["groups"]:
            size = group["tokens"]
            share = f"{size / total:.1%}" if total else "—"
            section = QTreeWidgetItem(startup, [group["name"], number(size), share])
            if group["name"] == "Instructions" and instructions.get("detail"):
                section.setToolTip(0, instructions["detail"])
            else:
                section.setToolTip(0, f"{group['name']} · {number(size)} estimated tokens")
            for part in group.get("parts", []):
                component = QTreeWidgetItem(section, [part["name"], number(part["tokens"])])
                component.setToolTip(0, f"{part['name']} · {number(part['tokens'])} estimated tokens")
        startup.setExpanded(True)

        known = [row["tokens"] for row in report["on_demand"] if row["tokens"] is not None]
        partial = any(row["known"] < row["total"] for row in report["on_demand"])
        extra = ("≥" if partial else "") + number(sum(known)) if known else "—"
        demand = QTreeWidgetItem(self.overview, ["Additional if loaded", extra])
        demand.setToolTip(0, "Estimated fully loaded size minus the upfront contribution, summed over items with both counts. "
                          "References are shown separately. Plugin totals overlap their bundled items and are excluded here.")
        for row in report["on_demand"]:
            size = row["tokens"]
            prefix = "≥" if size is not None and row["known"] < row["total"] else ""
            item = QTreeWidgetItem(demand, [KINDS[row["name"]], prefix + number(size)])
            item.setToolTip(0, f"{row['known']} of {row['total']} items have both estimates.")
        demand.setExpanded(True)
        refs = QTreeWidgetItem(self.overview, ["Skill reference files", number(report["references"])])
        refs.setToolTip(0, "Measured text references available to skills. Codex can read them on demand.")
        if report.get("non_text_parts"):
            startup.setToolTip(0, f"{startup.toolTip(0)} {report['non_text_parts']} non-text parts were omitted.")
        self.overview.setCurrentItem(startup)

    def fill_items(self, result):
        order = self.items.header().sortIndicatorOrder()
        column = self.items.header().sortIndicatorSection()
        self.items.setSortingEnabled(False)
        rows = list(result.get("rows", []))
        rows.extend({"kind": "Plugin", "name": name, **row}
                    for name, row in result.get("tables", {}).get("plugins", {}).items() if row)
        for row in rows:
            upfront, full = row.get("upfront"), row.get("full")
            extra = None
            if upfront is not None and full is not None and row["kind"] != "Plugin":
                extra = max(0, full - upfront)
            counts = (upfront, full, extra, row.get("references"))
            partials = (row.get("upfront_partial"), row.get("full_partial"), False, False)
            labels = [("≥" if partial else "") + number(size) for size, partial in zip(counts, partials)]
            item = ContextItem(self.items, [row.get("name", row["kind"]), row["kind"], *labels])
            item.setData(1, Qt.ItemDataRole.UserRole, row["kind"])
            counts_text = "\n".join(f"{label} · {size}" for label, size in zip(self.item_labels(), labels))
            detail = row.get("detail") or ("Saved counts. Measure to refresh the detailed item breakdown." if result.get("cached") else "")
            item.setToolTip(0, f"{row.get('name', row['kind'])}\n{counts_text}" + (f"\n\n{detail}" if detail else ""))
            for index, size in enumerate(counts, 2):
                item.setData(index, Qt.ItemDataRole.UserRole, size)
        self.items.setSortingEnabled(True)
        self.items.sortItems(max(0, column), order)
        self.filter_items()

    def item_labels(self):
        return [self.items.headerItem().text(column) for column in range(2, self.items.columnCount())]

    def filter_items(self):
        query = self.search.text().strip().casefold()
        kind = self.kind.currentData()
        for index in range(self.items.topLevelItemCount()):
            item = self.items.topLevelItem(index)
            item.setHidden((bool(kind) and item.data(1, Qt.ItemDataRole.UserRole) != kind)
                           or (bool(query) and query not in item.text(0).casefold()))
