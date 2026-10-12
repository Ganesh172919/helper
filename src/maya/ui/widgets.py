"""Shared chat widgets, a restrained native theme, and a procedural Maya flower icon."""

import re

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize, QUrl
from PyQt5.QtGui import QDesktopServices, QFont, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QLayout,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from maya.core.types import Message
from .branding import MayaMark, maya_icon as maya_icon
from .text import safe_tooltip


# --- Theme and icon are code-native assets: no downloaded art or browser frontend. ---
STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 13px; color: #253f37; }
QMainWindow, QDialog, QWidget#canvas, QWidget#settingsPage { background: #f8f6ef; }
QWidget#floatingShell { background: transparent; }
QWidget#sidebar { background: #e9eee4; border-right: 1px solid #d8e0d1; }
QWidget#compactPanel { background: #f8f6ef; border: 1px solid #bbcdbf; border-radius: 16px; }
QLabel#brand { font-family: 'Georgia'; font-size: 29px; font-weight: 600; color: #214f43; }
QLabel#heading { font-size: 22px; font-weight: 600; }
QLabel#welcomeTitle { font-family: 'Georgia'; font-size: 23px; font-weight: 600; color: #254f43; }
QLabel#muted { color: #64756b; }
QLabel#eyebrow { color: #657466; font-size: 11px; font-weight: 600; }
QLabel#signature { color: #94753f; font-size: 10px; letter-spacing: 1px; }
QLabel#sectionTitle { font-family: 'Georgia'; font-size: 20px; font-weight: 600; color: #254f43; }
QFrame#setupStep { background: #eef1e7; border: 1px solid #dce3d4; border-radius: 10px; }
QFrame#settingsCard { background: #fffef9; border: 1px solid #d9e0d2; border-radius: 12px; }
QLabel#statusCapsule { color: #536d5c; font-size: 11px; padding: 4px 6px; border-radius: 6px; }
QLabel#statusCapsule[phase="error"] { background: #f4e4db; color: #864531; }
QLabel#statusCapsule[phase="thinking"], QLabel#statusCapsule[phase="capturing"] { background: #f2e9ce; color: #705924; }
QLabel#statusCapsule[phase="streaming"] { background: #e5efe5; color: #365e49; }
QLabel#notice { background: #efe8d8; color: #625238; padding: 9px; border-radius: 8px; }
QPushButton#notice { background: #f3ead6; color: #705a31; border-color: #e4d4ae; }
QPushButton { background: #f1f2e9; border: 1px solid #d9e0d3; border-radius: 9px;
              padding: 5px 9px; min-height: 18px; }
QPushButton#iconButton { background: transparent; border: 1px solid transparent; padding: 3px; }
QPushButton#quiet { background: transparent; border: 1px solid transparent; color: #5a7060; padding: 3px 6px; min-height: 16px; }
QPushButton#quiet:hover, QPushButton#iconButton:hover { background: #e8edde; border-color: #d2dcc9; }
QPushButton#quiet:focus, QPushButton#iconButton:focus { background: #edf3e5; border-color: #62906b; }
QWidget#compactPanel QPushButton { padding: 3px 6px; }
QWidget#compactPanel QComboBox { padding: 4px; }
QPushButton#promptChip { background: #fffdf5; border: 1px solid #e4dbc4; color: #76613d; padding: 5px 8px; }
QPushButton#promptChip:hover { background: #f3ebd8; border-color: #c8b382; }
QPushButton#promptChip:focus { border-color: #8ba575; }
QPushButton[needsSetup="true"] { background: #f4ecd7; border-color: #ddc997; color: #725b2d; }
QPushButton#contextToggle[screenEnabled="true"] { background: #e0eddf; border-color: #83a78a; color: #2f5c41; }
QPushButton:hover { background: #e8edde; border-color: #a9beaa; }
QPushButton:pressed { background: #d6e3d2; }
QPushButton:disabled { color: #939d91; background: #f0f1eb; border-color: #e2e6dc; }
QPushButton#primary { background: #23594b; border-color: #23594b; color: #ffffff; font-weight: 600; }
QPushButton#primary:hover { background: #184739; border-color: #184739; }
QPushButton#primary:focus { background: #1e5243; border-color: #a8c5a2; }
QPushButton#primary:pressed { background: #123b30; }
QPushButton#primary:disabled { background: #d8ddd2; border-color: #d8ddd2; color: #8a968a; }
QPushButton#danger { color: #934b3b; }
QPushButton#danger:disabled { color: #909991; }
QPushButton:checked { background: #e0eddf; border-color: #83a78a; color: #2f5c41; }
QPlainTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget {
    background: #fffef9; border: 1px solid #d9e0d2; border-radius: 8px; padding: 6px;
    selection-background-color: #c7e0cf; selection-color: #153d33; }
QPlainTextEdit:focus, QLineEdit:focus, QComboBox:focus, QPushButton:focus { border-color: #62906b; }
QComboBox:disabled { color: #98a191; background: #f1f2ec; }
QFrame#composeWell { background: #fffef9; border: 1px solid #d1dccb; border-radius: 14px; }
QFrame#composeWell[focused="true"] { border-color: #709c78; background: #fffffa; }
QPlainTextEdit#questionInput { background: transparent; border: none; padding: 4px 3px; }
QComboBox::drop-down { width: 24px; border: none; }
QTextBrowser { background: transparent; border: none; font-size: 14px; }
QScrollArea { border: none; background: transparent; }
QWidget#chatContent { background: #f8f6ef; }
QFrame#assistantCard { background: #fffef9; border: 1px solid #e4dece; border-radius: 13px; }
QFrame#userCard { background: #e8eee3; border: 1px solid #d9e3d1; border-radius: 13px; }
QMenu { background: #fffdf5; border: 1px solid #d3deca; border-radius: 8px; padding: 6px; }
QMenu::item { padding: 7px 22px 7px 12px; border-radius: 5px; }
QMenu::item:selected { background: #e4eddf; color: #254f3c; }
QMenu::separator { height: 1px; background: #e4e6da; margin: 5px 8px; }
QTabWidget::pane { border: 1px solid #d9e0d2; border-radius: 8px; }
QTabBar::tab { background: #eef1e7; padding: 9px 14px; border: 1px solid #d9e0d2; }
QTabBar::tab:selected { background: #fffef9; color: #23594b; border-bottom-color: #fffef9; }
QGroupBox { border: 1px solid #d9ddd0; border-radius: 8px; margin-top: 14px; padding-top: 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; }
QStatusBar { background: #f8f6ef; color: #6a7b6b; font-size: 11px; border-top: 1px solid #e6e8dd; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 2px 0; }
QScrollBar::handle:vertical { background: #c4cfbd; border-radius: 3px; min-height: 26px; }
QScrollBar::handle:vertical:hover { background: #9fb39b; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: #fffdf5; border: 1px solid #b9c8ac; color: #253f37; padding: 7px; }
"""


def button(text: str, callback=None, primary: bool = False) -> QPushButton:
    """Create a keyboard-focusable button with optional action and primary styling."""
    result = QPushButton(text)
    result.setCursor(Qt.PointingHandCursor)
    if primary:
        result.setObjectName("primary")
    if callback:
        result.clicked.connect(callback)
    return result


class CredentialEdit(QLineEdit):
    """Only typed credentials can be revealed; losing focus or hiding asks the owner to mask again."""

    conceal_requested = pyqtSignal()

    def focusOutEvent(self, event) -> None:
        self.conceal_requested.emit()
        super().focusOutEvent(event)

    def hideEvent(self, event) -> None:
        self.conceal_requested.emit()
        super().hideEvent(event)


def label(text: str, name: str = "muted") -> QLabel:
    """Create a wrapping label; plain text prevents user-controlled rich text injection."""
    result = QLabel(text)
    result.setTextFormat(Qt.PlainText)
    result.setObjectName(name)
    result.setWordWrap(True)
    return result


class ElidingLabel(QLabel):
    """A one-line status that fits the work area while preserving the full accessible explanation."""

    def __init__(self, text: str, name: str):
        super().__init__()
        self.full_text = ""
        self.setObjectName(name)
        self.setTextFormat(Qt.PlainText)
        self.setWordWrap(False)
        self.setAccessibleName("Maya status")
        self.setText(text)

    def setText(self, text: str) -> None:
        """Truncation affects only painting, never the tooltip or assistive-technology description."""
        self.full_text = text
        safe_tooltip(self, text)
        self.setAccessibleDescription(text)
        self.fit_text()

    def fit_text(self) -> None:
        """Leave space for the capsule's horizontal padding; Qt handles proportional/Unicode text."""
        super().setText(
            self.fontMetrics().elidedText(self.full_text, Qt.ElideRight, max(16, self.width() - 12))
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_text()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "full_text"):
            self.fit_text()


# --- Conversation rendering blocks resource loads and opens only explicitly clicked web links. ---
class SafeBrowser(QTextBrowser):
    """Qt Markdown viewer with no remote/local embedded resource loading."""

    def __init__(self):
        """Disable automatic links and scrollbars; the enclosing conversation owns scrolling."""
        super().__init__()
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.anchorClicked.connect(self.open_link)
        self.setFont(QFont("Segoe UI", 11))

    def loadResource(self, resource_type, url):
        """Reject embedded image/resource loads, including local file URLs in provider Markdown."""
        return None

    def open_link(self, url: QUrl) -> None:
        """Open only user-clicked HTTP(S) links; file, script, and application schemes are ignored."""
        if (
            url.isValid()
            and url.host()
            and len(url.toString()) <= 4096
            and url.scheme() in {"https", "http"}
            and not url.userName()
            and not url.password()
        ):
            QDesktopServices.openUrl(url)

    def set_content(self, text: str, markdown: bool) -> None:
        """Update text and height, retaining selectable code and Markdown tables."""
        if markdown:
            self.setMarkdown(text)
        else:
            self.setPlainText(text)
        self.fit_height()

    def fit_height(self) -> None:
        """Size to the document after wrapping; a hard bound protects Qt against enormous layouts."""
        self.document().setTextWidth(max(120, self.viewport().width()))
        height = max(38, int(self.document().size().height()) + 14)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if height > 30000 else Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(min(30000, height))

    def resizeEvent(self, event) -> None:
        """Reflow the text at the new panel width without changing content."""
        super().resizeEvent(event)
        self.fit_height()


class MessageCard(QFrame):
    """One selectable turn with status, optional in-memory screenshot, and explicit copy/feedback actions."""

    rate = pyqtSignal(object, int)

    def __init__(self, message: Message):
        """Build a message card; the shared Message instance is updated by the controller."""
        super().__init__()
        self.message = message
        self.setObjectName("userCard" if message.role == "user" else "assistantCard")
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(12, 10, 12, 10)
        row = QHBoxLayout()
        self.title = label("YOU" if message.role == "user" else "MAYA", "eyebrow")
        row.addWidget(self.title)
        row.addStretch()
        copy = button("Copy", self.copy)
        copy.setObjectName("quiet")
        copy.setToolTip("Copy this message")
        row.addWidget(copy)
        if message.role == "assistant":
            feedback = button("Rate")
            feedback.setObjectName("quiet")
            feedback.setAccessibleName("Feedback for this answer")
            feedback.setToolTip("Was this helpful? Save feedback locally")
            menu = QMenu(feedback)
            menu.addAction("Helpful", lambda: self.rate.emit(self.message, 1))
            menu.addAction("Needs work", lambda: self.rate.emit(self.message, -1))
            feedback.setMenu(menu)
            row.addWidget(feedback)
        self.box.addLayout(row)
        if message.image:
            preview = button("Screenshot", self.preview)
            preview.setToolTip(f"{message.image.width} × {message.image.height} · Click to view")
            preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            preview.setMinimumWidth(120)
            pixmap = QPixmap()
            pixmap.loadFromData(message.image.data)
            # Keep small decoded thumbnails rather than full-resolution pixmaps in both chat surfaces.
            preview.setIcon(QIcon(pixmap.scaled(144, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            preview.setIconSize(QSize(72, 45))
            self.box.addWidget(preview)
        self.body = SafeBrowser()
        self.box.addWidget(self.body)
        self.code_row = QHBoxLayout()
        self.box.addLayout(self.code_row)
        self.copy_code = button("Copy code")
        self.copy_code.hide()
        self.code_menu = QMenu(self.copy_code)
        self.copy_code.setMenu(self.code_menu)
        self.code_row.addWidget(self.copy_code)
        self.code_row.addStretch()
        self.status = label("", "eyebrow")
        self.box.addWidget(self.status)
        self.refresh()

    def copy(self) -> None:
        """Copy this answer only on a user action; no automatic clipboard updates or insertion."""
        QApplication.clipboard().setText(self.message.text)

    def preview(self) -> None:
        """Show an already-approved attachment in a larger local dialog."""
        from .capture_ui import ImagePreview
        from PIL import Image
        from io import BytesIO

        dialog = ImagePreview(
            Image.open(BytesIO(self.message.image.data)).copy(), editable=False, parent=self
        )
        dialog.exec_()

    def refresh(self) -> None:
        """Render the latest buffered text; copy-code controls appear once a response is final."""
        text = self.message.text or (
            "Thinking…" if self.message.status == "streaming" else "No response text."
        )
        self.body.set_content(text, self.message.role == "assistant")
        self.status.setText("" if self.message.status == "complete" else self.message.status.upper())
        self.status.setVisible(self.message.status != "complete")
        if self.message.status != "streaming" and not self.code_menu.actions():
            for index, match in enumerate(re.finditer(r"```([^\n]*)\n([\s\S]*?)```", self.message.text)):
                code = match.group(2)
                self.code_menu.addAction(
                    f"{match.group(1).strip()[:24] or 'Code'} · block {index + 1}",
                    lambda checked=False, value=code: QApplication.clipboard().setText(value),
                )
                if index >= 49:
                    break  # Whole-answer Copy retains every block; keep the menu bounded.
            self.copy_code.setVisible(bool(self.code_menu.actions()))


class ChatView(QWidget):
    """A vertical conversation that follows streaming until the user scrolls upward."""

    rated = pyqtSignal(object, int)
    prompt_chosen = pyqtSignal(str)

    def __init__(self, compact: bool = False):
        """Create the scroll surface and useful first-run empty state."""
        super().__init__()
        layout = QVBoxLayout(self)
        # The viewport yields space to capture/error controls, keeping the outer panel stable.
        layout.setSizeConstraint(QLayout.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.setMinimumHeight(36)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.scroll.setWidgetResizable(True)
        self.content = QWidget()
        self.content.setObjectName("chatContent")
        self.box = QVBoxLayout(self.content)
        self.box.setContentsMargins(4 if compact else 8, 8, 4 if compact else 8, 8)
        self.box.setSpacing(10)
        self.box.addStretch()
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)
        self.jump = button("↓ Jump to latest", self.latest)
        self.jump.hide()
        layout.addWidget(self.jump)
        self.cards: list[MessageCard] = []
        self.follow = True
        self.programmatic = False
        self.scroll.verticalScrollBar().valueChanged.connect(self.scrolled)
        self.empty = QWidget()
        empty_box = QVBoxLayout(self.empty)
        empty_box.setContentsMargins(8, 6, 8, 4)
        empty_box.setSpacing(6)
        mark = MayaMark(48 if compact else 64)
        empty_box.addWidget(mark, 0, Qt.AlignHCenter)
        title = label("A little clarity, right here." if not compact else "Need a hand?", "welcomeTitle")
        if compact:
            title.setStyleSheet("font-size: 18px;")
        title.setAlignment(Qt.AlignCenter)
        description = label(
            "A command, a formula, an unfamiliar idea.\nBring the question. We'll find the next step."
        )
        description.setAlignment(Qt.AlignCenter)
        self.hint = label("")
        self.hint.setAlignment(Qt.AlignCenter)
        self.set_model_state(False, False, False)
        empty_box.addWidget(title)
        empty_box.addWidget(description)
        empty_box.addWidget(self.hint)
        # Friendly entry points fill a draft; they never capture a screen or submit a request.
        if not compact:
            prompts = QHBoxLayout()
            for name, question in (
                ("A command", "Help me understand this command: "),
                ("A formula", "Help me understand this Excel formula: "),
                ("An idea", "Explain this idea with a simple example: "),
            ):
                chip = button(name, lambda checked=False, text=question: self.prompt_chosen.emit(text))
                chip.setObjectName("promptChip")
                prompts.addWidget(chip)
            empty_box.addLayout(prompts)
        self.box.insertWidget(0, self.empty)

    def set_model_state(self, available: bool, selected: bool, screen_enabled: bool) -> None:
        """Keep the welcome guidance accurate as setup, selection and screen consent change."""
        next_step = (
            "Your model is ready. Ask in your own words."
            if selected
            else "Choose a model above to begin."
            if available
            else "Set up your model above to begin."
        )
        screen = (
            "Review each screenshot before sending."
            if screen_enabled
            else "Your screen is off. You're in control."
        )
        self.hint.setText(next_step + "\n" + screen)

    def scrolled(self, value: int) -> None:
        """Stop follow-scroll when the user moves away from the bottom."""
        if not self.programmatic:
            self.follow = value >= self.scroll.verticalScrollBar().maximum() - 40
            self.jump.setVisible(not self.follow)

    def latest(self) -> None:
        """Explicitly resume following the newest output."""
        self.follow = True
        self.programmatic = True
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())
        self.programmatic = False
        self.jump.hide()

    def add(self, message: Message) -> None:
        """Append one turn and connect feedback without duplicating conversation state."""
        self.empty.hide()
        card = MessageCard(message)
        card.rate.connect(self.rated)
        self.cards.append(card)
        self.box.insertWidget(self.box.count() - 1, card)
        if self.follow:
            QTimer.singleShot(0, self.latest)

    def refresh_last(self) -> None:
        """Repaint only the currently streaming card, at the controller's bounded timer rate."""
        if self.cards:
            following = self.follow
            self.programmatic = True
            self.cards[-1].refresh()
            self.programmatic = False
            if following:
                QTimer.singleShot(0, self.latest)

    def load(self, messages: list[Message]) -> None:
        """Replace the visible conversation when history/new chat is selected."""
        for card in self.cards:
            self.box.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self.empty.setVisible(not messages)
        self.follow = True
        for message in messages:
            self.add(message)


class Composer(QPlainTextEdit):
    """Accessible multiline question input: Enter submits; Shift+Enter inserts a newline."""

    submit = pyqtSignal()
    focus_changed = pyqtSignal(bool)

    def __init__(self):
        """Provide a compact input without replacing standard editing shortcuts."""
        super().__init__()
        self.setObjectName("questionInput")
        self.setPlaceholderText("Ask about what you're working on…")
        self.setAccessibleName("Question for Maya")
        self.setAccessibleDescription("Enter to send. Shift+Enter adds a new line.")
        self.setToolTip("Enter to send · Shift+Enter for a new line")
        self.setFixedHeight(94)

    def focusInEvent(self, event) -> None:
        """Let the surrounding composer show one clear focus boundary for keyboard users."""
        super().focusInEvent(event)
        self.focus_changed.emit(True)

    def focusOutEvent(self, event) -> None:
        """Return to the quiet resting border without changing or submitting the draft."""
        super().focusOutEvent(event)
        self.focus_changed.emit(False)

    def keyPressEvent(self, event) -> None:
        """Submit only an unmodified Enter so multiline/editing shortcuts behave predictably."""
        if event.key() in {Qt.Key_Return, Qt.Key_Enter} and event.modifiers() == Qt.NoModifier:
            self.submit.emit()
        else:
            super().keyPressEvent(event)
