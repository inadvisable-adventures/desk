from datetime import datetime

from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


def build() -> QWidget:
    container = QWidget()
    container.setStyleSheet("background-color: #24272b;")

    layout = QVBoxLayout(container)

    timestamp = datetime.now().strftime("%H:%M:%S")
    label = QLabel(f"Desk demo widget (Python/Qt) — rendered {timestamp}")
    label.setStyleSheet("color: #e8e8e8; padding: 1rem;")
    layout.addWidget(label)

    return container
