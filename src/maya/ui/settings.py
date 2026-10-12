"""Dedicated settings tabs and dynamic searchable model selection."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from urllib.parse import urlsplit
from uuid import uuid4
import sqlite3

from PyQt5.QtCore import QEvent, QTimer, Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from maya import __version__
from maya.core.config import PROVIDERS, validate_url
from maya.core.prompts import InstructionManager
from maya.core.safety import redact
from maya.platform.secrets import catalog_identity
from maya.core.types import MayaError, Model
from .widgets import CredentialEdit, button, label
from .branding import MayaMark


# --- Model lists rely on discovery metadata, with independent all/free searches. ---
class ModelPicker(QDialog):
    """Search hundreds of live models without making up IDs or inferring free pricing from absent values."""

    def __init__(
        self, models: list[Model], selected: str, refreshed: float, parent=None, *, allow_manual: bool = True
    ):
        """Build keyboard-navigable all/free lists and a conservative compatible-model fallback."""
        super().__init__(parent)
        self.setWindowTitle("Choose a model — Maya")
        self.resize(710, 570)
        self.models = models
        self.match_summaries = []
        self.empty_hints = []
        self.chosen = None
        self.choice_identity = None
        layout = QVBoxLayout(self)
        layout.addWidget(label("Choose your model", "heading"))
        time_label = datetime.fromtimestamp(refreshed).strftime("%H:%M") if refreshed else "not loaded"
        layout.addWidget(
            label(f"Catalog refreshed: {time_label} · discovery does not guarantee account quota or access")
        )
        self.tabs = QTabWidget()
        self.filters = []
        for title, free_only in (("All models", False), ("Free models", True)):
            panel = QWidget()
            box = QVBoxLayout(panel)
            search = QLineEdit()
            search.setPlaceholderText("Search by model name or ID")
            options = QHBoxLayout()
            vision = QCheckBox("Vision only")
            sort = QComboBox()
            sort.addItems(["Name", "Largest context first"])
            options.addWidget(vision)
            options.addStretch()
            options.addWidget(sort)
            listing = QListWidget()
            listing.setAccessibleName(title)
            summary = label("")
            empty = label("")
            box.addWidget(search)
            box.addLayout(options)
            box.addWidget(summary)
            box.addWidget(empty)
            box.addWidget(listing, 1)
            if free_only:
                box.addWidget(
                    label(
                        "Free models can have strict quotas or disappear. A zero token price does not guarantee unlimited use."
                    )
                )
            self.filters.append((search, vision, sort, listing, free_only))
            self.match_summaries.append(summary)
            self.empty_hints.append(empty)
            search.textChanged.connect(self.refilter)
            vision.toggled.connect(self.refilter)
            sort.currentIndexChanged.connect(self.refilter)
            listing.itemDoubleClicked.connect(self.choose)
            self.tabs.addTab(panel, title)
        layout.addWidget(self.tabs, 1)
        self.unknown_vision = QCheckBox("I have verified image input support for this unknown/manual model")
        layout.addWidget(self.unknown_vision)
        row = QHBoxLayout()
        self.manual = QLineEdit()
        self.manual.setEnabled(allow_manual)
        self.manual.setVisible(allow_manual)
        self.manual.setPlaceholderText(
            "Compatible/local endpoint: manual model ID if discovery is unavailable"
        )
        row.addWidget(self.manual, 1)
        layout.addLayout(row)
        actions = QHBoxLayout()
        actions.addWidget(button("Reset filters", self.reset_filters))
        actions.addStretch()
        actions.addWidget(button("Cancel", self.reject))
        self.use_button = button("Use model", self.choose, True)
        actions.addWidget(self.use_button)
        layout.addLayout(actions)
        self.refilter()
        self.manual.textChanged.connect(self.update_choice)
        self.tabs.currentChanged.connect(self.update_choice)
        for _, _, _, listing, _ in self.filters:
            listing.currentItemChanged.connect(self.update_choice)
        for _, _, _, listing, _ in self.filters:
            for index in range(listing.count()):
                if listing.item(index).data(Qt.UserRole).id == selected:
                    listing.setCurrentRow(index)

    def refilter(self) -> None:
        """Filter each tab independently while retaining the selected model where possible."""
        for index, (search, vision, sort, listing, free_only) in enumerate(self.filters):
            current = listing.currentItem()
            selected = current.data(Qt.UserRole).id if current else ""
            query = search.text().casefold().strip()
            matching = [
                model
                for model in self.models
                if (not free_only or model.free)
                and (not vision.isChecked() or model.vision)
                and query in (model.name + " " + model.id).casefold()
            ]
            matching.sort(key=lambda model: -model.context if sort.currentIndex() else model.name.casefold())
            listing.clear()
            for model in matching:
                badge = (
                    "VISION" if model.vision else "IMAGE SUPPORT UNKNOWN" if model.vision is None else "TEXT"
                )
                item = QListWidgetItem(
                    f"{model.name}\n{model.id}   ·   {badge}   ·   {'FREE · ' if model.free else ''}{model.context:,} context"
                )
                item.setData(Qt.UserRole, model)
                listing.addItem(item)
                if model.id == selected:
                    listing.setCurrentItem(item)
            if listing.count() and listing.currentRow() < 0:
                listing.setCurrentRow(0)
            self.match_summaries[index].setText(
                f"{len(matching):,} {'free ' if free_only else ''}models shown · filters apply locally"
            )
            hint = (
                "No matches. Try another search, or reset the filters."
                if self.models
                else "No catalog is loaded. Refresh your provider in Settings, or enter a verified compatible/local ID."
                if self.manual.isEnabled()
                else "No catalog is loaded. Close this dialog and refresh the provider in Settings."
            )
            self.empty_hints[index].setText(hint)
            self.empty_hints[index].setVisible(not matching)
        self.update_choice()

    def update_choice(self, *args) -> None:
        """Keep selection actionable; an empty result cannot silently accept a previous model."""
        listing = self.filters[self.tabs.currentIndex()][3]
        manual = self.manual.text().strip() if self.manual.isEnabled() else ""
        model = listing.currentItem().data(Qt.UserRole) if listing.currentItem() else None
        identity = ("manual", manual) if manual else ("listed", model.id, model.provider) if model else None
        if identity != self.choice_identity:
            # Confirmation belongs to one model, not to whichever unknown result the user selects next.
            self.unknown_vision.setChecked(False)
            self.choice_identity = identity
        self.unknown_vision.setEnabled(bool(manual) or bool(model and model.vision is None))
        self.unknown_vision.setVisible(bool(manual) or bool(model and model.vision is None))
        self.use_button.setEnabled(
            bool(listing.currentItem() or (self.manual.isEnabled() and self.manual.text().strip()))
        )

    def reset_filters(self) -> None:
        """Reset only the active tab, preserving the other search and never refreshing the provider."""
        search, vision, sort, _, _ = self.filters[self.tabs.currentIndex()]
        search.clear()
        vision.setChecked(False)
        sort.setCurrentIndex(0)

    def choose(self, *args) -> None:
        """Accept an actual model or explicit manual ID; image support overrides require a checkbox."""
        manual = self.manual.text().strip()
        listing = self.filters[self.tabs.currentIndex()][3]
        item = listing.currentItem()
        if manual:
            if (
                not self.manual.isEnabled()
                or len(manual) > 200
                or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in manual)
            ):
                QMessageBox.information(
                    self, "Model ID", "Use a model ID without spaces (maximum 200 characters)."
                )
                return
            self.chosen = Model(
                manual, manual, "compatible", True if self.unknown_vision.isChecked() else None
            )
        elif item:
            self.chosen = item.data(Qt.UserRole)
            if self.chosen.vision is None and self.unknown_vision.isChecked():
                self.chosen = replace(self.chosen, vision=True)
        else:
            QMessageBox.information(
                self, "Choose a model", "Select a listed model or enter a compatible model ID."
            )
            return
        self.accept()


# --- Settings values are edited in a copy and committed only on explicit Save. ---
class SettingsDialog(QDialog):
    """Provider credentials, personalization, overlay preferences, local memories, and attribution."""

    def __init__(self, settings, secret_store, history, data_dir, parent=None):
        """Build tabs; never populate key fields with stored secrets or place secrets in labels."""
        super().__init__(parent)
        self.settings = deepcopy(settings)
        self.secrets, self.history, self.data_dir = secret_store, history, data_dir
        self.setWindowTitle("Settings — Maya the Helper")
        self.resize(680, 660)
        self.reveal_timer = QTimer(self)
        self.reveal_timer.setSingleShot(True)
        self.reveal_timer.setInterval(30000)
        self.reveal_timer.timeout.connect(self.conceal_key)
        outer = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(MayaMark(36))
        heading.addWidget(label("Make Maya work for you", "heading"), 1)
        outer.addLayout(heading)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self.create_providers()
        self.create_preferences()
        self.create_routing()
        self.create_profiles()
        self.create_memory()
        self.create_about()
        row = QHBoxLayout()
        row.addWidget(label("Credentials stay in Windows Credential Manager."))
        row.addStretch()
        row.addWidget(button("Cancel", self.reject))
        row.addWidget(button("Save & refresh models", self.save, True))
        outer.addLayout(row)

    def create_providers(self) -> None:
        """Configure primary providers and extension endpoints without silently redirecting keys."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.addWidget(label("Connect your model", "sectionTitle"))
        layout.addWidget(
            label("Use your own provider account. Your questions go directly to the model you choose.")
        )
        steps = QHBoxLayout()
        for number, title, description in (
            ("01", "Provider", "Choose where to connect"),
            ("02", "Your key", "Add it securely below"),
            ("03", "Model", "Save, then choose in chat"),
        ):
            card = QFrame()
            card.setObjectName("setupStep")
            box = QVBoxLayout(card)
            box.setSpacing(3)
            box.addWidget(label(number + "  /  " + title, "eyebrow"))
            box.addWidget(label(description))
            steps.addWidget(card, 1)
        layout.addLayout(steps)
        card = QFrame()
        card.setObjectName("settingsCard")
        form = QFormLayout(card)
        form.setContentsMargins(14, 14, 14, 14)
        form.setVerticalSpacing(10)
        layout.addWidget(card)
        self.provider = QComboBox()
        for identifier, title in PROVIDERS.items():
            self.provider.addItem(title, identifier)
        self.provider.setCurrentIndex(self.provider.findData(self.settings.provider))
        self.endpoint = QLineEdit()
        self.endpoint.setAccessibleName("Provider API base URL")
        self.endpoint.textChanged.connect(self.endpoint_changed)
        self.key = CredentialEdit()
        self.key.setAccessibleName("New API key")
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("Paste a new key here; blank keeps the stored key")
        self.show_key = button("Show")
        self.show_key.setObjectName("quiet")
        self.show_key.setCheckable(True)
        self.show_key.setAutoDefault(False)
        self.show_key.setAccessibleName("Temporarily reveal the new API key")
        self.show_key.setToolTip("Show only the key you typed; mask again after 30 seconds or on focus loss")
        self.show_key.toggled.connect(self.reveal_key)
        self.key.conceal_requested.connect(self.conceal_key)
        self.key.textChanged.connect(self.key_edited)
        key_row = QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.addWidget(self.key, 1)
        key_row.addWidget(self.show_key)
        clear = button("Clear input", self.key.clear)
        clear.setObjectName("quiet")
        clear.setAutoDefault(False)
        clear.setToolTip("Discard the typed key; the stored credential is kept")
        key_row.addWidget(clear)
        self.key_state = label("")
        self.provider.currentIndexChanged.connect(self.provider_changed)
        form.addRow("Provider", self.provider)
        form.addRow("Base URL", self.endpoint)
        form.addRow("API key", key_row)
        form.addRow("Credential status", self.key_state)
        form.addRow(button("Remove stored key", self.remove_key))
        layout.addWidget(
            label(
                "Gemini and OpenRouter are the primary integrations. Compatible endpoints use Chat Completions. "
                "Local Ollama needs a running server and installed models. Maya never downloads a model automatically."
            )
        )
        layout.addWidget(
            label(
                "Stored keys are never shown here. Blank keeps the current key; Cancel discards your typed key."
            )
        )
        layout.addStretch()
        self.tabs.addTab(page, "Providers")
        self.provider_changed()

    def provider_changed(self) -> None:
        """Update the selected endpoint and masked-key status, clearing an unsaved key on provider switches."""
        identifier = self.provider.currentData()
        self.endpoint.setText(self.settings.urls[identifier])
        self.endpoint.setReadOnly(identifier in {"gemini", "openrouter", "anthropic"})
        self.key.clear()
        self.key.setEnabled(identifier != "ollama")
        self.key_edited()
        self.refresh_key_state()

    def endpoint_changed(self) -> None:
        """Discard typed credentials when their destination changes; never carry a key to another host."""
        if hasattr(self, "key"):
            self.key.clear()
            self.conceal_key()
            self.refresh_key_state()

    def refresh_key_state(self) -> None:
        """Report availability for the URL currently displayed, including endpoint-bound environment keys."""
        identifier = self.provider.currentData()
        try:
            available = bool(self.secrets.get(identifier, validate_url(self.endpoint.text())))
            self.key_state.setText(
                "Key available for this endpoint (kept hidden)"
                if available
                else "Add your key for this endpoint"
                if identifier != "ollama"
                else "No key needed"
            )
        except MayaError as exc:
            self.key_state.setText(str(exc))

    def key_edited(self) -> None:
        """Enable reveal only for a nonempty typed key; clearing input stops the reveal timer."""
        self.show_key.setEnabled(bool(self.key.text()) and self.key.isEnabled())
        if not self.key.text():
            self.conceal_key()

    def reveal_key(self, revealed: bool) -> None:
        """Briefly reveal only explicit input, retaining keyboard focus in its editor."""
        visible = revealed and bool(self.key.text())
        self.key.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.show_key.setText("Hide" if visible else "Show")
        if visible:
            self.key.setFocus()
            self.reveal_timer.start()
        else:
            self.reveal_timer.stop()

    def conceal_key(self) -> None:
        """Mask again on blur, timeout, tab/window hide or provider change without deleting a saved key."""
        self.show_key.setChecked(False)
        self.key.setEchoMode(QLineEdit.Password)
        self.reveal_timer.stop()

    def changeEvent(self, event) -> None:
        if (
            event.type() == QEvent.ActivationChange
            and not self.isActiveWindow()
            and hasattr(self, "show_key")
        ):
            self.conceal_key()
        super().changeEvent(event)

    def reject(self) -> None:
        """Cancel releases the unsaved typed credential instead of retaining it in a hidden dialog."""
        self.key.clear()
        self.conceal_key()
        super().reject()

    def remove_key(self) -> None:
        """Delete the selected app credential after an explicit UI confirmation."""
        if (
            QMessageBox.question(
                self, "Remove API key", "Remove Maya's saved key for this provider/endpoint?"
            )
            != QMessageBox.Yes
        ):
            return
        try:
            self.secrets.remove(self.provider.currentData(), validate_url(self.endpoint.text()))
            self.key.clear()
            self.refresh_key_state()
        except MayaError as exc:
            QMessageBox.information(self, "Credentials", str(exc))

    def create_preferences(self) -> None:
        """Expose bounded generation, privacy and shortcut settings in one predictable form."""
        page = QWidget()
        page.setObjectName("settingsPage")
        form = QFormLayout(page)
        self.name = QLineEdit(self.settings.display_name)
        self.language = QLineEdit(self.settings.language)
        self.style = QLineEdit(self.settings.response_style)
        self.remember = QCheckBox("Use my approved local memories in answers")
        self.remember.setChecked(self.settings.remember_enabled)
        self.save_history = QCheckBox("Save new conversations locally")
        self.save_history.setChecked(self.settings.save_history)
        self.redact = QCheckBox("Redact recognizable secrets in questions before sending")
        self.redact.setChecked(self.settings.redact_text)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0, 2)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(self.settings.temperature)
        self.output = QSpinBox()
        self.output.setRange(128, 65536)
        self.output.setValue(self.settings.max_output)
        self.timeout = QSpinBox()
        self.timeout.setRange(15, 600)
        self.timeout.setValue(self.settings.timeout)
        self.context = QSpinBox()
        self.context.setRange(2048, 200000)
        self.context.setValue(self.settings.context_budget)
        self.edge = QSpinBox()
        self.edge.setRange(512, 4096)
        self.edge.setValue(self.settings.image_edge)
        self.size = QSpinBox()
        self.size.setRange(44, 84)
        self.size.setValue(self.settings.orb_size)
        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.35, 1)
        self.opacity.setSingleStep(0.05)
        self.opacity.setValue(self.settings.orb_opacity)
        self.pin_main = QCheckBox("Keep the main Maya window above other applications")
        self.pin_main.setChecked(self.settings.pin_main)
        self.reduce_motion = QCheckBox("Use a static Maya icon during activity")
        self.reduce_motion.setChecked(self.settings.reduce_motion)
        self.overlay_opacity = QDoubleSpinBox()
        self.overlay_opacity.setRange(0.65, 1)
        self.overlay_opacity.setSingleStep(0.05)
        self.overlay_opacity.setValue(self.settings.overlay_opacity)
        self.hotkey = QLineEdit(self.settings.hotkey)
        self.capture_key = QLineEdit(self.settings.capture_hotkey)
        self.screen_key = QLineEdit(self.settings.screen_hotkey)
        for title, widget in (
            ("Your name", self.name),
            ("Answer language", self.language),
            ("Answer style", self.style),
            ("Memory", self.remember),
            ("History", self.save_history),
            ("Typed secrets", self.redact),
            ("Temperature (native providers)", self.temperature),
            ("Maximum output tokens", self.output),
            ("Context budget (estimate)", self.context),
            ("Request timeout (seconds)", self.timeout),
            ("Screenshot longest edge", self.edge),
            ("Orb size", self.size),
            ("Idle orb opacity", self.opacity),
            ("Main window", self.pin_main),
            ("Reduced motion", self.reduce_motion),
            ("Floating panel opacity", self.overlay_opacity),
            ("Show/hide shortcut", self.hotkey),
            ("Capture shortcut", self.capture_key),
            ("Screen toggle shortcut", self.screen_key),
        ):
            form.addRow(title, widget)
        # Scroll the form so laptop displays can reach every preference without tiny controls.
        from PyQt5.QtWidgets import QScrollArea

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "Preferences")

    def create_routing(self) -> None:
        """Make the separate Google classification call and its transmitted context an explicit choice."""
        page = QWidget()
        page.setObjectName("settingsPage")
        box = QVBoxLayout(page)
        self.routing_enabled = QCheckBox("Use Gemini to choose a skill when task profile is Auto")
        self.routing_enabled.setChecked(self.settings.classifier_enabled)
        box.addWidget(self.routing_enabled)
        box.addWidget(
            label(
                "When enabled, Send makes an extra Gemini request, even if your answer uses another provider. "
                "It may consume quota or cost money. Gemini receives a redacted question excerpt (up to 2,000 "
                "characters), window title (200), and profile names/brief descriptions, including custom profiles. "
                "Screenshots, history and memories are excluded from classification."
            )
        )
        self.routing_model = QComboBox()
        self.routing_model.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.routing_model.setMinimumContentsLength(14)
        self.routing_model.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.routing_model.setMinimumWidth(150)
        self.routing_model.addItem("Auto · choose a discovered Flash/Lite model", "")
        try:
            key = self.secrets.get("gemini", self.settings.urls["gemini"])
            models, _ = (
                self.history.cached_models("gemini", catalog_identity(self.settings.urls["gemini"], key))
                if key
                else ([], 0)
            )
        except (MayaError, sqlite3.Error, OSError):
            models = []
        for model in sorted(models, key=lambda m: m.name.casefold()):
            if model.id.removeprefix("models/").startswith("gemini-"):
                self.routing_model.addItem(model.name + " · " + model.id, model.id)
        index = self.routing_model.findData(self.settings.classifier_model)
        if index < 0:
            self.routing_model.addItem(
                "Saved routing ID · " + self.settings.classifier_model, self.settings.classifier_model
            )
            index = self.routing_model.count() - 1
        self.routing_model.setCurrentIndex(index)
        self.routing_timeout = QSpinBox()
        self.routing_timeout.setRange(2, 30)
        self.routing_timeout.setValue(self.settings.classifier_timeout)
        form = QFormLayout()
        form.addRow("Gemini classifier model", self.routing_model)
        form.addRow("Routing deadline (seconds)", self.routing_timeout)
        box.addLayout(form)
        box.addWidget(
            label(
                "Add your Gemini key in Providers and refresh its model catalog to populate this list. "
                "Auto discovers models on Send if no fresh cache exists. A missing key, timeout, unavailable "
                "model or invalid/uncertain decision uses local matching. Choosing a task profile directly "
                "skips Gemini classification. Stop keeps your draft."
            )
        )
        self.instruction_library = QComboBox()
        self.instruction_library.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.instruction_library.setMinimumContentsLength(14)
        self.instruction_library.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.instruction_library.setMinimumWidth(150)
        # Search the instruction library locally; typing never starts classification or edits profiles.
        self.instruction_library.setEditable(True)
        self.instruction_library.setInsertPolicy(QComboBox.NoInsert)
        self.instruction_library.lineEdit().setPlaceholderText("Find a task skill…")
        self.instruction_library.setAccessibleName("Search task instructions")
        self.instruction_library.completer().setCaseSensitivity(Qt.CaseInsensitive)
        self.instruction_library.completer().setFilterMode(Qt.MatchContains)
        self.instruction_library.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.instruction_preview = QPlainTextEdit()
        self.instruction_preview.setReadOnly(True)
        self.instruction_preview.setMaximumHeight(150)
        for skill in InstructionManager(self.settings.custom_profiles).profiles():
            self.instruction_library.addItem(skill.name, skill)
        self.instruction_library.currentIndexChanged.connect(self.preview_instruction)
        box.addWidget(label("Instruction library · preview the guidance for each skill"))
        box.addWidget(self.instruction_library)
        box.addWidget(
            label("Type to find a skill. Previewing its guidance does not change your chat profile.")
        )
        box.addWidget(self.instruction_preview)
        self.preview_instruction()
        box.addStretch()
        from PyQt5.QtWidgets import QScrollArea

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "Smart routing")

    def preview_instruction(self) -> None:
        """Show saved guidance as plain text; user profiles never become executable plugins."""
        skill = self.instruction_library.currentData()
        self.instruction_preview.setPlainText(skill.instruction if skill else "")

    def create_memory(self) -> None:
        """Provide inspection, additions, and deletion of approved preferences rather than hidden extraction."""
        page = QWidget()
        box = QVBoxLayout(page)
        box.addWidget(
            label(
                "Maya remembers only what you explicitly save here or with Remember this. "
                "Approved memories can be sent with future requests when Memory is enabled. "
                "Memory additions, edits and deletions take effect immediately."
            )
        )
        self.memory_list = QListWidget()
        self.memory_list.currentItemChanged.connect(self.select_memory)
        self.memory_summary = label("", "muted")
        self.memory_summary.setAccessibleName("Saved memory summary")
        box.addWidget(self.memory_summary)
        box.addWidget(self.memory_list, 1)
        self.memory_text = QLineEdit()
        self.memory_text.setAccessibleName("Approved memory text")
        self.memory_text.setPlaceholderText("A useful preference, skill level, or fact — never a secret")
        self.scope = QComboBox()
        self.scope.setAccessibleName("Memory task scope")
        self.reload_scopes()
        box.addWidget(self.memory_text)
        box.addWidget(self.scope)
        row = QHBoxLayout()
        row.addWidget(button("Save new", self.add_memory))
        self.update_memory_button = button("Update selected", self.edit_memory)
        self.update_memory_button.setEnabled(False)
        row.addWidget(self.update_memory_button)
        self.forget_memory_button = button("Forget selected", self.forget_memory)
        self.forget_memory_button.setEnabled(False)
        row.addWidget(self.forget_memory_button)
        self.forget_all_button = button("Forget all", self.forget_all_memories)
        self.forget_all_button.setEnabled(False)
        row.addWidget(self.forget_all_button)
        row.addStretch()
        box.addLayout(row)
        self.tabs.addTab(page, "Memory")
        self.reload_memory()

    def reload_memory(self) -> None:
        """Show the latest saved memory records without exposing any credential store contents."""
        self.memory_list.clear()
        try:
            memories = self.history.memories()
        except (sqlite3.Error, OSError):
            self.memory_summary.setText("Memories could not be loaded. Reopen Settings to retry.")
            self.forget_all_button.setEnabled(False)
            QMessageBox.information(
                self, "Memory", "Could not read memories. Check the local data folder and reopen Settings."
            )
            return
        self.memory_summary.setText(
            "No saved memories. Add a preference when you want Maya to remember it."
            if not memories
            else f"{len(memories)} saved {'memory' if len(memories) == 1 else 'memories'}"
            + (" shown · the list is limited to 500" if len(memories) == 500 else "")
        )
        self.forget_all_button.setEnabled(bool(memories))
        for memory in memories:
            item = QListWidgetItem(f"[{memory['scope']}] {memory['text']}")
            item.setData(Qt.UserRole, memory)
            self.memory_list.addItem(item)

    def reload_scopes(self) -> None:
        """Include user profiles in memory scopes while preserving any current selection."""
        current = self.scope.currentData()
        self.scope.clear()
        for skill in InstructionManager(self.settings.custom_profiles).profiles():
            self.scope.addItem(skill.name, skill.id)
        self.scope.setCurrentIndex(max(0, self.scope.findData(current)))

    def select_memory(self, item, previous=None) -> None:
        """Load a selected memory into the editor; edits require an explicit Update selected action."""
        self.update_memory_button.setEnabled(bool(item))
        self.forget_memory_button.setEnabled(bool(item))
        if item:
            memory = item.data(Qt.UserRole)
            self.memory_text.setText(memory["text"])
            index = self.scope.findData(memory["scope"])
            if index < 0:
                self.scope.addItem("Unavailable profile · " + memory["scope"], memory["scope"])
                index = self.scope.count() - 1
            self.scope.setCurrentIndex(index)

    def edit_memory(self) -> None:
        """Apply one selected edit immediately to SQLite, retaining its stable memory ID."""
        item = self.memory_list.currentItem()
        if not item:
            return
        try:
            self.history.update_memory(
                item.data(Qt.UserRole)["id"], self.memory_text.text(), self.scope.currentData()
            )
            self.memory_text.clear()
            self.reload_memory()
        except MayaError as exc:
            QMessageBox.information(self, "Memory", str(exc))
        except (sqlite3.Error, OSError):
            QMessageBox.information(
                self,
                "Memory",
                "Could not update this memory. Your edit is kept; check the local data folder.",
            )

    def add_memory(self) -> None:
        """Save explicitly entered non-secret text; recognizable credentials are rejected."""
        try:
            text = self.memory_text.text()
            if redact(text)[1]:
                raise MayaError("Do not store API keys, passwords, or tokens as memories.", "privacy")
            self.history.remember(text, self.scope.currentData())
            self.memory_text.clear()
            self.reload_memory()
        except MayaError as exc:
            QMessageBox.information(self, "Memory", str(exc))
        except (sqlite3.Error, OSError):
            QMessageBox.information(
                self, "Memory", "Could not save this memory. Your text is kept; check the local data folder."
            )

    def forget_memory(self) -> None:
        """Remove a selected local memory only after confirmation."""
        item = self.memory_list.currentItem()
        if (
            item
            and QMessageBox.question(self, "Forget memory", "Forget this local memory?") == QMessageBox.Yes
        ):
            try:
                self.history.forget(item.data(Qt.UserRole)["id"])
                self.memory_text.clear()
                self.reload_memory()
            except (sqlite3.Error, OSError):
                QMessageBox.information(
                    self, "Memory", "Could not remove this memory. Check the local data folder."
                )

    def forget_all_memories(self) -> None:
        """Offer an explicit fresh memory slate; cancellation and disk errors preserve saved data."""
        if (
            QMessageBox.question(
                self, "Forget all memories", "Permanently forget all approved local memories?"
            )
            != QMessageBox.Yes
        ):
            return
        try:
            self.history.clear_memories()
            self.memory_text.clear()
            self.reload_memory()
        except (sqlite3.Error, OSError):
            QMessageBox.information(self, "Memory", "Could not clear memories. Check the local data folder.")

    # --- Custom instructions are staged with settings; built-in rules remain mandatory. ---
    def create_profiles(self) -> None:
        """Let users save reusable task preferences without editing Python or installing plugins."""
        page = QWidget()
        box = QVBoxLayout(page)
        box.addWidget(
            label(
                "Save instructions for your recurring work. Select the profile in either chat window. "
                "Shared safety and grounding rules still apply. Never put secrets here."
            )
        )
        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self.select_profile)
        box.addWidget(self.profile_list, 1)
        self.profile_name = QLineEdit()
        self.profile_name.setMaxLength(80)
        self.profile_name.setPlaceholderText("Profile name, e.g. Exam revision")
        self.profile_instruction = QPlainTextEdit()
        self.profile_instruction.setPlaceholderText("How should Maya help? Up to 4,000 characters.")
        self.profile_instruction.setMaximumHeight(150)
        box.addWidget(self.profile_name)
        box.addWidget(self.profile_instruction)
        row = QHBoxLayout()
        row.addWidget(button("New", self.new_profile))
        row.addWidget(button("Save profile", self.save_profile))
        row.addWidget(button("Delete selected", self.delete_profile))
        box.addLayout(row)
        box.addWidget(label("Profile changes take effect when you save this settings dialog."))
        self.tabs.addTab(page, "Task profiles")
        self.reload_profiles()

    def reload_profiles(self, selected: str = "") -> None:
        """Refresh the staged collection, optionally retaining the edited profile selection."""
        self.profile_list.clear()
        library_id = (
            self.instruction_library.currentData().id if self.instruction_library.currentData() else "general"
        )
        self.instruction_library.blockSignals(True)
        self.instruction_library.clear()
        for skill in InstructionManager(self.settings.custom_profiles).profiles():
            self.instruction_library.addItem(skill.name, skill)
            if skill.id == library_id:
                self.instruction_library.setCurrentIndex(self.instruction_library.count() - 1)
        self.instruction_library.blockSignals(False)
        self.preview_instruction()
        for identifier, profile in self.settings.custom_profiles.items():
            item = QListWidgetItem(profile["name"])
            item.setData(Qt.UserRole, identifier)
            self.profile_list.addItem(item)
            if identifier == selected:
                self.profile_list.setCurrentItem(item)
        if hasattr(self, "scope"):
            self.reload_scopes()

    def select_profile(self, item, previous=None) -> None:
        """Display a staged profile; typing alone never changes the saved collection."""
        profile = self.settings.custom_profiles.get(item.data(Qt.UserRole), {}) if item else {}
        self.profile_name.setText(profile.get("name", ""))
        self.profile_instruction.setPlainText(profile.get("instruction", ""))

    def new_profile(self) -> None:
        """Clear selection so Save profile creates a new ID instead of overwriting a prior profile."""
        self.profile_list.setCurrentRow(-1)
        self.profile_name.clear()
        self.profile_instruction.clear()
        self.profile_name.setFocus()

    def save_profile(self) -> bool:
        """Validate staged additions/edits transactionally, preserving prior text on validation failures."""
        item = self.profile_list.currentItem()
        identifier = item.data(Qt.UserRole) if item else "custom:" + uuid4().hex[:12]
        candidate = deepcopy(self.settings)
        profile = {
            "name": self.profile_name.text().strip(),
            "instruction": self.profile_instruction.toPlainText().strip(),
        }
        try:
            if redact(profile["name"] + "\n" + profile["instruction"])[1]:
                raise MayaError("Do not save API keys, passwords, or tokens in task profiles.", "privacy")
            candidate.custom_profiles[identifier] = profile
            candidate.validate()
            self.settings.custom_profiles = candidate.custom_profiles
            self.reload_profiles(identifier)
            return True
        except MayaError as exc:
            QMessageBox.information(self, "Task profile", str(exc))
            return False

    def delete_profile(self) -> None:
        """Remove a staged user profile; its memories remain inspectable and may be reassigned."""
        item = self.profile_list.currentItem()
        if (
            item
            and QMessageBox.question(self, "Delete task profile", "Delete this custom task profile?")
            == QMessageBox.Yes
        ):
            identifier = item.data(Qt.UserRole)
            del self.settings.custom_profiles[identifier]
            if self.settings.skill == identifier:
                self.settings.skill = "auto"
            self.reload_profiles()

    def create_about(self) -> None:
        """Describe the shared product and its boundaries without embedding a personal profile."""
        page = QWidget()
        box = QVBoxLayout(page)
        box.addWidget(label("Maya the Helper", "brand"))
        box.addWidget(label(f"Python desktop edition · {__version__}"))
        box.addWidget(
            label(
                "A small companion for coding, study, documents and everyday desktop work.\n\n"
                "Every installation starts with an empty profile and no saved memories. "
                "Add only the preferences you want Maya to use."
            )
        )
        box.addWidget(
            label(
                "Bring useful explanations into the work you are already doing. "
                "Maya reads your supplied context and explains; it never executes suggested commands."
            )
        )
        box.addWidget(label(f"Local data folder:\n{self.data_dir}"))
        box.addWidget(
            label(
                "No account, telemetry, analytics, or Maya cloud backend. Cloud model requests "
                "go directly to the provider you choose. Provider policies still apply."
            )
        )
        box.addStretch()
        self.tabs.addTab(page, "About")

    def save(self) -> None:
        """Validate all preferences and OS-backed key writes before returning the edited settings."""
        from maya.platform.windows import WindowsDesktop

        try:
            # Commit typed profile edits on the main Save too, so a draft is never silently lost.
            item = self.profile_list.currentItem()
            current = self.settings.custom_profiles.get(item.data(Qt.UserRole), {}) if item else {}
            draft = {
                "name": self.profile_name.text().strip(),
                "instruction": self.profile_instruction.toPlainText().strip(),
            }
            if (draft["name"] or draft["instruction"]) and draft != current and not self.save_profile():
                return
            values = self.settings
            values.provider = self.provider.currentData()
            endpoint = validate_url(self.endpoint.text())
            if values.provider == "ollama" and urlsplit(endpoint).hostname not in {
                "localhost",
                "127.0.0.1",
                "::1",
            }:
                raise MayaError("The Local Ollama provider requires a localhost URL.", "config")
            values.urls[values.provider] = endpoint
            values.display_name, values.language, values.response_style = (
                self.name.text().strip(),
                self.language.text(),
                self.style.text(),
            )
            values.remember_enabled, values.save_history, values.redact_text = (
                self.remember.isChecked(),
                self.save_history.isChecked(),
                self.redact.isChecked(),
            )
            values.temperature, values.max_output = self.temperature.value(), self.output.value()
            values.classifier_enabled = self.routing_enabled.isChecked()
            values.classifier_model = self.routing_model.currentData()
            values.classifier_timeout = self.routing_timeout.value()
            values.context_budget, values.timeout, values.image_edge = (
                self.context.value(),
                self.timeout.value(),
                self.edge.value(),
            )
            values.orb_size, values.orb_opacity = self.size.value(), self.opacity.value()
            values.pin_main = self.pin_main.isChecked()
            values.reduce_motion = self.reduce_motion.isChecked()
            values.overlay_opacity = self.overlay_opacity.value()
            values.hotkey, values.capture_hotkey, values.screen_hotkey = (
                self.hotkey.text(),
                self.capture_key.text(),
                self.screen_key.text(),
            )
            shortcuts = [values.hotkey, values.capture_hotkey, values.screen_hotkey]
            if len(set(shortcut.casefold() for shortcut in shortcuts)) != 3:
                raise MayaError("Choose three different global shortcuts.", "hotkey")
            for shortcut in shortcuts:
                WindowsDesktop.parse_hotkey(shortcut)
            values.validate()
            if self.key.text().strip():
                self.secrets.save(values.provider, endpoint, self.key.text())
            self.key.clear()
            self.accept()
        except (MayaError, OSError) as exc:
            QMessageBox.information(
                self,
                "Settings",
                str(exc)
                if isinstance(exc, MayaError)
                else "Could not save settings. Check data-folder permissions.",
            )
