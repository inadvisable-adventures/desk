from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desk.installed_jobs import INSTALLED_JOBS_UPDATED_EVENT, installed_job_dir
from desk.shell import current_context
from desk.shell.event_broker import EventSubscription

ITEM_LIST_STYLE = """
QListWidget::item {
    border: 1px solid #888;
    border-radius: 4px;
    padding: 0px;
}
"""
ITEM_LIST_SPACING = 3
ROW_BUTTON_WIDTH = 90


class InstalledJobsWidget(QWidget):
    """Lists the current Desk's Installed Jobs (TODO 7dca383) --
    durable, versioned, agent-authored jobs registered via the
    desk_install_job MCP tool (desk.shell.desk_mcp_server), as opposed
    to a one-shot tempui-DSL Job. Mirrors
    widgets/parking_lot/widget.py's per-row QListWidget/setItemWidget
    shape. Each row's "View Source" opens an editor widget instance
    (current_context.get_editor_or_scrap_opener(), the same service
    JobRunnerWidget's own "View Code" button already calls) for every
    file under that job's own desk-installed-jobs/<name>/ directory;
    "Uninstall" confirms (current_context.get_popup_opener()) before
    unregistering it (current_context.get_installed_job_uninstaller())
    -- the job's source is left on disk either way, only the
    registration is removed."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._jobs: list[dict] = []

        self._status_label = QLabel()
        self._status_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self._list.setStyleSheet(ITEM_LIST_STYLE)
        self._list.setSpacing(ITEM_LIST_SPACING)

        layout = QVBoxLayout(self)
        layout.addWidget(self._list, stretch=1)
        layout.addWidget(self._status_label)

        self._subscription: EventSubscription | None = None

        self.reload()

    def reload(self) -> None:
        provider = current_context.get_installed_jobs_provider()
        self._jobs = provider() if provider is not None else []
        self._populate_list()

    def bind_event_mediator(self, instance_id: str, mediator) -> None:
        """TODO 7dca383: opts into DeskWindow._bind_event_mediator's
        generic per-placed-python-widget hook (TODO 6f9c51b) to stay
        current after an install/uninstall that happened elsewhere
        (e.g. an MCP tool call) -- the published event's own payload
        carries the new registry directly, mirroring
        widgets/project_files/widget.py's own
        FILE_TYPE_REGISTRY_UPDATED_EVENT subscription."""
        self._subscription = EventSubscription(
            mediator, instance_id, names=[INSTALLED_JOBS_UPDATED_EVENT], parent=self
        )
        self._subscription.message_received.connect(self._on_mediated_event)

    def _on_mediated_event(self, name: str, payload: object, _sender_instance_id: str) -> None:
        if name == INSTALLED_JOBS_UPDATED_EVENT and isinstance(payload, dict):
            self._jobs = payload.get("jobs", [])
            self._populate_list()

    def _populate_list(self) -> None:
        self._list.clear()
        if not self._jobs:
            self._status_label.setText("No installed jobs.")
        else:
            self._status_label.setText(f"{len(self._jobs)} installed.")
        for job in self._jobs:
            list_item = QListWidgetItem()
            row = self._build_row(job)
            list_item.setSizeHint(row.sizeHint())
            self._list.addItem(list_item)
            self._list.setItemWidget(list_item, row)

    def _build_row(self, job: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        label = QLabel(f"{job['name']}  [{job.get('kind', 'python')}]  ({job['version_hash']})")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(label, 1)

        view_source_button = QPushButton("View Source")
        view_source_button.setFixedWidth(ROW_BUTTON_WIDTH)
        view_source_button.clicked.connect(lambda checked=False, name=job["name"]: self._view_source(name))
        layout.addWidget(view_source_button, 0, Qt.AlignmentFlag.AlignVCenter)

        uninstall_button = QPushButton("Uninstall")
        uninstall_button.setFixedWidth(ROW_BUTTON_WIDTH)
        uninstall_button.clicked.connect(lambda checked=False, name=job["name"]: self._uninstall(name))
        layout.addWidget(uninstall_button, 0, Qt.AlignmentFlag.AlignVCenter)

        return row

    def _view_source(self, name: str) -> None:
        directory = current_context.get_current_desk_directory()
        opener = current_context.get_editor_or_scrap_opener()
        if directory is None or opener is None:
            return
        job_dir = installed_job_dir(directory, name)
        # TODO 94a2fa2: skip a rust-kind job's own cargo target/ build
        # output -- opening every build artifact file one at a time
        # (potentially thousands, after a first build) is never useful
        # here the way opening the job's own real source files is.
        for path in sorted(p for p in job_dir.rglob("*") if p.is_file()):
            if "target" in path.relative_to(job_dir).parts[:-1]:
                continue
            opener(path)

    def _uninstall(self, name: str) -> None:
        popup_opener = current_context.get_popup_opener()
        if popup_opener is not None:
            answer = popup_opener(
                "Uninstall Job",
                f"Uninstall {name!r}? Its source under desk-installed-jobs/ is kept -- "
                "you can reinstall it later.",
                ["Uninstall", "Cancel"],
                "Cancel",
            )
            if answer != "Uninstall":
                return
        uninstaller = current_context.get_installed_job_uninstaller()
        if uninstaller is not None:
            uninstaller(name)


def build() -> QWidget:
    return InstalledJobsWidget()
