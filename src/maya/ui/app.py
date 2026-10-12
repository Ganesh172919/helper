"""Application coordinator: one conversation, two surfaces, explicit capture, and bounded background jobs."""

from dataclasses import replace
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import sqlite3
import time

from PIL import Image
from PyQt5.QtCore import (
    QAbstractNativeEventFilter,
    QCoreApplication,
    QObject,
    QPoint,
    QRect,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from maya.capture import capture, prepare
from maya.core.config import ConfigStore, Settings
from maya.core.context import prepare_context
from maya.core.prompts import InstructionManager, preferred_model
from maya.core.providers import GeminiProvider, create_provider
from maya.core.routing import RoutingDecision, TaskRouter, classification_payload
from maya.core.safety import redact, refusal
from maya.core.storage import HistoryStore
from maya.core.types import Cancellation, MayaError, Message, Model
from maya.platform.secrets import SecretStore, catalog_identity
from maya.platform.windows import ActiveWindow, WindowsDesktop
from .capture_ui import ImagePreview, RegionSelector
from .settings import ModelPicker, SettingsDialog
from .history import HistoryDialog
from .clipboard import ClipboardWindow
from .context_review import ContextReview
from .widgets import maya_icon
from .windows import MAIN_MIN, MINI_SIZE, MainWindow, MiniWindow, Orb
from .privacy import CaptureGuard
from .workers import Generation, Job


# --- Global shortcut messages are translated to ordinary controller actions. ---
class HotkeyFilter(QAbstractNativeEventFilter):
    """Keep pointer-size-specific Windows messages out of the widgets and portable core."""

    def __init__(self, controller):
        """Retain controller ownership for the lifetime of the native event filter."""
        super().__init__()
        self.controller = controller

    def nativeEventFilter(self, event_type, message):
        """Handle only WM_HOTKEY, passing every other native event through to Qt."""
        import sys
        from ctypes import wintypes

        if sys.platform == "win32" and event_type in {b"windows_generic_MSG", b"windows_dispatcher_MSG"}:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312:
                action = {
                    1: self.controller.toggle_visible,
                    2: self.controller.ask_screen,
                    3: self.controller.toggle_screen,
                    4: lambda: self.controller.scroll_answer(-120),
                    5: lambda: self.controller.scroll_answer(120),
                }.get(int(msg.wParam))
                if action:
                    QTimer.singleShot(0, action)
                    return True, 0
        return False, 0


# --- Coordinator: widgets emit intent, workers emit data, persistence commits completed turns. ---
class AppController(QObject):
    """Central lifecycle/state owner so normal and floating modes never drift apart."""

    config_changed = pyqtSignal()
    message_added = pyqtSignal(object)
    messages_reset = pyqtSignal(object)
    message_updated = pyqtSignal()
    question_changed = pyqtSignal(str)
    attachment_changed = pyqtSignal()
    state_changed = pyqtSignal(str, str)
    notice_changed = pyqtSignal(str)
    routing_changed = pyqtSignal()

    def __init__(self, store: ConfigStore, settings: Settings, history: HistoryStore, secrets=None):
        """Create shared state, native windows, tray and timers; no network call occurs in the constructor."""
        super().__init__()
        self.store, self.settings, self.history = store, settings, history
        self.secrets = secrets or SecretStore()
        self.desktop = WindowsDesktop()
        self.capture_guard = CaptureGuard(self.desktop, self)
        self.instructions = InstructionManager(settings.custom_profiles)
        self.messages: list[Message] = []
        self.chat_id = None
        self.question = ""
        self.pending_image = None
        self.last_image = None
        self.reuse_image = None
        self.generation = None
        self.routing_job = None
        self.review_dialog = None
        self.last_routing = None
        self.jobs: set[Job | Generation] = set()
        self.models: list[Model] = []
        self.selected_model = None
        self.catalog_refreshed = 0
        self.catalog_generation = 0
        self.catalog_job = None
        self.capturing = False
        self.paused = False
        self.quitting = False
        self.last_window = ActiveWindow()
        self.draft_edit = False
        self.buffer = ""
        self.main = MainWindow(self)
        self.mini = MiniWindow(self)
        self.orb = Orb(self)
        self.clipboard_window = ClipboardWindow(self)
        self.clipboard_restore = False
        self.icon = maya_icon()
        self.main.setWindowIcon(self.icon)
        self.mini.setWindowIcon(self.icon)
        self.clipboard_window.setWindowIcon(self.icon)
        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip("Maya the Helper · local desktop assistant")
        self.tray.activated.connect(self.tray_clicked)
        self.tray_menu = QMenu()
        for title, action in (
            ("Show Maya", self.show_normal),
            ("Show floating Maya", self.show_overlay),
            ("Show / hide", self.toggle_visible),
            ("Toggle screen context", self.toggle_screen),
            ("Floating clipboard viewer", self.show_clipboard),
            ("Pause / resume", self.toggle_pause),
            ("Settings", self.open_settings),
            ("Quit Maya", self.quit),
        ):
            self.tray_menu.addAction(title, action)
        self.tray.setContextMenu(self.tray_menu)
        self.flush_timer = QTimer(self)
        self.flush_timer.setInterval(45)
        self.flush_timer.timeout.connect(self.flush)
        self.window_timer = QTimer(self)
        self.window_timer.setInterval(750)
        self.window_timer.timeout.connect(self.track_window)
        self.window_timer.start()
        self.hotkeys = HotkeyFilter(self)
        QCoreApplication.instance().installNativeEventFilter(self.hotkeys)
        self.restore_geometry()
        self.config_changed.connect(self.cancel_routing)
        self.attachment_changed.connect(self.cancel_routing)
        self.config_changed.connect(self.apply_pin)

    @property
    def answering(self) -> bool:
        """Classification and generation form one single-flight operation for every UI action."""
        return self.generation is not None or self.routing_job is not None

    def cancel_routing(self) -> None:
        """Invalidate a pending decision immediately; a late worker result can never submit a stale draft."""
        if self.routing_job is not None:
            job, self.routing_job = self.routing_job, None
            job.token.cancel()
            self.state("idle", "Task routing cancelled · your draft is kept")

    def start(self) -> None:
        """Display the user's last mode, register shortcuts, and load a matching fresh catalog cache."""
        self.capture_guard.start()
        if self.tray.isSystemTrayAvailable():
            self.tray.show()
        if self.settings.mode == "overlay":
            self.show_overlay()
        else:
            self.show_normal()
        self.apply_hotkeys()
        for widget in (self.main, self.mini, self.orb):
            self.desktop.exclude_capture(int(widget.winId()))
        self.load_cache()
        self.state(
            "idle",
            "Ready · ask a question" if self.selected_model else "Ready · refresh models and choose one",
        )

    def state(self, state: str, text: str) -> None:
        """Broadcast a human-readable status to both surfaces and the orb tooltip."""
        self.state_changed.emit(state, text)

    def notice(self, text: str) -> None:
        """Show a recoverable inline explanation in both chat surfaces."""
        self.notice_changed.emit(text)

    def explain_capture_privacy(self) -> None:
        """Let users inspect reference-style exclusion without transmitting anything or hiding errors."""
        dialog = QMessageBox(
            QMessageBox.Information, "Maya — Screen-share privacy", "", QMessageBox.Ok, self.visible_parent()
        )
        dialog.setTextFormat(Qt.PlainText)
        dialog.setText(
            self.capture_guard.report()
            + "\n\nMaya requests Windows capture exclusion for its windows, dialogs and menus. "
            "This does not guarantee invisibility in every sharing tool. Verify using a private "
            "recording with your actual tool. Alt+Shift+N hides Maya. "
            "Maya also hides its windows when taking its own reviewed screenshot."
        )
        dialog.exec_()

    def save_settings(self) -> None:
        """Persist non-secret settings; a write failure stays visible without crashing the chat."""
        try:
            self.store.save(self.settings)
        except (MayaError, OSError):
            self.notice("Could not save preferences. Check permissions for the local data folder.")

    def set_question(self, text: str) -> None:
        """Keep the draft shared between both windows, ignoring redundant updates."""
        if self.question != text:
            self.cancel_routing()
            self.question = text
            self.question_changed.emit(text)

    def change_provider(self, provider: str) -> None:
        """Switch provider for future requests; current generation retains its immutable inputs."""
        if provider != self.settings.provider:
            self.catalog_generation += 1
            if self.catalog_job:
                self.catalog_job.token.cancel()
            self.settings.provider = provider
            self.models, self.selected_model = [], None
            self.save_settings()
            self.config_changed.emit()
            self.load_cache()
            if not self.models:
                self.refresh_models()

    def change_skill(self, skill: str) -> None:
        """Store a user-selected task profile without starting a request."""
        self.settings.skill = skill
        self.save_settings()
        self.config_changed.emit()

    def load_cache(self) -> None:
        """Read only a fresh endpoint/key-matching cached catalog, then select a discovered default."""
        try:
            name = self.settings.provider
            key = self.secrets.get(name, self.settings.urls[name])
            self.models, self.catalog_refreshed = self.history.cached_models(
                name, catalog_identity(self.settings.urls[name], key)
            )
            self.selected_model = self.default_model(self.models)
            self.config_changed.emit()
        except MayaError as exc:
            self.notice(str(exc))
        except (sqlite3.Error, OSError):
            self.notice(
                "Could not read the local model cache. Check disk space/permissions, then Refresh models."
            )

    def default_model(self, models: list[Model]) -> Model | None:
        """Restore explicit manual IDs and verified vision choices only for their matching endpoint."""
        name = self.settings.provider
        explicit = self.settings.models.get(name, "")
        preference = self.settings.model_preferences.get(name, {})
        matches = preference.get("endpoint") == self.settings.urls[name] and preference.get("id") == explicit
        selected = preferred_model(models, explicit)
        discovered = next((model for model in models if model.id == explicit), None)
        if matches and preference.get("manual") and not discovered:
            return Model(explicit, explicit, name, True if preference["vision_confirmed"] else None)
        if matches and discovered and discovered.vision is None and preference.get("vision_confirmed"):
            return replace(discovered, vision=True)
        return selected

    def refresh_models(self) -> None:
        """Validate the selected key and discover models in a worker; reject stale provider-switch results."""
        if self.quitting:
            return
        self.catalog_generation += 1
        generation = self.catalog_generation
        if self.catalog_job and self.catalog_job.isRunning():
            self.catalog_job.token.cancel()
        try:
            name, endpoint = self.settings.provider, self.settings.urls[self.settings.provider]
            key = self.secrets.get(name, endpoint)
            provider = create_provider(self.settings, key)
        except MayaError as exc:
            self.notice(str(exc))
            self.state("error", "Model discovery could not start · check Settings")
            return
        identity = catalog_identity(endpoint, key)
        self.state("thinking", "Checking provider and discovering models…")

        def task(token):
            """OpenRouter's authenticated /key check supplements its public catalog request."""
            if name == "openrouter":
                provider.validate_key(token)
            return provider.list_models(token)

        def complete(models):
            """Accept only the current refresh; cache metadata without retaining credentials."""
            if generation != self.catalog_generation or name != self.settings.provider or self.quitting:
                return
            self.models = models
            self.catalog_refreshed = time.time()
            try:
                self.history.cache_models(name, models, identity)
                cache_note = ""
            except (sqlite3.Error, OSError):
                cache_note = "Models loaded, but could not be cached locally. Check disk space/permissions."
            self.selected_model = self.default_model(models)
            if self.selected_model:
                previous = self.settings.models.get(name, "")
                self.settings.models[name] = self.selected_model.id
                self.save_settings()
                self.notice(
                    "Your previous model is unavailable; a discovered default is selected. Choose a model to change it."
                    if previous and previous != self.selected_model.id
                    else cache_note
                )
            else:
                self.notice(
                    "No supported chat models were found. Check provider access, install a local model, or use a compatible manual ID."
                )
            self.config_changed.emit()
            self.state("idle", f"Loaded {len(models)} models · catalog access verified")

        job = Job(task, Cancellation(self.settings.timeout))
        self.catalog_job = job
        job.result.connect(complete)
        job.error.connect(lambda text: self.catalog_error(generation, text))
        self.start_job(job)

    def catalog_error(self, generation: int, text: str) -> None:
        """Ignore obsolete catalog failures caused by a later refresh or provider switch."""
        if generation == self.catalog_generation and not self.quitting:
            self.notice(text)
            self.state("error", "Model discovery failed · check Settings")

    def start_job(self, job) -> None:
        """Retain a running QThread until its finished signal, preventing premature object destruction."""
        self.jobs.add(job)
        job.finished.connect(lambda current=job: self.release_job(current))
        job.start()

    def release_job(self, job) -> None:
        """Release finished workers; a quitting app exits only after every worker is stopped."""
        self.jobs.discard(job)
        if job is self.catalog_job:
            self.catalog_job = None
        job.deleteLater()
        if self.quitting and not self.jobs:
            QApplication.instance().quit()

    def pick_model(self) -> None:
        """Select a discovered model or compatible manual ID, preserving its explicit vision override."""
        allow_manual = self.settings.provider in {"compatible", "ollama"}
        dialog = ModelPicker(
            self.models,
            self.selected_model.id if self.selected_model else "",
            self.catalog_refreshed,
            self.visible_parent(),
            allow_manual=allow_manual,
        )
        dialog.manual.setVisible(allow_manual)
        original = next(
            (model for model in self.models if self.selected_model and model.id == self.selected_model.id),
            None,
        )
        if allow_manual and self.selected_model and original is None:
            dialog.manual.setText(self.selected_model.id)
        if (
            self.selected_model
            and self.selected_model.vision is True
            and (original is None or original.vision is None)
        ):
            dialog.unknown_vision.setChecked(True)
        self.desktop.exclude_capture(int(dialog.winId()))
        if dialog.exec_() == QDialog.Accepted:
            self.use_model(dialog.chosen)

    def use_model(self, model: Model) -> None:
        """Persist a user choice plus endpoint-scoped manual/vision metadata; do not grant unknown capabilities implicitly."""
        name = self.settings.provider
        self.selected_model = replace(model, provider=name)
        original = next((item for item in self.models if item.id == model.id), None)
        self.settings.models[name] = model.id
        self.settings.model_preferences[name] = {
            "id": model.id,
            "endpoint": self.settings.urls[name],
            "manual": original is None,
            "vision_confirmed": model.vision is True and (original is None or original.vision is None),
        }
        self.save_settings()
        self.config_changed.emit()

    def open_settings(self) -> None:
        """Open separate tabs with masked keys; accepted edits trigger authenticated model refresh."""
        dialog = SettingsDialog(
            self.settings, self.secrets, self.history, self.store.directory, self.visible_parent()
        )
        self.desktop.exclude_capture(int(dialog.winId()))
        if dialog.exec_() == QDialog.Accepted:
            self.catalog_generation += 1
            if self.catalog_job:
                self.catalog_job.token.cancel()
            self.settings = dialog.settings
            self.instructions = InstructionManager(self.settings.custom_profiles)
            self.save_settings()
            self.apply_hotkeys()
            self.models, self.selected_model = [], None
            self.config_changed.emit()
            self.load_cache()
            self.refresh_models()

    def toggle_screen(self) -> None:
        """Persist screen ON/OFF; OFF discards all pending/reusable screenshots and blocks capture."""
        self.settings.screen_enabled = not self.settings.screen_enabled
        if not self.settings.screen_enabled:
            self.pending_image = self.reuse_image = self.last_image = None
        self.save_settings()
        self.config_changed.emit()
        self.attachment_changed.emit()
        self.state(
            "idle",
            f"Screen context {'ON · Capture to attach' if self.settings.screen_enabled else 'OFF · text only'}",
        )

    def remove_attachment(self) -> None:
        """Remove the pending image and disable reuse for subsequent follow-up requests."""
        self.cancel_routing()
        self.pending_image = self.reuse_image = None
        self.attachment_changed.emit()

    def preview_pending(self) -> None:
        """Review/redact an already pending screenshot; Discard removes it from the next request."""
        self.cancel_routing()
        if not self.pending_image:
            return
        image = Image.open(BytesIO(self.pending_image.data)).copy()
        self.review_image(image)

    def capture_screen(self) -> None:
        """Capture only on explicit action with screen ON, hiding every own top-level window first."""
        if not self.settings.screen_enabled:
            self.notice("Screen context is OFF. Turn it on before taking a screenshot.")
            return
        if self.paused or self.capturing or self.answering:
            self.notice("Finish or stop the current operation before taking another screenshot.")
            return
        scope = self.settings.capture_scope
        if scope == "last":
            if self.last_image:
                self.pending_image = self.last_image
                self.attachment_changed.emit()
                self.preview_pending()
            else:
                self.notice("No previous capture is available in this session.")
            return
        self.track_window()
        window = self.last_window
        if scope == "window" and not self.desktop.valid_window(window):
            self.notice(
                "The last external window is minimized or unavailable. Focus it and use the capture shortcut."
            )
            return
        point = self.desktop.cursor()
        self.capture_screen_object = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        self.capture_views = [
            widget
            for widget in QApplication.topLevelWidgets()
            if widget.isVisible() and not isinstance(widget, QMenu)
        ]
        self.capturing = True
        for widget in self.capture_views:
            widget.hide()
        self.state("capturing", "Capturing the selected screen…")
        self.config_changed.emit()
        # Let the compositor finish hiding own windows before the worker reads desktop pixels.
        QTimer.singleShot(180, lambda: self.run_capture(scope, point, window))

    def run_capture(self, scope: str, point, window: ActiveWindow) -> None:
        """Start a capture job after hiding; turning screen OFF during the delay cancels capture."""
        if self.quitting or not self.settings.screen_enabled:
            self.restore_capture_windows()
            return
        job = Job(lambda token: capture("monitor" if scope == "region" else scope, point, window.rect))
        job.result.connect(lambda result: self.captured(scope, result))
        job.error.connect(self.capture_error)
        self.start_job(job)

    def restore_capture_windows(self) -> None:
        """Restore only the windows visible before capture, keeping original mode and focus behavior."""
        for widget in getattr(self, "capture_views", []):
            if not self.quitting:
                widget.show()
        self.capture_views = []
        self.capturing = False
        self.config_changed.emit()
        self.state("paused" if self.paused else "idle", "Capture finished · review before sending")

    def captured(self, scope: str, result) -> None:
        """Map optional region selection and show mandatory local review before attachment."""
        image, bounds = result
        self.restore_capture_windows()
        if self.quitting or not self.settings.screen_enabled:
            return
        if scope == "region":
            selector = RegionSelector(image, self.capture_screen_object)
            self.desktop.exclude_capture(int(selector.winId()))
            if selector.exec_() != QDialog.Accepted:
                self.notice("Region selection cancelled. No new screenshot is attached.")
                return
            image = selector.selected
        try:
            encoded = prepare(image, self.settings.image_edge)
            self.review_image(Image.open(BytesIO(encoded.data)).copy())
        except MayaError as exc:
            self.notice(str(exc))

    def review_image(self, image) -> None:
        """Accept only reviewed/redacted pixels; discard cancels outbound attachment and reuse."""
        dialog = ImagePreview(image, parent=self.visible_parent())
        self.desktop.exclude_capture(int(dialog.winId()))
        if dialog.exec_() == QDialog.Accepted and self.settings.screen_enabled:
            self.pending_image = prepare(dialog.canvas.image, self.settings.image_edge, check_blank=False)
            self.last_image = self.pending_image
            self.notice("")
        else:
            self.pending_image = self.reuse_image = None
        self.attachment_changed.emit()

    def capture_error(self, text: str) -> None:
        """Restore UI after capture failure and keep the draft available for text-only help."""
        self.restore_capture_windows()
        self.notice(text)
        self.state("error", "Capture failed · text chat is available")

    def prepared_context(self, skill=None):
        """Prepare current inputs without credentials, discovery, capture or a history write."""
        image = (self.pending_image or self.reuse_image) if self.settings.screen_enabled else None
        question = self.question.strip()
        if not question and not image:
            raise MayaError("Enter a question or capture and attach a screenshot first.", "validation")
        question = question or "Help me understand what is on this screen and suggest a useful next step."
        if self.settings.redact_text:
            clean, changed = redact(question)
            if changed:
                self.set_question(clean)
                raise MayaError(
                    "Recognizable secrets were redacted. Review the question, then press Send again.",
                    "privacy",
                )
        if reply := refusal(question):
            raise MayaError(reply, "safety")
        if not self.selected_model:
            raise MayaError("Choose a model first. Add your key in Settings and refresh models.", "model")
        settings = deepcopy(self.settings)
        settings.validate()
        profile = self.instructions.select(
            skill.id if skill else settings.skill, question, self.last_window.title
        )
        memories = self.history.relevant_memories(question, profile.id) if settings.remember_enabled else []
        prior = self.messages[:-2] if self.draft_edit and len(self.messages) >= 2 else self.messages
        return prepare_context(
            question,
            image,
            self.selected_model,
            settings,
            self.instructions,
            profile,
            memories,
            prior,
            self.last_window.title,
            self.draft_edit,
            self.chat_id,
        )

    def show_context(self, context, routing_payload=None, note="") -> bool:
        """Show only local prepared content; never expose stored keys, headers or recognizable text credentials."""
        visible_text = "\n".join(
            [
                context.request.system,
                self.settings.urls[self.settings.provider],
                context.request.model.id,
                *context.memories,
                *(m.text for m in context.request.messages),
            ]
        )
        if redact(visible_text)[1]:
            raise MayaError(
                "Recognizable credentials remain in this context. Remove them or enable redaction before reviewing.",
                "privacy",
            )
        dialog = ContextReview(
            context,
            self.settings.urls[self.settings.provider],
            self.settings.provider,
            routing_payload,
            self.settings.classifier_model,
            note,
            self.visible_parent(),
        )
        self.review_dialog = dialog
        try:
            return dialog.exec_() == QDialog.Accepted
        finally:
            self.review_dialog = None
            dialog.deleteLater()

    def review_context(self) -> None:
        """Opt in to a local review, then explicit routing/final review before answer generation."""
        if self.quitting or self.paused or self.capturing or self.answering or self.review_dialog:
            return
        try:
            context = self.prepared_context()
            routing = self.settings.skill == "auto" and self.settings.classifier_enabled
            payload = (
                classification_payload(self.instructions, context.question, self.last_window.title)
                if routing
                else None
            )
            if not self.show_context(context, payload):
                return
            if self.prepared_context().signature != context.signature:
                self.notice("Your context changed. Open Review request context again before sending.")
                return
            self.submit(
                review_answer=routing,
                expected_signature=context.signature,
                reviewed_request=None if routing else context.request,
            )
        except MayaError as exc:
            self.notice(str(exc))
        except (sqlite3.Error, OSError):
            self.submit_error()

    def submit(self, review_answer=False, expected_signature=None, reviewed_request=None) -> None:
        """Validate credentials/model/context, redact secrets with review, then stream in a worker."""
        if self.quitting or self.paused or self.capturing or self.answering or self.review_dialog:
            return
        try:
            context = self.prepared_context()
            if expected_signature and context.signature != expected_signature:
                self.notice("Your context changed. Open Review request context again before sending.")
                return
            question, image, skill = context.question, context.request.messages[-1].image, context.skill
            name = self.settings.provider
            provider = create_provider(self.settings, self.secrets.get(name, self.settings.urls[name]))
            decision = RoutingDecision(
                skill,
                "manual" if self.settings.skill != "auto" else "local",
                "User-selected profile" if self.settings.skill != "auto" else "Local task matching",
            )
            settings, instructions, model = (
                deepcopy(self.settings),
                deepcopy(self.instructions),
                self.selected_model,
            )
            if settings.skill == "auto" and settings.classifier_enabled:
                try:
                    key = self.secrets.get("gemini", settings.urls["gemini"])
                except MayaError:
                    key = ""
                if key:
                    identity = catalog_identity(settings.urls["gemini"], key)
                    try:
                        models, _ = self.history.cached_models("gemini", identity)
                    except (sqlite3.Error, OSError):
                        models = []
                    router = TaskRouter(
                        instructions,
                        GeminiProvider("gemini", settings.urls["gemini"], key),
                        models,
                        settings.classifier_model,
                    )
                    # Snapshot the title before the user changes applications while the job is running.
                    title = self.last_window.title
                    job = Job(
                        lambda token: router.route(question, title, token),
                        Cancellation(settings.classifier_timeout),
                    )
                    self.routing_job = job

                    def complete(result):
                        if self.routing_job is not job or self.quitting:
                            return
                        self.routing_job = None
                        if result.models:
                            try:
                                self.history.cache_models("gemini", list(result.models), identity)
                            except (sqlite3.Error, OSError):
                                pass  # Cache failure must not prevent a valid answer.
                        self.begin_answer(
                            question,
                            image,
                            provider,
                            model,
                            settings,
                            instructions,
                            result,
                            review_answer=review_answer,
                            expected_signature=expected_signature,
                        )

                    def failed(text):
                        if self.routing_job is not job or self.quitting:
                            return
                        self.routing_job = None
                        fallback = RoutingDecision(skill, note="Local fallback · Gemini routing unavailable")
                        self.begin_answer(
                            question,
                            image,
                            provider,
                            model,
                            settings,
                            instructions,
                            fallback,
                            review_answer=review_answer,
                            expected_signature=expected_signature,
                        )

                    job.result.connect(complete)
                    job.error.connect(failed)
                    self.notice("")
                    self.state("thinking", "Choosing a task skill with Gemini… · Stop keeps your draft")
                    self.start_job(job)
                    return
                decision = RoutingDecision(skill, note="Local fallback · no Gemini routing key configured")
            self.begin_answer(
                question,
                image,
                provider,
                model,
                settings,
                instructions,
                decision,
                review_answer=review_answer,
                expected_signature=expected_signature,
                reviewed_request=reviewed_request,
            )
        except MayaError as exc:
            self.submit_error(str(exc))
        except (sqlite3.Error, OSError):
            self.submit_error()

    def begin_answer(
        self,
        question,
        image,
        provider,
        model,
        settings,
        instructions,
        decision,
        review_answer=False,
        expected_signature=None,
        reviewed_request=None,
    ) -> None:
        """Commit the validated turn atomically after routing, then start a fresh cancellable stream."""
        if self.quitting or self.paused:
            return
        try:
            skill = decision.skill
            if expected_signature and self.prepared_context().signature != expected_signature:
                self.notice(
                    "Your context changed during routing. Open Review request context again; your draft is kept."
                )
                self.state("idle", "Context review cancelled · your draft is kept")
                return
            memories = self.history.relevant_memories(question, skill.id) if settings.remember_enabled else []
            prior = self.messages[:-2] if self.draft_edit and len(self.messages) >= 2 else self.messages
            user = Message("user", question, image=image)
            context = prepare_context(
                question,
                image,
                model,
                settings,
                instructions,
                skill,
                memories,
                prior,
                self.last_window.title,
                self.draft_edit,
                self.chat_id,
            )
            request = reviewed_request or context.request
            if review_answer:
                self.state("idle", "Routing finished · review the answer context before sending")
                if not self.show_context(
                    context, note=f"{decision.note}. Review this final answer context before Send."
                ):
                    self.state("idle", "Context review cancelled · your draft is kept")
                    return
                if (
                    self.prepared_context(skill).signature != context.signature
                    or self.quitting
                    or self.paused
                    or self.capturing
                ):
                    self.notice("Your context changed. Open Review request context again before sending.")
                    return
                request = context.request
            assistant = Message("assistant", "", "streaming")
            if settings.save_history:
                replace_from = self.messages[-2].id if self.draft_edit and len(self.messages) >= 2 else None
                self.chat_id, user.id, assistant.id = self.history.begin_turn(
                    self.chat_id, user, assistant, settings.provider, model.id, replace_from
                )
            if self.draft_edit:
                self.truncate_last_turn()
                self.draft_edit = False
            self.notice("")
            self.set_question("")
            if len(self.messages) >= 200:
                # Saved history remains available; cap live widgets and image references in long sessions.
                self.messages = self.messages[-198:]
                self.messages_reset.emit(self.messages)
            self.messages.extend([user, assistant])
            self.message_added.emit(user)
            self.message_added.emit(assistant)
            self.reuse_image = image
            self.pending_image = image  # Reuse remains visible and removable for follow-ups.
            self.attachment_changed.emit()
            self.last_routing = decision
            self.routing_changed.emit()
            self.generation = Generation(provider, request, settings.retries, settings.timeout)
            self.generation.delta.connect(self.receive_delta)
            self.generation.ended.connect(self.generation_ended)
            self.buffer = ""
            self.flush_timer.start()
            self.state("thinking", f"Thinking · {skill.name} · {decision.source} routing")
            self.start_job(self.generation)
        except MayaError as exc:
            self.submit_error(str(exc))
        except (sqlite3.Error, OSError):
            self.submit_error()

    def submit_error(self, text="") -> None:
        """Keep the draft and existing turns available after validation or persistence failures."""
        self.notice(
            text
            or (
                "Could not save this turn locally. Your draft is kept. Check disk space/permissions, "
                "or disable History and Memory in Settings to continue without the database."
            )
        )
        self.state("error", "Ready to retry after adjusting context or Settings")

    def explain_routing(self) -> None:
        """Expose the chosen instructions' provenance without treating model confidence as a benchmark."""
        if self.last_routing:
            decision = self.last_routing
            self.notice(
                f"Skill: {decision.skill.name}. {decision.note}. Choose a profile above to override Auto."
            )
        else:
            self.notice(
                "No answer has been routed yet. Auto uses local matching, or Gemini when enabled in Smart routing."
            )

    def receive_delta(self, text: str) -> None:
        """Buffer small deltas to avoid a Qt repaint for every token."""
        self.buffer += text
        if sum(len(message.text) for message in self.messages[-1:]) + len(self.buffer) > 400000:
            self.stop()
            self.notice("This response reached the local display limit. Start a new question to continue.")

    def flush(self) -> None:
        """Apply buffered text every 45 ms to the shared message and visible panels."""
        if self.buffer and self.messages and self.messages[-1].role == "assistant":
            self.messages[-1].text += self.buffer
            self.buffer = ""
            self.message_updated.emit()
            self.state("streaming", "Receiving answer… · Stop keeps the partial text")

    def generation_ended(self, status: str, note: str, metrics: dict) -> None:
        """Persist final/partial text once; history statuses distinguish errors and user stops."""
        self.flush()
        self.flush_timer.stop()
        if self.messages and self.messages[-1].role == "assistant":
            message = self.messages[-1]
            message.status = status
            try:
                self.history.update_message(message)
            except (sqlite3.Error, OSError):
                note += " The response remains visible, but could not be saved locally. Copy or export it."
        self.generation = None
        self.message_updated.emit()
        first = metrics.get("first")
        latency = f"{metrics.get('total', 0):.1f}s total" + (
            f" · first text {first:.1f}s" if first is not None else ""
        )
        self.state(
            "paused" if self.paused else "error" if status == "error" else "idle",
            f"{status.title()} · {latency}",
        )
        self.notice(note + (" Use More → Regenerate or Continue." if status == "error" else ""))

    def stop(self) -> None:
        """Stop closes the active stream without blocking the GUI or deleting the partial answer."""
        self.cancel_routing()
        if self.generation:
            self.generation.token.cancel()
            self.state("thinking", "Stopping generation…")

    def truncate_last_turn(self) -> None:
        """Replace the latest user/assistant pair only for an explicit edit/regenerate action."""
        if len(self.messages) >= 2:
            # Persistence replacement already committed with begin_turn; history OFF preserves old saved text.
            self.messages = self.messages[:-2]
            self.messages_reset.emit(self.messages)

    def regenerate(self) -> None:
        """Retry the latest question and same in-memory attachment without duplicating the user turn."""
        if self.answering or len(self.messages) < 2:
            return
        self.draft_edit = True
        self.set_question(self.messages[-2].text)
        self.pending_image = self.messages[-2].image if self.settings.screen_enabled else None
        self.reuse_image = self.pending_image
        self.submit()

    def edit_last(self) -> None:
        """Load the last question for editing; the old turn is replaced only after a valid submit."""
        if not self.answering and len(self.messages) >= 2:
            self.draft_edit = True
            self.set_question(self.messages[-2].text)
            self.pending_image = self.messages[-2].image if self.settings.screen_enabled else None
            self.reuse_image = self.pending_image
            self.attachment_changed.emit()

    def continue_answer(self) -> None:
        """Ask for continuation with interrupted output quoted as user context, compatible with all adapters."""
        if not self.answering and self.messages and self.messages[-1].role == "assistant":
            text = self.messages[-1].text[-16000:]
            self.set_question(
                "Continue the previous answer from where it stopped. Do not repeat finished sections.\n"
                "Previous answer excerpt (context only):\n" + text
            )
            self.submit()

    def copy_latest(self) -> None:
        """Copy only the most recent assistant response on explicit user intent."""
        response = next(
            (message.text for message in reversed(self.messages) if message.role == "assistant"), ""
        )
        QApplication.clipboard().setText(response)

    def paste(self) -> None:
        """Read clipboard text only when Paste context is clicked; the user reviews it in the draft."""
        value = QApplication.clipboard().text()
        self.set_question((self.question + "\n" + value).strip()[:200000])

    def remember_draft(self) -> None:
        """Save an explicitly reviewed draft as a local non-secret memory, never inferred from screenshots."""
        value, accepted = QInputDialog.getMultiLineText(
            self.visible_parent(), "Remember this", "Save a useful fact or preference locally:", self.question
        )
        if accepted:
            try:
                if redact(value)[1]:
                    raise MayaError("Secrets cannot be saved as memories.", "privacy")
                self.history.remember(value)
                self.notice("Memory saved locally. You can inspect or forget it in Settings → Memory.")
            except MayaError as exc:
                self.notice(str(exc))

    def feedback(self, message: Message, rating: int) -> None:
        """Record local feedback; helpfulness is not claimed as an automatic model-training benchmark."""
        if message.id is not None:
            try:
                self.history.rate(message.id, rating)
            except (sqlite3.Error, OSError):
                self.notice("Could not save feedback locally. Check the data folder and try again.")
                return
        self.notice("Feedback saved locally. Save a specific preference in Memory to shape future answers.")

    def new_chat(self) -> None:
        """Start a clean conversation without deleting existing saved history."""
        if self.answering or self.capturing:
            self.notice("Finish capture or stop the current answer before starting a new conversation.")
            return
        self.messages, self.chat_id = [], None
        self.pending_image = self.reuse_image = None
        self.draft_edit = False
        self.last_routing = None
        self.routing_changed.emit()
        self.set_question("")
        self.messages_reset.emit([])
        self.attachment_changed.emit()
        self.notice("")
        self.state("idle", "New conversation · ready")

    def show_history(self) -> None:
        """Load/delete selected local conversations; deletion always requires an explicit confirmation."""
        if self.answering or self.capturing:
            self.notice("Finish capture or stop the current answer before switching conversations.")
            return
        dialog = HistoryDialog(self.history, self.visible_parent())
        dialog.chat_deleted.connect(lambda chat: self.new_chat() if self.chat_id == chat else None)
        self.desktop.exclude_capture(int(dialog.winId()))
        if dialog.exec_() == QDialog.Accepted and dialog.chosen is not None:
            self.chat_id = dialog.chosen
            self.messages = self.history.messages(self.chat_id)[-200:]
            self.pending_image = self.reuse_image = None
            self.draft_edit = False
            self.last_routing = None
            self.routing_changed.emit()
            self.set_question("")
            self.messages_reset.emit(self.messages)
            self.attachment_changed.emit()
            self.notice("History restored. Attach a new screenshot for screen-based follow-ups.")

    def export(self) -> None:
        """Export visible text to a user-selected Markdown file; no credentials or screenshot bytes are exported."""
        path, _ = QFileDialog.getSaveFileName(
            self.visible_parent(), "Export conversation", "Maya conversation.md", "Markdown (*.md)"
        )
        if path:
            try:
                body = "# Maya the Helper conversation\n\n"
                for message in self.messages:
                    body += f"## {'You' if message.role == 'user' else 'Maya'}\n\n{message.text}\n\n"
                    if message.image:
                        body += "[Screenshot was attached; image is not exported.]\n\n"
                    if message.status != "complete":
                        body += f"Status: {message.status}\n\n"
                Path(path).write_text(body, encoding="utf-8")
                self.notice("Conversation exported.")
            except OSError:
                self.notice("Could not export this file. Choose a writable folder.")

    def visible_parent(self):
        """Attach dialogs to whichever mode is currently visible."""
        return self.main if self.main.isVisible() else self.mini if self.mini.isVisible() else None

    def restore_geometry(self) -> None:
        """Restore placement only inside a currently connected screen's available work area."""
        screens = QApplication.screens()
        bounds = QApplication.primaryScreen().availableGeometry()
        # Default client size must leave room for the native title bar on small laptop screens.
        self.main.resize(
            min(self.main.width(), bounds.width() - 20), min(self.main.height(), bounds.height() - 45)
        )
        geometry = self.settings.window_geometry
        if len(geometry) == 4:
            requested = QRect(*geometry)
            # Migrate the previous release's default while preserving deliberately resized workbenches.
            if geometry[2:] == [560, 620]:
                requested.setSize(self.main.size())
            screen = next(
                (screen for screen in screens if screen.availableGeometry().contains(requested.center())),
                None,
            )
            if screen:
                available = screen.availableGeometry()
                requested.setWidth(min(max(MAIN_MIN[0], requested.width()), available.width()))
                requested.setHeight(min(max(MAIN_MIN[1], requested.height()), available.height() - 45))
                requested.moveLeft(
                    max(available.left(), min(requested.left(), available.right() - requested.width() + 1))
                )
                requested.moveTop(
                    max(available.top(), min(requested.top(), available.bottom() - requested.height() + 1))
                )
                self.main.setGeometry(requested)
        position = self.settings.orb_position
        if len(position) == 2 and any(
            screen.availableGeometry().contains(QPoint(*position)) for screen in screens
        ):
            point = QPoint(*position)
            screen = QApplication.screenAt(point) or QApplication.primaryScreen()
            available = screen.availableGeometry()
            self.orb.move(
                max(available.left(), min(point.x(), available.right() - self.orb.width())),
                max(available.top(), min(point.y(), available.bottom() - self.orb.height())),
            )
        else:
            self.orb.move(bounds.right() - self.orb.width() - 18, bounds.center().y())

    def remember_geometry(self) -> None:
        """Save normal window placement and the orb's current position outside the repository."""
        if not self.main.isMinimized():
            rect = self.main.geometry()
            self.settings.window_geometry = [rect.x(), rect.y(), rect.width(), rect.height()]
        self.settings.orb_position = [self.orb.x(), self.orb.y()]
        self.save_settings()

    def show_normal(self) -> None:
        """Open the full conversation, preserving draft/model/attachment from the floating mode."""
        self.mini.hide()
        self.orb.hide()
        self.main.showNormal()
        self.main.raise_()
        self.main.activateWindow()
        self.settings.mode = "normal"
        self.save_settings()

    def compact_window(self) -> None:
        """Bring the normal conversation back to its compact default and save the new placement."""
        self.show_normal()
        self.main.compact_size()
        self.remember_geometry()

    def toggle_pin(self) -> None:
        """Persist the user's top-layer choice; changing flags preserves the conversation and draft."""
        self.settings.pin_main = not self.settings.pin_main
        self.save_settings()
        self.config_changed.emit()

    def apply_pin(self) -> None:
        """Qt may recreate a native handle when flags change, so restore visibility and capture exclusion."""
        if bool(self.main.windowFlags() & Qt.WindowStaysOnTopHint) == self.settings.pin_main:
            return
        visible, state, geometry = self.main.isVisible(), self.main.windowState(), self.main.geometry()
        self.main.setWindowFlag(Qt.WindowStaysOnTopHint, self.settings.pin_main)
        self.main.setGeometry(geometry)
        self.main.setWindowState(state)
        if visible:
            self.main.show()
        self.desktop.exclude_capture(int(self.main.winId()))

    def show_overlay(self) -> None:
        """Move to the non-activating orb, preserving the full conversation in memory."""
        self.remember_geometry()
        self.main.hide()
        self.mini.hide()
        self.orb.show()
        self.settings.mode = "overlay"
        self.save_settings()

    def expand(self) -> None:
        """Anchor the compact panel next to the orb and clamp it inside the selected monitor."""
        if self.mini.isVisible():
            self.mini.hide()
            return
        available = (
            QApplication.screenAt(self.orb.geometry().center()) or QApplication.primaryScreen()
        ).availableGeometry()
        self.mini.resize(
            min(MINI_SIZE[0], available.width() - 20), min(MINI_SIZE[1], available.height() - 20)
        )
        x = self.orb.x() - self.mini.width() - 10
        if x < available.left():
            x = self.orb.x() + self.orb.width() + 10
        x = max(available.left() + 8, min(x, available.right() - self.mini.width() - 8))
        y = max(available.top() + 8, min(self.orb.y() - 180, available.bottom() - self.mini.height() - 8))
        self.mini.move(x, y)
        self.mini.show()
        self.desktop.exclude_capture(int(self.mini.winId()))

    def collapse(self) -> None:
        """Hide the compact panel while leaving the orb available."""
        self.mini.hide()

    def toggle_visible(self) -> None:
        """Preserve the legacy Alt+Shift+N show/hide behavior for the current operating mode."""
        if (
            self.main.isVisible()
            or self.orb.isVisible()
            or self.mini.isVisible()
            or self.clipboard_window.isVisible()
        ):
            self.clipboard_restore = self.clipboard_window.isVisible()
            self.clipboard_window.hide()
            self.remember_geometry()
            self.main.hide()
            self.mini.hide()
            self.orb.hide()
        elif self.clipboard_restore:
            self.clipboard_restore = False
            self.show_clipboard()
        elif self.settings.mode == "overlay":
            self.orb.show()
        else:
            self.show_normal()

    def ask_screen(self) -> None:
        """Show the panel and capture only if the persisted screen toggle is already ON."""
        if not self.settings.screen_enabled:
            self.notice("Screen context is OFF. Open Maya and turn it on before capturing.")
            if not self.main.isVisible():
                self.orb.show()
                if not self.mini.isVisible():
                    self.expand()
            return
        if not self.main.isVisible():
            self.orb.show()
            if not self.mini.isVisible():
                self.expand()
        self.capture_screen()

    def ask_text(self) -> None:
        """Open a text-only draft by removing image context; screen toggle remains under user control."""
        self.remove_attachment()
        self.orb.show()
        if not self.mini.isVisible():
            self.expand()

    def toggle_pause(self) -> None:
        """Pause all new operations and stop generation; Resume is a visible explicit action."""
        self.paused = not self.paused
        if self.paused:
            self.clipboard_window.set_watching(False)
            self.stop()
        self.state("paused" if self.paused else "idle", "Maya is paused" if self.paused else "Maya is ready")

    def tray_clicked(self, reason) -> None:
        """A tray double-click opens the normal conversation without starting any request."""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_normal()

    def track_window(self) -> None:
        """Remember the last external foreground window for profile inference and explicit window capture."""
        own = {int(widget.winId()) for widget in QApplication.topLevelWidgets()}
        window = self.desktop.active_window(own)
        if window.handle:
            self.last_window = window

    def scroll_answer(self, delta: int) -> None:
        """Retain the reference's Alt+Shift+Up/Down answer-scrolling shortcuts."""
        if self.clipboard_window.isVisible():
            self.clipboard_window.scroll_text(delta)
            return
        view = self.main.panel.view if self.main.isVisible() else self.mini.panel.view
        bar = view.scroll.verticalScrollBar()
        bar.setValue(bar.value() + delta)

    def show_clipboard(self) -> None:
        """Open the reference-compatible floating viewer with watching OFF until explicitly enabled."""
        window = self.clipboard_window
        screen = QApplication.screenAt(self.orb.geometry().center()) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        window.resize(min(window.width(), bounds.width() - 20), min(window.height(), bounds.height() - 20))
        window.move(
            max(bounds.left() + 8, min(window.x(), bounds.right() - window.width() - 8)),
            max(bounds.top() + 8, min(window.y(), bounds.bottom() - window.height() - 8)),
        )
        window.show()
        self.desktop.exclude_capture(int(window.winId()))

    def apply_hotkeys(self) -> None:
        """Register configured shortcuts and report conflicts instead of silently promising they work."""
        self.desktop.unregister_hotkeys()
        for identifier, shortcut in (
            (1, self.settings.hotkey),
            (2, self.settings.capture_hotkey),
            (3, self.settings.screen_hotkey),
            (4, "Alt+Shift+Up"),
            (5, "Alt+Shift+Down"),
        ):
            try:
                self.desktop.register_hotkey(int(self.main.winId()), identifier, shortcut)
            except MayaError as exc:
                self.notice(str(exc))

    def quit(self) -> None:
        """Coordinate cancellation and wait asynchronously for worker cleanup before Qt exits."""
        if self.quitting:
            return
        self.quitting = True
        if self.review_dialog:
            self.review_dialog.reject()
        self.capture_guard.stop()
        self.cancel_routing()
        self.clipboard_window.hide()
        self.remember_geometry()
        self.desktop.unregister_hotkeys()
        self.window_timer.stop()
        self.tray.hide()
        self.state("thinking", "Closing connections and saving the partial answer…")
        for job in list(self.jobs):
            job.token.cancel()
        if not self.jobs:
            QApplication.instance().quit()
