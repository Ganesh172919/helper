"""Normal and compact chat surfaces plus the draggable, non-activating Maya orb."""

import math

from PyQt5.QtCore import Qt, QPoint, QTimer, QEvent, QRectF, QSize
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from maya.core.config import PROVIDERS
from .widgets import ChatView, Composer, ElidingLabel, button, label, safe_tooltip
from .branding import MayaMark, paint_maya
from .icons import line_icon


# --- One set of dimensions keeps startup, restore, resize and tests in agreement. ---
MAIN_SIZE, MAIN_MIN = (480, 560), (400, 450)
MINI_SIZE, MINI_MIN = (360, 440), (320, 360)


# --- Both chat surfaces subscribe to the same controller state. ---
class ChatPanel(QWidget):
    """Shared conversation/composer UI used by the full window and compact overlay."""

    def __init__(self, controller, compact: bool = False):
        """Build context controls and subscribe to bounded update signals."""
        super().__init__()
        self.controller = controller
        self.compact = compact
        if compact:
            self.setObjectName("compactPanel")
            # Custom QWidget subclasses need styled-background painting on a transparent tool window.
            self.setAttribute(Qt.WA_StyledBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8 if compact else 10, 8, 8 if compact else 10, 8)
        layout.setSpacing(6 if compact else 8)
        title = QHBoxLayout()
        title.setSpacing(5)
        if not compact:
            self.navigation = button("", lambda: controller.main.toggle_navigation())
            self.navigation.setIcon(line_icon("navigation"))
            self.navigation.setIconSize(QSize(16, 16))
            self.navigation.setFixedSize(28, 28)
            self.navigation.setAccessibleName("Toggle navigation")
            self.navigation.setToolTip("Show or hide navigation")
            self.navigation.setObjectName("iconButton")
            title.addWidget(self.navigation)
        self.mark = MayaMark(32 if compact else 40)
        title.addWidget(self.mark)
        identity = QVBoxLayout()
        identity.setSpacing(0)
        identity.addWidget(label("Maya", "heading"))
        if not compact:
            identity.addWidget(label("BY YOUR SIDE", "signature"))
        title.addLayout(identity)
        title.addStretch()
        title.addWidget(
            button(
                "Full" if compact else "Float",
                controller.show_normal if compact else controller.show_overlay,
            )
        )
        if compact:
            collapse = button("", controller.collapse)
            collapse.setObjectName("iconButton")
            collapse.setIcon(line_icon("close"))
            collapse.setFixedSize(26, 26)
            collapse.setAccessibleName("Collapse quick panel")
            collapse.setToolTip("Collapse quick panel · Esc")
            title.addWidget(collapse)
        else:
            self.pin = button("Pin", controller.toggle_pin)
            self.pin.setCheckable(True)
            self.pin.setAccessibleName("Keep Maya on top")
            self.pin.setToolTip("Keep the main Maya window above other applications")
            title.addWidget(self.pin)
            settings_button = button("", controller.open_settings)
            settings_button.setIcon(line_icon("settings"))
            settings_button.setIconSize(QSize(16, 16))
            settings_button.setFixedSize(28, 28)
            settings_button.setObjectName("iconButton")
            settings_button.setAccessibleName("Settings")
            settings_button.setToolTip("Settings & memory")
            title.addWidget(settings_button)
        layout.addLayout(title)
        controls = QHBoxLayout()
        self.skill = QComboBox()
        self.skill.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.skill.setMinimumContentsLength(8)
        self.skill.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.skill.setMinimumWidth(86 if compact else 100)
        self.skill.setToolTip("Choose a task profile, or let Auto infer the task")
        self.skill.currentIndexChanged.connect(self.change_skill)
        controls.addWidget(self.skill, 1)
        self.model = button("Choose model", self.choose_model)
        self.model.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.model.setMinimumWidth(86 if compact else 100)
        controls.addWidget(self.model, 1)
        self.context_toggle = button("Screen OFF", self.toggle_capture_controls)
        self.context_toggle.setObjectName("contextToggle")
        self.context_toggle.setCheckable(True)
        self.context_toggle.setAccessibleName("Expand screen capture controls")
        self.context_toggle.setToolTip(
            "Show screen switch, capture scope and Capture; this does not take a screenshot"
        )
        controls.addWidget(self.context_toggle)
        layout.addLayout(controls)
        self.capture_controls = QWidget()
        capture_row = QHBoxLayout(self.capture_controls)
        capture_row.setContentsMargins(0, 0, 0, 0)
        capture_row.setSpacing(6)
        self.screen = button("Screen: OFF", controller.toggle_screen)
        self.screen.setCheckable(True)
        capture_row.addWidget(self.screen)
        self.scope = QComboBox()
        self.scope.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.scope.setMinimumContentsLength(8)
        self.scope.setMinimumWidth(76 if compact else 100)
        self.scope.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        for title, identifier in (
            ("Current monitor", "monitor"),
            ("All monitors", "all"),
            ("Active window", "window"),
            ("Select region", "region"),
            ("Last capture", "last"),
        ):
            self.scope.addItem(title, identifier)
        self.scope.setCurrentIndex(max(0, self.scope.findData(controller.settings.capture_scope)))
        self.scope.currentIndexChanged.connect(self.change_scope)
        capture_row.addWidget(self.scope, 1)
        self.capture = button("Capture", controller.capture_screen)
        capture_row.addWidget(self.capture)
        layout.addWidget(self.capture_controls)
        self.capture_controls.hide()
        self.view = ChatView(compact)
        self.view.rated.connect(controller.feedback)
        self.view.prompt_chosen.connect(controller.set_question)
        layout.addWidget(self.view, 1)
        self.notice_text = ""
        self.notice = button("Notice · Read details", self.notice_details)
        self.notice.setObjectName("notice")
        self.notice.setMaximumHeight(40)
        self.notice.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.notice.hide()
        layout.addWidget(self.notice)
        self.attachment = button("", controller.preview_pending)
        self.attachment.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.attachment.setMinimumWidth(100)
        self.attachment.hide()
        self.remove_attachment = button("Remove", controller.remove_attachment)
        self.remove_attachment.setToolTip("Remove the screenshot from future requests")
        self.remove_attachment.hide()
        attachment_row = QHBoxLayout()
        attachment_row.addWidget(self.attachment, 1)
        attachment_row.addWidget(self.remove_attachment)
        layout.addLayout(attachment_row)
        # One paper-like input well groups drafting and its actions without adding another toolbar.
        self.compose_well = QFrame()
        self.compose_well.setObjectName("composeWell")
        self.compose_well.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        compose_layout = QVBoxLayout(self.compose_well)
        compose_layout.setContentsMargins(6 if compact else 8, 5, 6 if compact else 8, 6)
        compose_layout.setSpacing(3)
        self.composer = Composer()
        self.composer.setFixedHeight(54 if compact else 66)
        self.composer.submit.connect(controller.submit)
        self.composer.textChanged.connect(self.text_changed)
        self.composer.focus_changed.connect(self.composer_focus)
        compose_layout.addWidget(self.composer)
        actions = QHBoxLayout()
        actions.setSpacing(4)
        paste = button("Paste", controller.paste)
        paste.setObjectName("quiet")
        paste.setToolTip("Paste clipboard text into this draft")
        actions.addWidget(paste)
        if not compact:
            new = button("New", controller.new_chat)
            new.setObjectName("quiet")
            new.setToolTip("Start a new conversation")
            actions.addWidget(new)
        self.more = button("More", self.more_actions)
        self.more.setObjectName("quiet")
        self.more.setAccessibleName("More conversation actions")
        actions.addWidget(self.more)
        actions.addStretch()
        self.stop = button("Stop", controller.stop)
        self.stop.setObjectName("danger")
        self.stop.setEnabled(False)
        actions.addWidget(self.stop)
        self.send = button("Send ↵", controller.submit, True)
        self.send.setToolTip("Send question · Enter\nShift+Enter for a new line")
        actions.addWidget(self.send)
        compose_layout.addLayout(actions)
        layout.addWidget(self.compose_well)
        # More contains full task prompts; keeping one action row leaves room for the conversation.
        self.status = ElidingLabel("Ready · screen context is off", "statusCapsule")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.status)
        controller.config_changed.connect(self.sync_config)
        controller.message_added.connect(self.view.add)
        controller.messages_reset.connect(self.view.load)
        controller.message_updated.connect(self.view.refresh_last)
        controller.question_changed.connect(self.set_question)
        controller.state_changed.connect(self.sync_state)
        controller.attachment_changed.connect(self.sync_attachment)
        controller.notice_changed.connect(self.show_notice)
        controller.routing_changed.connect(self.sync_routing)
        controller.state_changed.connect(self.mark.set_state)
        self.sync_config()

    def toggle_capture_controls(self) -> None:
        """Expand only local UI chrome; inspecting context controls never changes screen consent."""
        self.capture_controls.setVisible(self.context_toggle.isChecked())

    def composer_focus(self, focused: bool) -> None:
        """Highlight the entire input well while keeping the user's native text editing behavior."""
        self.compose_well.setProperty("focused", focused)
        self.compose_well.style().unpolish(self.compose_well)
        self.compose_well.style().polish(self.compose_well)

    def choose_model(self) -> None:
        """Give empty cloud catalogs a useful setup path; manual/local selection stays accessible."""
        if (
            not self.controller.models
            and not self.controller.selected_model
            and self.controller.settings.provider in {"gemini", "openrouter", "anthropic"}
        ):
            self.controller.open_settings()
        else:
            self.controller.pick_model()

    def change_skill(self) -> None:
        """Persist a user override; Auto can use the optional Gemini classifier on Send."""
        self.controller.settings.skill = self.skill.currentData()
        self.controller.save_settings()
        self.controller.config_changed.emit()

    def change_scope(self) -> None:
        """Select a capture target without immediately taking or sending a screenshot."""
        self.controller.settings.capture_scope = self.scope.currentData()
        self.controller.save_settings()
        self.controller.config_changed.emit()

    def text_changed(self) -> None:
        """Keep the two composers synchronized without retaining a separate draft."""
        self.controller.set_question(self.composer.toPlainText())

    def set_question(self, value: str) -> None:
        """Apply a shared draft only when different, avoiding recursive text-change signals."""
        if self.composer.toPlainText() != value:
            self.composer.blockSignals(True)
            self.composer.setPlainText(value)
            self.composer.blockSignals(False)
        self.sync_actions()

    def sync_config(self) -> None:
        """Reflect model, screen state, scope and profile; screen OFF disables capture controls."""
        settings = self.controller.settings
        self.mark.set_motion_reduced(settings.reduce_motion)
        if not self.compact:
            self.pin.setChecked(settings.pin_main)
        self.context_toggle.setText("Screen ON" if settings.screen_enabled else "Screen OFF")
        self.context_toggle.setProperty("screenEnabled", settings.screen_enabled)
        self.context_toggle.style().unpolish(self.context_toggle)
        self.context_toggle.style().polish(self.context_toggle)
        self.skill.blockSignals(True)
        self.skill.clear()
        self.skill.addItem("Auto · task profile", "auto")
        for skill in self.controller.instructions.profiles():
            self.skill.addItem(skill.name, skill.id)
        self.skill.blockSignals(False)
        self.screen.setChecked(settings.screen_enabled)
        self.screen.setText("Screen: ON" if settings.screen_enabled else "Screen: OFF")
        self.capture.setEnabled(
            settings.screen_enabled
            and not self.controller.capturing
            and not self.controller.answering
            and not self.controller.paused
        )
        self.scope.setEnabled(settings.screen_enabled)
        for combo, value in ((self.scope, settings.capture_scope), (self.skill, settings.skill)):
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(value)))
            combo.blockSignals(False)
        model = self.controller.selected_model
        can_choose = bool(self.controller.models) or settings.provider in {"compatible", "ollama"}
        needs_setup = not can_choose and not model
        self.model.setText(
            (model.name[:20] + ("…" if len(model.name) > 20 else ""))
            if model
            else "Set up model"
            if needs_setup
            else "Choose model"
        )
        self.model.setProperty("needsSetup", needs_setup)
        self.model.style().unpolish(self.model)
        self.model.style().polish(self.model)
        safe_tooltip(
            self.model,
            model.id if model else "Open provider settings" if needs_setup else "Choose or configure a model",
        )
        self.view.set_model_state(can_choose, bool(model), settings.screen_enabled)
        self.sync_actions()

    def sync_actions(self) -> None:
        """Make the next available action clear without granting screen access or submitting anything."""
        busy = self.controller.answering or self.controller.capturing
        has_input = bool(
            self.controller.question.strip()
            or (self.controller.settings.screen_enabled and self.controller.pending_image)
        )
        self.send.setEnabled(
            bool(self.controller.selected_model) and has_input and not busy and not self.controller.paused
        )
        self.send.setToolTip(
            "Send question · Enter\nShift+Enter for a new line"
            if self.controller.selected_model and has_input
            else "Type a question or attach a reviewed screenshot before sending."
            if self.controller.selected_model
            else "Choose a model before sending. You can keep writing your draft."
        )
        self.stop.setEnabled(self.controller.answering)
        self.capture.setEnabled(
            self.controller.settings.screen_enabled and not busy and not self.controller.paused
        )

    def show_prompts(self) -> None:
        """Offer the current task's full quick prompts without truncation or an oversized row."""
        skill = self.controller.instructions.select(
            self.controller.settings.skill, self.controller.question, self.controller.last_window.title
        )
        if self.controller.settings.skill == "auto" and self.controller.last_routing:
            skill = self.controller.last_routing.skill
        menu = QMenu(self)
        for text in skill.chips:
            menu.addAction(text, lambda value=text: self.controller.set_question(value))
        menu.exec_(self.more.mapToGlobal(QPoint(0, self.more.height())))

    def sync_state(self, state: str, text: str) -> None:
        """Show explicit load/stream/error states and prevent repeated submission."""
        self.status.setText(
            (
                "Screen " + ("ON" if self.controller.settings.screen_enabled else "OFF") + " · "
                if self.compact
                else ""
            )
            + text
        )
        self.status.setProperty("phase", state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.sync_actions()

    def sync_routing(self) -> None:
        """Keep the latest selected skill inspectable without increasing the compact panel's height."""
        decision = self.controller.last_routing
        safe_tooltip(
            self.more,
            f"Last skill: {decision.skill.name}. {decision.note}"
            if decision
            else "Suggestions for the chosen task profile",
        )

    def sync_attachment(self) -> None:
        """Preview pending screenshots; OFF removes them from requests even if an old capture remains in memory."""
        image = self.controller.pending_image if self.controller.settings.screen_enabled else None
        self.attachment.setVisible(bool(image))
        self.remove_attachment.setVisible(bool(image))
        self.sync_actions()
        if image:
            self.attachment.setText("Screenshot · Review / redact")
            self.attachment.setToolTip(f"{image.width} × {image.height} · Click to review or redact")

    def show_notice(self, text: str) -> None:
        """Keep errors visible and actionable without replacing the conversation or partial response."""
        self.notice_text = text
        self.notice.setText("Notice · Read details")
        safe_tooltip(self.notice, text)
        self.notice.setAccessibleDescription(text)
        self.notice.setVisible(bool(text))

    def notice_details(self) -> None:
        """Show a complete local notice as plain text, keeping the small reader's controls in place."""
        if not self.notice_text:
            return
        dialog = QMessageBox(QMessageBox.Information, "Maya — Notice", "", QMessageBox.Ok, self)
        dialog.setTextFormat(Qt.PlainText)
        dialog.setText(self.notice_text)
        dialog.exec_()

    def more_actions(self) -> None:
        """Expose secondary conversation controls without crowding the compact interface."""
        menu = QMenu(self)
        for group in (
            (
                ("Quick prompts", self.show_prompts),
                ("Why this skill?", self.controller.explain_routing),
                ("Review request context", self.controller.review_context),
            ),
            (
                ("Regenerate last answer", self.controller.regenerate),
                ("Continue answer", self.controller.continue_answer),
                ("Edit last question", self.controller.edit_last),
                ("Copy latest answer", self.controller.copy_latest),
            ),
            (
                ("New conversation", self.controller.new_chat),
                ("History", self.controller.show_history),
                ("Remember this draft", self.controller.remember_draft),
                ("Export chat to Markdown", self.controller.export),
            ),
            (
                ("Floating clipboard viewer", self.controller.show_clipboard),
                ("Screen-share privacy", self.controller.explain_capture_privacy),
                ("Use compact window size", self.controller.compact_window),
                ("Settings", self.controller.open_settings),
            ),
        ):
            if menu.actions():
                menu.addSeparator()
            for title, action in group:
                menu.addAction(title, action)
        menu.exec_(self.more.mapToGlobal(QPoint(0, self.more.height())))


class MainWindow(QMainWindow):
    """Resizable desktop chat with a small workbench sidebar and no local account/login flow."""

    def __init__(self, controller):
        """Build the normal surface and retain placement through the controller."""
        super().__init__()
        self.controller = controller
        self.setWindowTitle("Maya the Helper")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, controller.settings.pin_main)
        self.resize(*MAIN_SIZE)
        self.setMinimumSize(*MAIN_MIN)
        canvas = QWidget()
        canvas.setObjectName("canvas")
        self.setCentralWidget(canvas)
        layout = QHBoxLayout(canvas)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = QScrollArea()
        self.sidebar.setWidgetResizable(True)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar.setFixedWidth(176)
        side_content = QWidget()
        side_content.setObjectName("sidebar")
        self.sidebar.setWidget(side_content)
        side = QVBoxLayout(side_content)
        side.setContentsMargins(16, 16, 16, 14)
        side.setSpacing(8)
        side.addWidget(MayaMark(56), 0, Qt.AlignHCenter)
        side.addWidget(label("maya", "brand"))
        side.addWidget(label("THE HELPER", "eyebrow"))
        side.addSpacing(15)
        side.addWidget(button("＋ New chat", controller.new_chat, True))
        side.addWidget(button("History", controller.show_history))
        side.addWidget(button("Settings", controller.open_settings))
        side.addSpacing(6)
        side.addWidget(label("YOUR MODEL", "eyebrow"))
        self.provider = QComboBox()
        self.provider.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.provider.setMinimumWidth(100)
        for identifier, name in PROVIDERS.items():
            self.provider.addItem(name, identifier)
        self.provider.setCurrentIndex(self.provider.findData(controller.settings.provider))
        self.provider.currentIndexChanged.connect(self.provider_changed)
        side.addWidget(self.provider)
        side.addWidget(button("Refresh models", controller.refresh_models))
        self.key_status = label("Configure your key in Settings")
        side.addWidget(self.key_status)
        side.addStretch()
        side.addWidget(button("Float Maya", controller.show_overlay))
        side.addSpacing(10)
        side.addWidget(label("LOCAL BY DESIGN\nYour keys · your choices", "eyebrow"))
        layout.addWidget(self.sidebar)
        self.sidebar.hide()
        self.panel = ChatPanel(controller)
        layout.addWidget(self.panel, 1)
        controller.config_changed.connect(self.sync_provider)
        self.statusBar().showMessage("Enter to send · Shift+Enter for a new line")

    def toggle_navigation(self) -> None:
        """Reveal navigation alongside the conversation, restoring the smaller width when closed."""
        showing = not self.sidebar.isVisible()
        target = self.width() + (self.sidebar.width() if showing else -self.sidebar.width())
        self.sidebar.setVisible(showing)
        self.setMinimumWidth(MAIN_MIN[0] + (self.sidebar.width() if showing else 0))
        self.resize(max(self.minimumWidth(), target), self.height())
        screen = self.screen() or QApplication.primaryScreen()
        available = screen.availableGeometry()
        self.resize(min(self.width(), available.width()), self.height())
        self.move(max(available.left(), min(self.x(), available.right() - self.width())), self.y())

    def compact_size(self) -> None:
        """Reset a resized workbench to the small default while retaining the shared conversation."""
        self.sidebar.hide()
        self.setMinimumSize(*MAIN_MIN)
        self.showNormal()
        available = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        self.resize(min(MAIN_SIZE[0], available.width() - 20), min(MAIN_SIZE[1], available.height() - 45))
        self.move(
            max(available.left(), min(self.x(), available.right() - self.width())),
            max(available.top(), min(self.y(), available.bottom() - self.height() - 35)),
        )

    def provider_changed(self) -> None:
        """Select the next provider and refresh its key-scoped catalog."""
        self.controller.change_provider(self.provider.currentData())

    def sync_provider(self) -> None:
        """Update sidebar controls when Settings changes provider/defaults."""
        self.provider.blockSignals(True)
        self.provider.setCurrentIndex(self.provider.findData(self.controller.settings.provider))
        self.provider.blockSignals(False)
        self.key_status.setText(
            f"{len(self.controller.models)} discovered models"
            if self.controller.models
            else "Add a key, then refresh models"
        )

    def closeEvent(self, event) -> None:
        """Close to the tray when available; Quit in the tray performs coordinated shutdown."""
        if self.controller.quitting:
            event.accept()
        elif self.controller.tray.isSystemTrayAvailable():
            self.controller.remember_geometry()
            self.hide()
            event.ignore()
        else:
            event.ignore()
            self.controller.quit()


class MiniWindow(QWidget):
    """Small topmost input panel anchored beside the orb; intentional input can acquire focus."""

    def __init__(self, controller):
        """Create an owned tool window with its own synchronized ChatPanel."""
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setWindowTitle("Maya — quick help")
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName("floatingShell")
        self.resize(*MINI_SIZE)
        self.setMinimumSize(*MINI_MIN)
        self.setWindowOpacity(controller.settings.overlay_opacity)
        self.controller = controller
        self.was_active = False
        self.drag_anchor = None
        box = QVBoxLayout(self)
        # Wrapped document hints must never resize the user's overlay while new text arrives.
        box.setSizeConstraint(QLayout.SetNoConstraint)
        box.setContentsMargins(0, 0, 0, 0)
        self.panel = ChatPanel(controller, compact=True)
        box.addWidget(self.panel)
        controller.config_changed.connect(self.configure)

    def configure(self) -> None:
        """Apply user-chosen translucency without changing focus, draft or screenshot permissions."""
        self.setWindowOpacity(self.controller.settings.overlay_opacity)

    def changeEvent(self, event) -> None:
        """Collapse after intentional panel focus is lost; keep owned settings dialogs visible."""
        if event.type() == QEvent.ActivationChange:
            if self.isActiveWindow():
                self.was_active = True
            elif self.was_active and QApplication.activeModalWidget() is None:
                self.was_active = False
                self.hide()
        super().changeEvent(event)

    def keyPressEvent(self, event) -> None:
        """Escape collapses the panel, preserving draft and conversation."""
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        """Drag the flower/title space; input and action buttons keep their normal mouse behavior."""
        if event.button() == Qt.LeftButton and event.pos().y() < 50:
            self.drag_anchor = event.globalPos() - self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Clamp the floating reader to the monitor under the pointer, including negative coordinates."""
        if self.drag_anchor is not None:
            self.move_to_pointer(event.globalPos())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def move_to_pointer(self, position: QPoint) -> None:
        """Keep the whole reader reachable on the target monitor during a header drag."""
        screen = QApplication.screenAt(position) or self.screen() or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        point = position - self.drag_anchor
        self.move(
            max(bounds.left(), min(point.x(), bounds.right() - self.width() + 1)),
            max(bounds.top(), min(point.y(), bounds.bottom() - self.height() + 1)),
        )

    def mouseReleaseEvent(self, event) -> None:
        """Use the final pointer position even if a busy event loop coalesced the last move."""
        if event.button() == Qt.LeftButton and self.drag_anchor is not None:
            self.move_to_pointer(event.globalPos())
            self.drag_anchor = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def hideEvent(self, event) -> None:
        """Discard an unfinished drag when Escape, capture or focus loss hides the reader."""
        self.drag_anchor = None
        super().hideEvent(event)


# --- The non-activating orb is a draggable native widget with text-backed state indicators. ---
class Orb(QWidget):
    """Always-on-top assistant flower with a gentle bloom animation only while active."""

    def __init__(self, controller):
        """Create a transparent shaped orb without stealing keyboard focus from other applications."""
        super().__init__(
            None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
        )
        self.controller = controller
        self.setWindowTitle("Maya — floating helper")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAccessibleName("Maya floating helper")
        self.setAccessibleDescription("Click for quick help. Drag to move. Right-click for actions.")
        self.state = "idle"
        self.hovered = False
        self.phase = 0
        self.anchor = None
        self.dragged = False
        self.timer = QTimer(self)
        self.timer.setInterval(90)
        self.timer.timeout.connect(self.animate)
        controller.state_changed.connect(self.set_state)
        controller.config_changed.connect(self.configure)
        self.configure()

    def configure(self) -> None:
        """Apply the user's size/opacity and expose capture state in a tooltip as well as a dot."""
        self.setFixedSize(self.controller.settings.orb_size, self.controller.settings.orb_size)
        self.phase = 0
        self.sync_animation()
        self.setWindowOpacity(self.controller.settings.orb_opacity)
        self.setToolTip(
            f"Maya · {self.state} · Screen {'ON' if self.controller.settings.screen_enabled else 'OFF'}\n"
            f"{self.controller.settings.hotkey} to show/hide · drag to move · right-click for actions"
        )
        self.update()

    def set_state(self, state: str, text: str) -> None:
        """Use state colors and a matching tooltip; no state relies on color alone."""
        self.state = state
        safe_tooltip(
            self, f"Maya · {text}\nScreen {'ON' if self.controller.settings.screen_enabled else 'OFF'}"
        )
        self.sync_animation()
        self.update()

    def sync_animation(self) -> None:
        """Stop hidden/idle orb animation so a full-window answer does not wake invisible painters."""
        if (
            self.isVisible()
            and self.state in {"capturing", "thinking", "streaming"}
            and not self.controller.settings.reduce_motion
        ):
            self.timer.start()
        else:
            self.timer.stop()

    def showEvent(self, event) -> None:
        """Resume active animation only after this surface becomes visible."""
        super().showEvent(event)
        self.sync_animation()

    def hideEvent(self, event) -> None:
        """No animation timer remains active while the orb is hidden or capture is in progress."""
        self.timer.stop()
        super().hideEvent(event)

    def animate(self) -> None:
        """Advance a bounded animation without waking timers while Maya is idle."""
        self.phase = (self.phase + 0.2) % math.tau
        self.update()

    def paintEvent(self, event) -> None:
        """Draw the compact procedural flower and screen/state badge."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        size = self.width()
        active = self.state in {"capturing", "thinking", "streaming"}
        animated = active and not self.controller.settings.reduce_motion
        paint_maya(
            painter,
            QRectF(0, 0, size, size),
            1 + (math.sin(self.phase) * 0.035 if animated else 0),
            -4 if self.hovered else 0,
            0.7 + (math.sin(self.phase) * 0.2 if animated else 0)
            if active
            else (0.65 if self.hovered else 0.35),
        )
        color = {
            "error": "#c06750",
            "paused": "#999b8b",
            "thinking": "#edc260",
            "streaming": "#8ccaac",
            "capturing": "#8ccaac",
        }.get(self.state, "#8ccaac" if self.controller.settings.screen_enabled else "#c4ccbc")
        painter.setPen(QPen(QColor("#f7f5ef"), 2))
        painter.setBrush(QColor(color))
        painter.drawEllipse(size - 17, size - 17, 11, 11)

    def mousePressEvent(self, event) -> None:
        """Begin drag without activating the window; right-click exposes explicit actions."""
        if event.button() == Qt.LeftButton:
            self.anchor = event.globalPos() - self.pos()
            self.dragged = False
        elif event.button() == Qt.RightButton:
            self.menu(event.globalPos())

    def mouseMoveEvent(self, event) -> None:
        """Move the orb within the active desktop; panel anchoring is recomputed when opened."""
        if self.anchor is not None and event.buttons() & Qt.LeftButton:
            target = event.globalPos() - self.anchor
            if (target - self.pos()).manhattanLength() > 3:
                self.dragged = True
            self.move(target)

    def mouseReleaseEvent(self, event) -> None:
        """Snap drags to the nearest monitor edge; a click expands/collapses the quick panel."""
        self.anchor = None
        if event.button() != Qt.LeftButton:
            return
        if self.dragged:
            screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
            bounds = screen.availableGeometry()
            x = (
                bounds.left() + 12
                if self.geometry().center().x() < bounds.center().x()
                else bounds.right() - self.width() - 12
            )
            y = max(bounds.top() + 12, min(self.y(), bounds.bottom() - self.height() - 12))
            self.move(x, y)
            self.controller.settings.orb_position = [x, y]
            self.controller.save_settings()
        else:
            self.controller.expand()

    def enterEvent(self, event) -> None:
        """Make a hovered orb fully legible without changing the saved idle opacity."""
        self.setWindowOpacity(1)
        self.hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        """Restore idle dimming after hover."""
        self.setWindowOpacity(self.controller.settings.orb_opacity)
        self.hovered = False
        self.update()

    def menu(self, point: QPoint) -> None:
        """Expose screen/no-screen ask, model/profile, settings, pause, hide and quit actions."""
        menu = QMenu(self)
        menu.addAction("Ask about screen", self.controller.ask_screen)
        menu.addAction("Ask without screenshot", self.controller.ask_text)
        menu.addAction("Floating clipboard viewer", self.controller.show_clipboard)
        menu.addAction("Choose model", self.controller.pick_model)
        skills = menu.addMenu("Task profile")
        for identifier, title in [("auto", "Auto")] + [
            (skill.id, skill.name) for skill in self.controller.instructions.profiles()
        ]:
            skills.addAction(title, lambda value=identifier: self.controller.change_skill(value))
        menu.addSeparator()
        menu.addAction("Resume" if self.controller.paused else "Pause", self.controller.toggle_pause)
        menu.addAction("Settings", self.controller.open_settings)
        menu.addAction("Hide orb", self.hide)
        menu.addAction("Quit Maya", self.controller.quit)
        menu.exec_(point)
