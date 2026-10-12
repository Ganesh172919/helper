"""Plain-text boundaries for dynamic native UI hints."""

from html import escape
from PyQt5.QtWidgets import QWidget


def safe_tooltip(widget: QWidget, text: str) -> None:
    """Escape dynamic markup so Qt AutoText cannot load provider/user supplied image resources."""
    widget.setToolTip(
        "<qt>" + escape(text).replace("\n", "<br/>") + "</qt>"
        if any(character in text for character in "<>&")
        else text
    )
