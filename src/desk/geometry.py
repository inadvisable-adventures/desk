from PyQt6.QtCore import QRectF, QSizeF


def fit_rect(content_size: QSizeF, container_size: QSizeF) -> QRectF:
    """A centered rect scaling `content_size` to fit within
    `container_size` while preserving aspect ratio (letterboxed on
    whichever axis has slack). Shared by `widgets/svg_viewer/widget.py`
    and `widgets/image_viewer/widget.py`, whose own custom-`paintEvent`
    renderers both need the same "no distortion, centered" scaling that
    a naive `QLabel.setScaledContents(True)`/`QSvgWidget` default
    doesn't give (both stretch non-uniformly to fill their rect,
    confirmed directly while planning the SVG viewer)."""
    if (
        content_size.width() <= 0
        or content_size.height() <= 0
        or container_size.width() <= 0
        or container_size.height() <= 0
    ):
        return QRectF(0, 0, container_size.width(), container_size.height())
    scale = min(
        container_size.width() / content_size.width(),
        container_size.height() / content_size.height(),
    )
    width = content_size.width() * scale
    height = content_size.height() * scale
    x = (container_size.width() - width) / 2
    y = (container_size.height() - height) / 2
    return QRectF(x, y, width, height)
