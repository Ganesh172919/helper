"""Local inspection of prepared context; this dialog never reads credentials or calls a provider."""

from io import BytesIO
import json

from PIL import Image
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from maya.core.config import PROVIDERS
from maya.core.context import AnswerContext
from maya.core.routing import CLASSIFIER_RULES
from maya.core.safety import redact
from .branding import MayaMark
from .capture_ui import ImagePreview
from .widgets import button, label


class ContextReview(QDialog):
    """Read-only prepared text/image and optional classifier inputs, with explicit stage-specific consent."""

    def __init__(
        self,
        context: AnswerContext,
        endpoint: str,
        provider: str,
        routing_payload: dict | None = None,
        routing_model: str = "",
        note: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.context = context
        self.setWindowTitle("Review request context — Maya")
        self.resize(680, 590)
        self.setMinimumSize(480, 400)
        outer = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(MayaMark(36))
        heading.addWidget(label("Know what you're sending", "heading"), 1)
        outer.addLayout(heading)
        outer.addWidget(
            label("Local preview · no credentials are read and no request is made by opening this view.")
        )
        self.stage = label(
            "Gemini routing may change the skill and included memories. Route first, then review the final answer context."
            if routing_payload is not None
            else note or "This is the prepared answer context. Your draft is kept if you cancel."
        )
        outer.addWidget(self.stage)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        request = context.request
        earlier = len(request.messages) - 1
        omitted = max(0, context.history_total - earlier)
        self.answer_text = self.text_tab(
            "Answer",
            (
                f"Provider: {PROVIDERS[provider]}\nAPI base URL: {endpoint}\nModel ID: {request.model.id}\n"
                f"Skill: {context.skill.name}\nEarlier messages included: {earlier}; omitted: {omitted}\n"
                f"Temperature: {request.temperature}; maximum output tokens: {request.max_output}\n\n"
                "QUESTION AND INCLUDED HISTORY\n\n"
                + "\n\n".join(f"{m.role.upper()}\n{m.text}" for m in request.messages)
                + "\n\nAPPROVED MEMORIES FOR THIS ANSWER\n"
                + ("\n".join("• " + redact(item)[0] for item in context.memories) or "None")
                + (
                    "\n\nA reviewed screenshot is attached; inspect it in the Screenshot tab."
                    if request.messages[-1].image
                    else "\n\nNo screenshot is included."
                )
            ),
        )
        self.system_text = self.text_tab("Instructions", request.system)
        self.routing_text = None
        if routing_payload is not None:
            self.routing_text = self.text_tab(
                "Gemini routing",
                (
                    "A separate Gemini call is possible if a Gemini key is configured. It may cost money or quota.\n"
                    "Screenshots, answer history, approved memories and name/language/style settings are excluded.\n"
                    "Profile names and brief instructions, including saved custom profiles, are included below.\n"
                    "Discovery may be needed before classification. The actual accessible model is selected on routing.\n"
                    f"Requested routing model: {routing_model or 'Auto · from the discovered Gemini catalog'}\n"
                    "Temperature: 0; output limit: up to 1,024 tokens, bounded by the discovered model.\n"
                    "Output: allowlisted skill_id and confidence only.\n\nCLASSIFIER INSTRUCTIONS\n"
                    + CLASSIFIER_RULES
                    + "\n\nPLANNED CLASSIFIER CONTEXT\n"
                    + json.dumps(routing_payload, indent=2, ensure_ascii=False)
                ),
            )
        self.image = request.messages[-1].image
        if self.image:
            page = QWidget()
            box = QVBoxLayout(page)
            box.addWidget(
                label(
                    f"Reviewed image · {self.image.width} × {self.image.height} · {len(self.image.data):,} bytes\n"
                    "These are the image bytes attached to this request. They are not saved by this preview."
                )
            )
            pixmap = QPixmap()
            pixmap.loadFromData(self.image.data)
            preview = QLabel()
            preview.setAlignment(Qt.AlignCenter)
            preview.setPixmap(pixmap.scaled(540, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            box.addWidget(preview, 1)
            box.addWidget(button("Inspect full screenshot", self.inspect_image))
            self.tabs.addTab(page, "Screenshot")
        row = QHBoxLayout()
        keep_editing = button("Keep editing", self.reject)
        keep_editing.setAutoDefault(False)
        row.addWidget(keep_editing)
        row.addStretch()
        self.proceed = button(
            "Route with Gemini & review" if routing_payload is not None else "Send this context",
            self.accept,
            True,
        )
        self.proceed.setAutoDefault(False)
        row.addWidget(self.proceed)
        outer.addLayout(row)

    def keyPressEvent(self, event) -> None:
        """Reading context with Enter cannot accept a paid request; focus the action for keyboard consent."""
        if event.key() in {Qt.Key_Return, Qt.Key_Enter}:
            if self.focusWidget() is self.proceed:
                self.accept()
            event.accept()
            return
        super().keyPressEvent(event)

    def text_tab(self, title: str, text: str) -> QPlainTextEdit:
        """Plain text stays selectable but cannot interpret markup or fetch local/remote resources."""
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setAccessibleName(title + " request context")
        editor.setPlainText(text)
        self.tabs.addTab(editor, title)
        return editor

    def inspect_image(self) -> None:
        """Display the same immutable image without editing it or acquiring fresh screen pixels."""
        try:
            ImagePreview(Image.open(BytesIO(self.image.data)).copy(), editable=False, parent=self).exec_()
        except (OSError, ValueError):
            QMessageBox.information(self, "Screenshot", "This prepared image could not be displayed.")
