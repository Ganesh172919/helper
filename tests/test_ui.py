"""Real Qt integration checks exercise state sharing, repeated sends, privacy, streaming, and stop."""

import time
import sqlite3

import pytest

from PIL import Image, ImageDraw
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest

from maya.capture import prepare
from maya.core.config import ConfigStore, Settings
from maya.core.storage import HistoryStore
from maya.core.types import Model, StreamEvent, MayaError, Message
from maya.ui.app import AppController
from maya.ui.settings import ModelPicker, SettingsDialog
from maya.ui.history import HistoryDialog
from maya.ui.workers import Generation


# --- Optional classification is part of Send, with draft-preserving cancellation and no auto tool use. ---
def test_gemini_routing_then_answer_uses_chosen_skill_memory_and_separate_provider(
    qapp, tmp_path, monkeypatch
):
    import json
    import httpx
    from maya.core.config import DEFAULT_URLS
    from maya.core.providers import GeminiProvider
    from maya.platform.secrets import catalog_identity

    app = controller(tmp_path, monkeypatch)
    app.settings.provider = "openrouter"
    app.settings.classifier_enabled = True
    app.settings.screen_enabled = True
    app.selected_model = Model("answer", "Answer model", "openrouter", True, 30000, 4096)
    image = prepare(Image.new("RGB", (50, 50), "white"), 512, check_blank=False)
    app.pending_image = image
    app.history.remember("I prefer join diagrams", "data")
    provider = FakeProvider()
    calls = []

    def handler(req):
        calls.append(req)
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-3.5-flash-lite",
                            "supportedGenerationMethods": ["generateContent"],
                        }
                    ]
                },
            )
        payload = json.loads(req.content)
        excerpt = json.loads(payload["contents"][0]["parts"][0]["text"])
        assert set(excerpt) == {"question_excerpt", "window_title", "available_profiles"}
        assert "join diagrams" not in req.content.decode() and "inlineData" not in req.content.decode()
        data = {
            "candidates": [
                {
                    "content": {"parts": [{"text": '{"skill_id":"data","confidence":0.9}'}]},
                    "finishReason": "STOP",
                }
            ]
        }
        return httpx.Response(200, content=("data: " + json.dumps(data) + "\n\n").encode())

    monkeypatch.setattr("maya.ui.app.create_provider", lambda settings, key: provider)
    monkeypatch.setattr(
        "maya.ui.app.GeminiProvider",
        lambda name, base, key: GeminiProvider(name, base, key, httpx.MockTransport(handler)),
    )
    app.set_question("Help explain these joins")
    app.submit()
    assert app.routing_job and not app.generation and not app.messages and app.question
    assert app.main.panel.stop.isEnabled() and not app.main.panel.send.isEnabled()
    app.submit()
    app.new_chat()
    app.show_history()
    assert app.question == "Help explain these joins" and not app.messages
    wait_until(qapp, lambda: not app.answering and not app.jobs)
    assert len(provider.requests) == 1 and len(calls) == 2
    assert (
        "Data science & SQL" in provider.requests[0].system and "join diagrams" in provider.requests[0].system
    )
    assert provider.requests[0].messages[-1].image == image
    assert app.last_routing.source == "gemini" and app.last_routing.skill.id == "data"
    cached, _ = app.history.cached_models("gemini", catalog_identity(DEFAULT_URLS["gemini"], "fake-test-key"))
    assert cached[0].id == "models/gemini-3.5-flash-lite"
    app.explain_routing()
    assert "Gemini task routing" in app.main.panel.notice_text
    dispose(app, qapp)


@pytest.mark.parametrize(
    "action", ["stop", "edit", "screen", "profile", "attachment", "preview", "pause", "settings"]
)
def test_cancel_or_edit_during_classification_ignores_late_decision(qapp, tmp_path, monkeypatch, action):
    from threading import Event
    from maya.core.prompts import SKILL_MAP
    from maya.core.routing import RoutingDecision

    app = controller(tmp_path, monkeypatch)
    app.settings.classifier_enabled = True
    app.settings.screen_enabled = True
    provider = FakeProvider()
    started, release = Event(), Event()

    def delayed(self, question, window, token):
        started.set()
        release.wait(2)  # Deliberately misbehaving worker returns after Stop to exercise stale-result guards.
        return RoutingDecision(SKILL_MAP["excel"], "gemini", "Gemini task routing", 0.9)

    monkeypatch.setattr("maya.ui.app.create_provider", lambda settings, key: provider)
    monkeypatch.setattr("maya.ui.app.TaskRouter.route", delayed)
    app.set_question("Original question")
    app.submit()
    wait_until(qapp, started.is_set)
    assert not app.history.chats()
    if action == "stop":
        app.stop()
    elif action == "edit":
        app.set_question("Changed question")
    elif action == "screen":
        app.toggle_screen()
    elif action == "profile":
        app.change_skill("python")
    elif action == "attachment":
        app.remove_attachment()
    elif action == "preview":
        app.pending_image = prepare(Image.new("RGB", (50, 50), "white"), 512, check_blank=False)
        monkeypatch.setattr(app, "review_image", lambda image: None)
        app.preview_pending()
    elif action == "pause":
        app.toggle_pause()
    else:
        app.config_changed.emit()
    assert not app.answering and not app.main.panel.stop.isEnabled()
    release.set()
    wait_until(qapp, lambda: not app.jobs)
    assert not provider.requests and not app.messages and not app.history.chats()
    assert app.question == ("Changed question" if action == "edit" else "Original question")
    dispose(app, qapp)


@pytest.mark.parametrize("mode", ["disabled", "manual", "missing-key", "failed-job"])
def test_local_or_manual_routing_still_streams_without_classifier_dependency(
    qapp, tmp_path, monkeypatch, mode
):
    app = controller(tmp_path, monkeypatch)
    provider = FakeProvider()
    routed = []

    def classify(self, question, window, token):
        routed.append(question)
        raise MayaError("Synthetic routing failure", "auth")

    monkeypatch.setattr("maya.ui.app.create_provider", lambda settings, key: provider)
    monkeypatch.setattr("maya.ui.app.TaskRouter.route", classify)
    app.settings.classifier_enabled = mode != "disabled"
    if mode == "manual":
        app.settings.skill = "python"
    elif mode == "missing-key":
        app.settings.provider = "openrouter"
        monkeypatch.setattr(
            app.secrets, "get", lambda name, endpoint: "fake-key" if name == "openrouter" else ""
        )
    app.set_question("Explain this Excel formula")
    app.submit()
    wait_until(qapp, lambda: not app.answering and not app.jobs)
    assert len(provider.requests) == 1
    assert app.last_routing.skill.id == ("python" if mode == "manual" else "excel")
    assert len(routed) == (1 if mode == "failed-job" else 0)
    dispose(app, qapp)


def test_invalid_answer_context_is_rejected_before_classification(qapp, tmp_path, monkeypatch):
    app = controller(tmp_path, monkeypatch)
    app.settings.classifier_enabled = True
    monkeypatch.setattr("maya.ui.app.create_provider", lambda settings, key: FakeProvider())
    monkeypatch.setattr(
        "maya.ui.app.TaskRouter.route",
        lambda *args: pytest.fail("Invalid answer must not trigger paid routing"),
    )
    app.set_question("x" * 200000)
    app.submit()
    assert not app.answering and not app.jobs and len(app.question) == 200000 and not app.history.chats()
    dispose(app, qapp)


def test_smart_routing_settings_preview_and_explicit_enable(qapp, tmp_path, monkeypatch):
    app = controller(tmp_path, monkeypatch)
    dialog = SettingsDialog(app.settings, app.secrets, app.history, tmp_path)
    assert not dialog.routing_enabled.isChecked()
    assert dialog.instruction_library.count() == 34
    dialog.instruction_library.setCurrentIndex(13)
    assert "authorized defensive" in dialog.instruction_preview.toPlainText()
    dialog.routing_enabled.setChecked(True)
    dialog.routing_timeout.setValue(3)
    dialog.save()
    assert dialog.result() == dialog.Accepted and dialog.settings.classifier_enabled
    assert dialog.settings.classifier_timeout == 3 and not app.settings.classifier_enabled
    dialog.deleteLater()
    dispose(app, qapp)


def test_instruction_search_selects_locally_without_saving_or_requesting(qapp, tmp_path, monkeypatch):
    """Contains matching and unrecognized search text leave approved profiles and provider consent intact."""
    app = controller(tmp_path, monkeypatch)
    dialog = SettingsDialog(app.settings, app.secrets, app.history, tmp_path)
    dialog.show()
    dialog.tabs.setCurrentIndex(2)
    picker = dialog.instruction_library
    picker.setEditText("network")
    completion = picker.completer()
    completion.setCompletionPrefix("network")
    assert completion.completionCount() == 1
    match = completion.currentCompletion()
    picker.setCurrentIndex(picker.findText(match))
    assert picker.currentData().id == "network"
    assert "read-only checks" in dialog.instruction_preview.toPlainText()
    picker.setEditText("not a task skill")
    picker.lineEdit().setFocus()
    QTest.keyClick(picker.lineEdit(), Qt.Key_Return)
    assert picker.count() == 34 and not dialog.settings.custom_profiles
    assert not app.settings.classifier_enabled and not app.jobs
    assert dialog.result() != dialog.Accepted
    dialog.reject()
    dialog.deleteLater()
    dispose(app, qapp)


# --- Setup, model choices and motion preferences retain their explicit privacy boundaries. ---
def test_typed_key_reveal_masks_on_blur_hide_timeout_and_cancel(qapp, tmp_path, monkeypatch):
    """Only explicitly entered input is revealed; transient UI changes restore the mask."""
    from PyQt5.QtWidgets import QLineEdit

    app = controller(tmp_path, monkeypatch)
    dialog = SettingsDialog(app.settings, app.secrets, app.history, tmp_path)
    dialog.show()
    dialog.activateWindow()
    qapp.processEvents()
    assert not dialog.key.text() and not dialog.show_key.isEnabled()
    dialog.key.setText("synthetic-typed-key")
    QTest.mouseClick(dialog.show_key, Qt.LeftButton)
    qapp.processEvents()
    assert dialog.key.echoMode() == QLineEdit.Normal and dialog.reveal_timer.isActive()
    dialog.provider.setFocus()
    qapp.processEvents()
    assert dialog.key.echoMode() == QLineEdit.Password and not dialog.show_key.isChecked()
    dialog.show_key.setChecked(True)
    dialog.reveal_timer.setInterval(1)
    wait_until(qapp, lambda: not dialog.reveal_timer.isActive())
    assert dialog.key.echoMode() == QLineEdit.Password
    dialog.show_key.setChecked(True)
    dialog.tabs.setCurrentIndex(1)
    qapp.processEvents()
    assert dialog.key.echoMode() == QLineEdit.Password
    dialog.reject()
    assert not dialog.key.text() and not dialog.reveal_timer.isActive() and not app.jobs
    dialog.deleteLater()
    dispose(app, qapp)


def test_endpoint_edit_clears_typed_key_and_reports_current_destination(qapp, tmp_path, monkeypatch):
    """A provider's stored credential status cannot describe an old URL after the destination changes."""
    app = controller(tmp_path, monkeypatch)
    app.settings.provider = "compatible"
    app.settings.urls["compatible"] = "https://one.example/v1"
    monkeypatch.setattr(
        app.secrets,
        "get",
        lambda provider, endpoint: "synthetic-stored-key" if endpoint == "https://one.example/v1" else "",
    )
    dialog = SettingsDialog(app.settings, app.secrets, app.history, tmp_path)
    assert "Key available" in dialog.key_state.text() and not dialog.key.text()
    dialog.key.setText("synthetic-typed-key")
    dialog.show_key.setChecked(True)
    dialog.endpoint.setText("https://two.example/v1")
    assert not dialog.key.text() and not dialog.show_key.isChecked()
    assert "Add your key" in dialog.key_state.text() and not app.jobs
    dialog.provider.setCurrentIndex(dialog.provider.findData("ollama"))
    assert not dialog.key.isEnabled() and not dialog.show_key.isEnabled()
    assert "No key needed" in dialog.key_state.text()
    dialog.reject()
    dialog.deleteLater()
    dispose(app, qapp)


def test_model_search_empty_state_and_reset_preserve_other_tab(qapp):
    """A failed search cannot use stale selection or start discovery; reset remains local to its tab."""
    models = [Model("one", "One", "openrouter", True, free=True), Model("two", "Two", "openrouter", False)]
    picker = ModelPicker(models, "one", 0)
    picker.filters[0][0].setText("two")
    picker.tabs.setCurrentIndex(1)
    picker.filters[1][0].setText("no-such-model")
    assert not picker.use_button.isEnabled() and not picker.filters[1][3].currentItem()
    assert "No matches" in picker.empty_hints[1].text()
    picker.reset_filters()
    assert picker.use_button.isEnabled() and picker.filters[1][3].count() == 1
    assert picker.filters[0][0].text() == "two" and picker.filters[0][3].count() == 1
    picker.choose()
    assert picker.chosen.id == "one"
    picker.deleteLater()
    qapp.processEvents()


def test_empty_model_catalog_allows_explicit_manual_choice(qapp):
    picker = ModelPicker([], "", 0)
    assert not picker.use_button.isEnabled() and "No catalog" in picker.empty_hints[0].text()
    picker.manual.setText("verified-local-model")
    assert picker.use_button.isEnabled()
    picker.choose()
    assert picker.chosen.id == "verified-local-model" and picker.chosen.vision is None
    picker.deleteLater()
    qapp.processEvents()


def test_image_confirmation_is_per_model_and_native_empty_state_is_actionable(qapp):
    models = [Model("one", "One", "compatible", None), Model("two", "Two", "compatible", None)]
    picker = ModelPicker(models, "one", 0)
    assert picker.unknown_vision.isEnabled()
    picker.unknown_vision.setChecked(True)
    picker.filters[0][3].setCurrentRow(1)
    assert not picker.unknown_vision.isChecked()
    picker.choose()
    assert picker.chosen.id == "two" and picker.chosen.vision is None
    picker.deleteLater()
    native = ModelPicker([], "", 0, allow_manual=False)
    assert not native.manual.isEnabled() and not native.unknown_vision.isEnabled()
    assert "Close this dialog" in native.empty_hints[0].text()
    native.deleteLater()
    qapp.processEvents()


def test_reduced_motion_stops_busy_timers_without_changing_draft_or_status(qapp, tmp_path, monkeypatch):
    app = controller(tmp_path, monkeypatch)
    app.main.show()
    app.mini.show()
    app.orb.show()
    qapp.processEvents()
    app.set_question("Keep this draft")
    app.state("streaming", "Synthetic activity")
    assert app.main.panel.mark.timer.isActive() and app.orb.timer.isActive()
    dialog = SettingsDialog(app.settings, app.secrets, app.history, tmp_path)
    dialog.reduce_motion.setChecked(True)
    dialog.save()
    app.settings = dialog.settings
    app.config_changed.emit()
    assert not app.main.panel.mark.timer.isActive() and not app.mini.panel.mark.timer.isActive()
    assert not app.orb.timer.isActive() and app.main.panel.mark.active
    assert app.question == "Keep this draft" and "Synthetic activity" in app.main.panel.status.full_text
    app.store.save(app.settings)
    assert app.store.load().reduce_motion
    app.settings.reduce_motion = False
    app.config_changed.emit()
    assert app.main.panel.mark.timer.isActive() and app.orb.timer.isActive()
    dialog.deleteLater()
    dispose(app, qapp)


def test_send_availability_tracks_text_and_screen_gated_attachment(qapp, tmp_path, monkeypatch):
    app = controller(tmp_path, monkeypatch)
    app.config_changed.emit()
    assert not app.main.panel.send.isEnabled() and not app.mini.panel.send.isEnabled()
    app.set_question("A useful question")
    assert app.main.panel.send.isEnabled() and app.mini.panel.send.isEnabled()
    app.set_question("   ")
    app.pending_image = prepare(Image.new("RGB", (30, 30), "white"), 512, check_blank=False)
    app.attachment_changed.emit()
    assert not app.main.panel.send.isEnabled()
    app.settings.screen_enabled = True
    app.config_changed.emit()
    assert app.main.panel.send.isEnabled()
    app.remove_attachment()
    assert not app.main.panel.send.isEnabled() and not app.jobs
    dispose(app, qapp)


def test_dynamic_tooltips_show_literal_markup_and_links_require_hosts(qapp, monkeypatch):
    from PyQt5.QtCore import QUrl
    from PyQt5.QtGui import QDesktopServices, QTextDocument
    from PyQt5.QtWidgets import QPushButton
    from maya.ui.text import safe_tooltip
    from maya.ui.widgets import SafeBrowser

    widget = QPushButton()
    payload = '<img src="file:///synthetic-private"> & <b>literal</b>'
    safe_tooltip(widget, payload)
    document = QTextDocument()
    document.setHtml(widget.toolTip())
    assert document.toPlainText() == payload
    assert not any(document.characterAt(index) == "\ufffc" for index in range(document.characterCount()))
    calls = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: calls.append(url.toString()))
    browser = SafeBrowser()
    for url in [
        "file:///synthetic-private",
        "https:///no-host",
        "https://user:synthetic@example.test",
        "javascript:alert(1)",
    ]:
        browser.open_link(QUrl(url))
    assert not calls
    browser.open_link(QUrl("https://example.test/help"))
    assert calls == ["https://example.test/help"]
    widget.deleteLater()
    browser.deleteLater()
    qapp.processEvents()


# --- Context review remains local until explicit stage-specific approval. ---
@pytest.mark.parametrize("routing", [False, True])
def test_context_review_cancel_reads_no_credentials_or_history_writes(qapp, tmp_path, monkeypatch, routing):
    from maya.ui.context_review import ContextReview

    app = controller(tmp_path, monkeypatch)
    app.settings.classifier_enabled = routing
    app.set_question("Explain this command <as literal text>")
    monkeypatch.setattr(app.secrets, "get", lambda *args: pytest.fail("Preview must not read keys"))
    seen = []

    def preview(dialog):
        seen.append(dialog.answer_text.toPlainText())
        assert dialog.answer_text.isReadOnly() and dialog.system_text.isReadOnly()
        app.submit()  # A second programmatic submit is ignored while review is open.
        return dialog.Rejected

    monkeypatch.setattr(ContextReview, "exec_", preview)
    app.review_context()
    assert "<as literal text>" in seen[0] and not app.messages and not app.jobs
    assert app.question == "Explain this command <as literal text>" and not app.history.chats()
    dispose(app, qapp)


def test_context_review_sends_the_exact_approved_request(qapp, tmp_path, monkeypatch):
    from maya.ui.context_review import ContextReview

    app = controller(tmp_path, monkeypatch)
    app.set_question("Explain this command")
    app.history.remember("Use concise explanations", "command")
    provider, seen = FakeProvider(), []
    monkeypatch.setattr("maya.ui.app.create_provider", lambda *args: provider)

    def preview(dialog):
        seen.append(dialog.context.request)
        assert "Use concise explanations" in dialog.answer_text.toPlainText()
        assert dialog.routing_text is None and not provider.requests
        return dialog.Accepted

    monkeypatch.setattr(ContextReview, "exec_", preview)
    app.review_context()
    wait_until(qapp, lambda: not app.answering and not app.jobs)
    assert len(seen) == len(provider.requests) == 1 and provider.requests[0] is seen[0]
    assert len(app.history.chats()) == 1 and app.messages[-1].status == "complete"
    dispose(app, qapp)


@pytest.mark.parametrize(
    "change", ["question", "model", "memory", "screen", "image", "profile", "history", "window"]
)
def test_context_change_invalidates_review_before_credential_access(qapp, tmp_path, monkeypatch, change):
    from dataclasses import replace
    from maya.ui.context_review import ContextReview

    app = controller(tmp_path, monkeypatch)
    app.set_question("Explain this command")
    monkeypatch.setattr(app.secrets, "get", lambda *args: pytest.fail("Stale approval must not read keys"))

    def preview(dialog):
        if change == "question":
            app.set_question("Changed question")
        elif change == "model":
            app.selected_model = replace(app.selected_model, id="other")
        elif change == "memory":
            app.history.remember("A new preference", "general")
        elif change == "screen":
            app.settings.screen_enabled = True
        elif change == "image":
            app.settings.screen_enabled = True
            app.pending_image = prepare(Image.new("RGB", (30, 30), "white"), 512, check_blank=False)
        elif change == "profile":
            app.settings.skill = "excel"
        elif change == "history":
            app.messages.extend([Message("user", "Earlier"), Message("assistant", "Earlier answer")])
        else:
            app.last_window = replace(app.last_window, title="Another external window")
        return dialog.Accepted

    monkeypatch.setattr(ContextReview, "exec_", preview)
    app.review_context()
    assert not app.jobs and not app.history.chats() and "changed" in app.main.panel.notice_text
    dispose(app, qapp)


@pytest.mark.parametrize("accept_answer", [False, True])
def test_gemini_review_has_separate_routing_and_final_answer_approvals(
    qapp, tmp_path, monkeypatch, accept_answer
):
    from maya.core.routing import RoutingDecision, classification_payload
    from maya.ui.context_review import ContextReview

    app = controller(tmp_path, monkeypatch)
    app.settings.classifier_enabled = True
    app.set_question("Explain this command")
    app.history.remember("Use concise command explanations", "command")
    app.history.remember("Prefer spreadsheet examples", "excel")
    provider, stages, calls = FakeProvider(), [], []
    monkeypatch.setattr("maya.ui.app.create_provider", lambda *args: provider)

    def classify(router, question, title, token):
        calls.append((question, title))
        return RoutingDecision(
            router.instructions.select("excel", question), "gemini", "Synthetic Gemini selection"
        )

    monkeypatch.setattr("maya.ui.app.TaskRouter.route", classify)

    def preview(dialog):
        stages.append(dialog.context)
        assert not provider.requests and not app.history.chats()
        if len(stages) == 1:
            assert not calls and dialog.context.skill.id == "command"
            assert (
                dialog.routing_text and "Prefer spreadsheet examples" not in dialog.routing_text.toPlainText()
            )
            assert (
                classification_payload(app.instructions, app.question, "")["question_excerpt"]
                in dialog.routing_text.toPlainText()
            )
            return dialog.Accepted
        assert dialog.context.skill.id == "excel" and dialog.routing_text is None
        assert dialog.context.memories == ("Prefer spreadsheet examples",)
        return dialog.Accepted if accept_answer else dialog.Rejected

    monkeypatch.setattr(ContextReview, "exec_", preview)
    app.review_context()
    wait_until(qapp, lambda: not app.answering and not app.jobs)
    assert len(calls) == 1 and len(stages) == 2
    if accept_answer:
        assert len(provider.requests) == 1 and provider.requests[0] is stages[-1].request
        assert "Prefer spreadsheet examples" in provider.requests[0].system
    else:
        assert not provider.requests and not app.history.chats() and app.question == "Explain this command"
    dispose(app, qapp)


def test_memory_change_during_reviewed_routing_blocks_late_answer(qapp, tmp_path, monkeypatch):
    from threading import Event
    from maya.core.routing import RoutingDecision
    from maya.ui.context_review import ContextReview

    app = controller(tmp_path, monkeypatch)
    app.settings.classifier_enabled = True
    app.set_question("Explain this command")
    provider, started, release, reviews = FakeProvider(), Event(), Event(), []
    monkeypatch.setattr("maya.ui.app.create_provider", lambda *args: provider)

    def classify(router, question, title, token):
        started.set()
        assert release.wait(2)
        return RoutingDecision(router.instructions.select("command", question), "gemini", "Synthetic route")

    monkeypatch.setattr("maya.ui.app.TaskRouter.route", classify)

    def preview(dialog):
        reviews.append(dialog.context)
        return dialog.Accepted

    monkeypatch.setattr(ContextReview, "exec_", preview)
    app.review_context()
    wait_until(qapp, started.is_set)
    app.history.remember("New memory during routing", "general")
    release.set()
    wait_until(qapp, lambda: not app.answering and not app.jobs)
    assert len(reviews) == 1 and not provider.requests and not app.history.chats()
    assert "changed during routing" in app.main.panel.notice_text and app.question
    dispose(app, qapp)


def test_review_redacts_included_history_without_overwriting_original(qapp, tmp_path, monkeypatch):
    from maya.ui.context_review import ContextReview

    app = controller(tmp_path, monkeypatch)
    original = Message("assistant", '"api_key": "synthetic private credential"')
    app.messages = [Message("user", "Earlier question"), original]
    app.set_question("Explain this command")
    provider = FakeProvider()
    monkeypatch.setattr("maya.ui.app.create_provider", lambda *args: provider)

    def preview(dialog):
        assert "synthetic private credential" not in dialog.answer_text.toPlainText()
        return dialog.Accepted

    monkeypatch.setattr(ContextReview, "exec_", preview)
    app.review_context()
    wait_until(qapp, lambda: not app.answering and not app.jobs)
    assert "synthetic private credential" in original.text
    assert "synthetic private credential" not in provider.requests[0].messages[1].text
    dispose(app, qapp)


def test_review_blocks_raw_recognizable_secrets_when_redaction_is_disabled(qapp, tmp_path, monkeypatch):
    from maya.ui.context_review import ContextReview

    app = controller(tmp_path, monkeypatch)
    app.settings.redact_text = False
    app.set_question('password="synthetic private value"')
    monkeypatch.setattr(app.secrets, "get", lambda *args: pytest.fail("No key access before review"))
    monkeypatch.setattr(
        ContextReview, "exec_", lambda *args: pytest.fail("Do not display recognizable credentials")
    )
    app.review_context()
    assert "Recognizable credentials remain" in app.main.panel.notice_text and not app.jobs
    dispose(app, qapp)


def test_context_screenshot_tab_respects_screen_off_and_keeps_approved_bytes(qapp, tmp_path, monkeypatch):
    from maya.ui.context_review import ContextReview

    app = controller(tmp_path, monkeypatch)
    app.pending_image = prepare(Image.new("RGB", (40, 40), "white"), 512, check_blank=False)
    app.set_question("Explain this image")
    contexts = []

    def preview(dialog):
        contexts.append(dialog.context)
        titles = [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())]
        assert ("Screenshot" in titles) == app.settings.screen_enabled
        return dialog.Rejected

    monkeypatch.setattr(ContextReview, "exec_", preview)
    app.review_context()
    app.settings.screen_enabled = True
    app.review_context()
    assert contexts[0].request.messages[-1].image is None
    assert contexts[1].request.messages[-1].image is app.pending_image and not app.jobs
    dispose(app, qapp)


@pytest.mark.parametrize("change", ["question", "memory", "model", "paused"])
def test_final_gemini_context_change_prevents_answer_submission(qapp, tmp_path, monkeypatch, change):
    from dataclasses import replace
    from maya.core.routing import RoutingDecision
    from maya.ui.context_review import ContextReview

    app = controller(tmp_path, monkeypatch)
    app.settings.classifier_enabled = True
    app.set_question("Explain this command")
    provider, reviews = FakeProvider(), []
    monkeypatch.setattr("maya.ui.app.create_provider", lambda *args: provider)
    monkeypatch.setattr(
        "maya.ui.app.TaskRouter.route",
        lambda router, question, title, token: RoutingDecision(
            router.instructions.select("excel", question), "gemini", "Synthetic selection"
        ),
    )

    def preview(dialog):
        reviews.append(dialog.context)
        if len(reviews) == 2:
            if change == "question":
                app.set_question("Updated question")
            elif change == "memory":
                app.history.remember("New spreadsheet preference", "excel")
            elif change == "model":
                app.selected_model = replace(app.selected_model, id="other")
            else:
                app.paused = True
        return dialog.Accepted

    monkeypatch.setattr(ContextReview, "exec_", preview)
    app.review_context()
    wait_until(qapp, lambda: not app.answering and not app.jobs)
    assert len(reviews) == 2 and not provider.requests and not app.history.chats()
    assert "changed" in app.main.panel.notice_text and app.question
    dispose(app, qapp)


def test_context_reading_enter_cannot_approve_a_request(qapp, tmp_path, monkeypatch):
    from maya.ui.context_review import ContextReview

    app = controller(tmp_path, monkeypatch)
    app.set_question("A readable question")
    context = app.prepared_context()
    dialog = ContextReview(context, app.settings.urls["gemini"], "gemini")
    dialog.show()
    dialog.activateWindow()
    dialog.answer_text.setFocus()
    qapp.processEvents()
    QTest.keyClick(dialog.answer_text, Qt.Key_Return)
    assert dialog.isVisible() and dialog.result() != dialog.Accepted
    dialog.proceed.setFocus()
    QTest.keyClick(dialog.proceed, Qt.Key_Return)
    assert dialog.result() == dialog.Accepted
    dialog.deleteLater()
    dispose(app, qapp)


# --- Live clipboard behavior is tested against synthetic notifications, never the user's clipboard. ---
def clipboard_fixture():
    from PyQt5.QtCore import QObject, QMimeData, pyqtSignal

    class FakeClipboard(QObject):
        dataChanged = pyqtSignal()

        def __init__(self):
            super().__init__()
            self.mime = QMimeData()
            self.reads = 0

        def mimeData(self):
            self.reads += 1
            return self.mime

        def copy(self, text):
            self.mime = QMimeData()
            if text is not None:
                self.mime.setText(text)
            self.dataChanged.emit()

    return FakeClipboard()


def test_clipboard_opt_in_debounce_redact_plain_text_and_explicit_draft(qapp, tmp_path, monkeypatch):
    app = controller(tmp_path, monkeypatch)
    clip = clipboard_fixture()
    window = app.clipboard_window
    window.clipboard = clip
    app.show_clipboard()
    clip.copy("private clipboard while OFF")
    QTest.qWait(100)
    qapp.processEvents()
    assert clip.reads == 0 and not window.viewer.toPlainText()
    window.watch.setChecked(True)
    for index in range(20):
        clip.copy(f"<img src=file:///example> item {index} password=test-secret")
    wait_until(qapp, lambda: clip.reads == 1)
    text = window.viewer.toPlainText()
    assert "item 19" in text and "test-secret" not in text and "[REDACTED SECRET]" in text
    assert "<img" in text and not app.question and not app.history.chats() and not app.jobs
    window.use_in_chat()
    assert (
        app.question == text
        and not window.isVisible()
        and not window.connected
        and not window.watch.isChecked()
    )
    assert not app.messages and not app.history.chats()
    dispose(app, qapp)


def test_clipboard_repeat_empty_large_and_hide_disable_subscription(qapp, tmp_path, monkeypatch):
    app = controller(tmp_path, monkeypatch)
    clip = clipboard_fixture()
    window = app.clipboard_window
    window.clipboard = clip
    app.show_clipboard()
    window.watch.setChecked(True)
    clip.copy("line\n" * 22000)
    wait_until(qapp, lambda: len(window.viewer.toPlainText()) == 100000)
    assert "shortened" in window.state.text()
    bar = window.viewer.verticalScrollBar()
    app.scroll_answer(120)
    position = bar.value()
    assert position > 0
    QTest.keyClick(window.viewer, Qt.Key_End)
    assert bar.value() == bar.maximum()
    QTest.keyClick(window.viewer, Qt.Key_Home)
    assert bar.value() == 0
    QTest.keyClick(window.viewer, Qt.Key_PageDown)
    assert bar.value() > 0
    position = bar.value()
    clip.copy("line\n" * 22000)
    QTest.qWait(100)
    qapp.processEvents()
    assert bar.value() == position
    clip.copy(None)
    wait_until(qapp, lambda: not window.viewer.toPlainText())
    assert not window.use_button.isEnabled()
    clip.copy("temporary text")
    wait_until(qapp, lambda: window.use_button.isEnabled())
    window.hide()
    reads = clip.reads
    clip.copy("text copied while hidden")
    QTest.qWait(100)
    qapp.processEvents()
    assert clip.reads == reads and not window.viewer.toPlainText() and not window.connected
    app.show_clipboard()
    assert not window.watch.isChecked()
    dispose(app, qapp)


def test_quit_during_classification_cancels_worker_without_starting_answer(qapp, tmp_path, monkeypatch):
    from threading import Event

    app = controller(tmp_path, monkeypatch)
    app.settings.classifier_enabled = True
    provider, started = FakeProvider(), Event()

    def classify(self, question, window, token):
        started.set()
        while True:
            token.wait(0.01)

    exits = []
    monkeypatch.setattr(qapp, "quit", lambda: exits.append(True))
    monkeypatch.setattr("maya.ui.app.create_provider", lambda settings, key: provider)
    monkeypatch.setattr("maya.ui.app.TaskRouter.route", classify)
    app.set_question("Question to keep")
    app.submit()
    wait_until(qapp, started.is_set)
    app.quit()
    wait_until(qapp, lambda: not app.jobs)
    assert app.quitting and exits and not provider.requests and not app.history.chats()
    assert app.question == "Question to keep"
    dispose(app, qapp)


def test_clipboard_pause_and_legacy_visibility_shortcut_clear_local_preview(qapp, tmp_path, monkeypatch):
    app = controller(tmp_path, monkeypatch)
    window = app.clipboard_window
    window.clipboard = clipboard_fixture()
    app.show_clipboard()
    window.watch.setChecked(True)
    window.clipboard.copy("test clipboard")
    wait_until(qapp, lambda: window.viewer.toPlainText() == "test clipboard")
    app.toggle_pause()
    assert not window.connected and not window.viewer.toPlainText()
    window.watch.setChecked(True)
    assert not window.connected and not window.watch.isChecked()
    app.toggle_pause()
    window.watch.setChecked(True)
    window.clipboard.copy("test again")
    wait_until(qapp, lambda: window.viewer.toPlainText() == "test again")
    app.toggle_visible()
    assert not window.isVisible() and not window.connected
    app.toggle_visible()
    assert window.isVisible() and not window.watch.isChecked()
    dispose(app, qapp)


# --- Test providers emit real incremental events on real QThreads, without internet requests. ---
class FakeSecrets:
    """In-memory test credential boundary prevents any test from reading the user's saved cloud keys."""

    def get(self, provider, endpoint):
        """Return only a synthetic test key."""
        return "fake-test-key"


class FakeProvider:
    """Deterministic provider with slow chunks so responsiveness and cancellation can be asserted."""

    def __init__(self, count=5):
        """Choose the number of visible text chunks; no actual API is used."""
        self.count = count
        self.requests = []

    def stream(self, request, token):
        """Record the outbound request and yield until finished or cancelled."""
        self.requests.append(request)
        for index in range(self.count):
            token.wait(0.02)
            yield StreamEvent("text", f"chunk {index} ")
        yield StreamEvent("finish", "complete")


def wait_until(qapp, predicate, seconds=4):
    """Pump the actual Qt event loop with a bounded test timeout."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    raise AssertionError("Qt state transition did not finish within the test deadline")


def controller(tmp_path, monkeypatch):
    """Construct an isolated app without native shortcuts, secure-store access, or cloud requests."""
    store = ConfigStore(tmp_path)
    app = AppController(store, Settings(), HistoryStore(tmp_path / "test.db"), FakeSecrets())
    monkeypatch.setattr(app.desktop, "exclude_capture", lambda handle: False)
    app.selected_model = Model("test", "Test model", "gemini", True, 30000, 4096)
    return app


def dispose(app, qapp):
    """Stop timers and destroy all test windows after workers finish."""
    app.window_timer.stop()
    app.flush_timer.stop()
    app.desktop.unregister_hotkeys()
    for widget in (app.main, app.mini, app.orb, app.clipboard_window):
        widget.hide()
        widget.deleteLater()
    qapp.removeNativeEventFilter(app.hotkeys)
    app.deleteLater()
    qapp.processEvents()


# --- The sculpted, smaller overlay must retain real behavior, not just pass a visual snapshot. ---
@pytest.mark.parametrize(
    "provider,available,selected,destination",
    [
        ("gemini", False, False, "settings"),
        ("openrouter", False, False, "settings"),
        ("anthropic", False, False, "settings"),
        ("compatible", False, False, "picker"),
        ("ollama", False, False, "picker"),
        ("gemini", True, False, "picker"),
        ("gemini", False, True, "picker"),
    ],
)
def test_first_run_model_action_preserves_manual_paths_and_draft(
    qapp, tmp_path, monkeypatch, provider, available, selected, destination
):
    """Setup guides empty cloud catalogs while cached/manual/local models remain selectable."""
    app = controller(tmp_path, monkeypatch)
    model = app.selected_model
    app.settings.provider = provider
    app.models = [model] if available else []
    app.selected_model = model if selected else None
    calls = []
    monkeypatch.setattr(app, "open_settings", lambda: calls.append("settings"))
    monkeypatch.setattr(app, "pick_model", lambda: calls.append("picker"))
    app.set_question("Keep this draft through setup")
    app.config_changed.emit()
    app.main.show()
    qapp.processEvents()
    QTest.mouseClick(app.main.panel.model, Qt.LeftButton)
    assert calls == [destination]
    assert app.question == app.mini.panel.composer.toPlainText() == "Keep this draft through setup"
    assert app.main.panel.send.isEnabled() == selected
    assert not app.jobs and not app.messages and not app.settings.screen_enabled
    dispose(app, qapp)


def test_composer_focus_multiline_and_paused_actions(qapp, tmp_path, monkeypatch):
    """Keyboard drafting stays native and private; a paused app offers neither Send nor Capture."""
    app = controller(tmp_path, monkeypatch)
    app.main.show()
    app.main.activateWindow()
    qapp.processEvents()
    panel = app.main.panel
    panel.composer.setFocus()
    qapp.processEvents()
    assert panel.compose_well.property("focused")
    QTest.keyClicks(panel.composer, "First line")
    QTest.keyClick(panel.composer, Qt.Key_Return, Qt.ShiftModifier)
    QTest.keyClicks(panel.composer, "Second line")
    assert app.question == "First line\nSecond line" and not app.jobs
    panel.more.setFocus()
    qapp.processEvents()
    assert not panel.compose_well.property("focused")
    app.settings.screen_enabled = True
    app.paused = True
    app.config_changed.emit()
    assert not panel.send.isEnabled() and not panel.capture.isEnabled()
    assert app.question == app.mini.panel.composer.toPlainText()
    dispose(app, qapp)


@pytest.mark.parametrize("surface", ["main", "mini"])
def test_screen_drawer_and_long_status_preserve_minimum_layout(qapp, tmp_path, monkeypatch, surface):
    """Both compact surfaces disclose screen controls without consent or growing on long notices."""
    app = controller(tmp_path, monkeypatch)
    window = getattr(app, surface)
    size = (400, 450) if surface == "main" else (320, 360)
    window.resize(*size)
    window.show()
    qapp.processEvents()
    panel = window.panel
    assert not panel.capture_controls.isVisible()
    QTest.mouseClick(panel.context_toggle, Qt.LeftButton)
    text = "Synthetic status with a complete explanation <plain text> " * 20
    app.state("idle", text)
    app.notice(text)
    qapp.processEvents()
    assert panel.capture_controls.isVisible() and not app.settings.screen_enabled and not app.jobs
    assert (window.width(), window.height()) == size
    assert "…" in panel.status.text()
    from PyQt5.QtGui import QTextDocument

    document = QTextDocument()
    document.setHtml(panel.status.toolTip())
    assert text.strip() in document.toPlainText() and text in panel.status.accessibleDescription()
    for control in (panel.compose_well, panel.composer, panel.send, panel.notice, panel.status):
        assert panel.rect().contains(control.mapTo(panel, control.rect().topLeft()))
        assert panel.rect().contains(control.mapTo(panel, control.rect().bottomRight()))
    dispose(app, qapp)


def test_floating_round_corners_keep_header_opaque(qapp, tmp_path, monkeypatch):
    """Transparent corners reveal the desktop; the header itself must retain readable paper backing."""
    app = controller(tmp_path, monkeypatch)
    app.mini.show()
    qapp.processEvents()
    image = app.mini.grab().toImage()
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(150, 12).alpha() == 255
    assert image.pixelColor(150, 12).name() == "#f8f6ef"
    assert not app.main.panel.mark.timer.isActive() and not app.mini.panel.mark.timer.isActive()
    dispose(app, qapp)


def test_pin_persists_topmost_and_preserves_shared_draft(qapp, tmp_path, monkeypatch):
    """Toggling native window flags preserves visibility, geometry, text, and future startup preference."""
    app = controller(tmp_path, monkeypatch)
    app.main.show()
    app.set_question("Keep my question while pinning")
    qapp.processEvents()
    bounds = app.main.geometry()
    assert app.main.windowFlags() & Qt.WindowStaysOnTopHint
    assert app.main.panel.pin.isChecked()
    QTest.mouseClick(app.main.panel.pin, Qt.LeftButton)
    qapp.processEvents()
    assert not (app.main.windowFlags() & Qt.WindowStaysOnTopHint)
    assert app.main.isVisible() and app.main.geometry() == bounds
    assert app.store.load().pin_main is False
    assert app.question == app.mini.panel.composer.toPlainText() == "Keep my question while pinning"
    QTest.mouseClick(app.main.panel.pin, Qt.LeftButton)
    qapp.processEvents()
    assert app.main.windowFlags() & Qt.WindowStaysOnTopHint and app.store.load().pin_main
    app.main.hide()
    app.toggle_pin()
    assert not app.main.isVisible(), "Changing pin on a hidden window must not reveal it"
    assert app.mini.windowFlags() & Qt.WindowStaysOnTopHint
    assert app.orb.windowFlags() & Qt.WindowDoesNotAcceptFocus
    assert app.clipboard_window.windowFlags() & Qt.WindowStaysOnTopHint
    dispose(app, qapp)


def test_compact_capture_drawer_is_inspection_only_and_controls_fit(qapp, tmp_path, monkeypatch):
    """Opening the reduced chrome does not capture/transmit or enable screen access implicitly."""
    app = controller(tmp_path, monkeypatch)
    app.mini.resize(320, 360)
    app.mini.show()
    qapp.processEvents()
    panel = app.mini.panel
    assert not panel.capture_controls.isVisible() and not app.settings.screen_enabled
    QTest.mouseClick(panel.context_toggle, Qt.LeftButton)
    qapp.processEvents()
    assert panel.capture_controls.isVisible() and not app.settings.screen_enabled and not app.jobs
    assert not panel.capture.isEnabled()
    QTest.mouseClick(panel.screen, Qt.LeftButton)
    qapp.processEvents()
    assert app.settings.screen_enabled and panel.context_toggle.text() == "Screen ON" and not app.jobs
    for control in (panel.screen, panel.scope, panel.capture):
        assert panel.capture_controls.rect().contains(control.geometry())
    # Long, visible errors and a screenshot must not force controls past the floating window edges.
    app.pending_image = prepare(Image.new("RGB", (50, 50), "white"), 512, check_blank=False)
    app.attachment_changed.emit()
    app.notice(
        "The provider rejected this request. Review model capabilities and try a smaller screenshot or shorter question."
    )
    qapp.processEvents()
    assert app.mini.width() == 320 and app.mini.height() == 360
    assert panel.rect().contains(panel.send.geometry()) and panel.rect().contains(panel.attachment.geometry())
    assert panel.notice.toolTip() == panel.notice_text
    QTest.mouseClick(panel.context_toggle, Qt.LeftButton)
    assert not panel.capture_controls.isVisible() and app.settings.screen_enabled
    dispose(app, qapp)


@pytest.mark.parametrize("surface", ["main", "mini"])
def test_compact_notice_details_are_complete_plain_text_without_requests(
    qapp, tmp_path, monkeypatch, surface
):
    """A small notice never clips its actionable detail or interprets HTML-like error text."""
    from PyQt5.QtWidgets import QMessageBox

    app = controller(tmp_path, monkeypatch)
    window = getattr(app, surface)
    window.show()
    text = "Review <b>model</b> capabilities & try a smaller screenshot. " * 10
    app.notice(text)
    dialogs = []
    monkeypatch.setattr(
        QMessageBox, "exec_", lambda dialog: dialogs.append((dialog.text(), dialog.textFormat()))
    )
    QTest.mouseClick(window.panel.notice, Qt.LeftButton)
    assert dialogs == [(text, Qt.PlainText)]
    from PyQt5.QtGui import QTextDocument

    document = QTextDocument()
    document.setHtml(window.panel.notice.toolTip())
    assert document.toPlainText().strip() == text.strip() and not app.jobs
    app.notice("")
    assert not window.panel.notice.isVisible()
    dispose(app, qapp)


def test_sculpted_icons_and_visible_only_active_animation(qapp, tmp_path, monkeypatch):
    """All icon scales render; animations stop hidden/idle and resume for an active visible surface."""
    from maya.ui.branding import maya_icon

    app = controller(tmp_path, monkeypatch)
    icon = maya_icon()
    assert {16, 24, 32, 48, 64, 128, 256} <= {size.width() for size in icon.availableSizes()}
    image = icon.pixmap(128, 128).toImage()
    assert image.pixelColor(0, 0).alpha() == 0 and image.pixelColor(64, 64).alpha() > 200
    app.state("thinking", "Choosing a skill")
    assert not app.main.panel.mark.timer.isActive() and not app.orb.timer.isActive()
    app.main.show()
    qapp.processEvents()
    mark = app.main.panel.mark
    assert mark.timer.isActive() and not app.mini.panel.mark.timer.isActive()
    phase = mark.phase
    QTest.qWait(120)
    qapp.processEvents()
    assert mark.phase != phase
    app.main.hide()
    assert not mark.timer.isActive()
    app.orb.show()
    qapp.processEvents()
    assert app.orb.timer.isActive()
    app.orb.hide()
    assert not app.orb.timer.isActive()
    app.main.show()
    app.state("idle", "Ready")
    assert not mark.timer.isActive()
    dispose(app, qapp)


def test_welcome_prompt_chips_only_prefill_shared_draft(qapp, tmp_path, monkeypatch):
    """Friendly first-run buttons can guide a question without hidden capture or AI calls."""
    from PyQt5.QtWidgets import QPushButton

    app = controller(tmp_path, monkeypatch)
    app.main.show()
    qapp.processEvents()
    chip = next(
        widget
        for widget in app.main.panel.view.empty.findChildren(QPushButton)
        if widget.text() == "A formula"
    )
    QTest.mouseClick(chip, Qt.LeftButton)
    assert "Excel formula" in app.question and app.mini.panel.composer.toPlainText() == app.question
    assert not app.messages and not app.jobs and not app.settings.screen_enabled
    dispose(app, qapp)


def test_overlay_preferences_saved_and_previous_default_migrates(qapp, tmp_path, monkeypatch):
    """Opacity and pin settings round-trip; only the old default dimensions adopt the new compact size."""
    app = controller(tmp_path, monkeypatch)
    dialog = SettingsDialog(app.settings, app.secrets, app.history, tmp_path)
    dialog.pin_main.setChecked(False)
    dialog.overlay_opacity.setValue(0.8)
    dialog.save()
    assert dialog.result() == dialog.Accepted
    app.settings = dialog.settings
    app.config_changed.emit()
    assert not (app.main.windowFlags() & Qt.WindowStaysOnTopHint)
    assert abs(app.mini.windowOpacity() - 0.8) < 0.01
    app.store.save(app.settings)
    assert app.store.load().overlay_opacity == 0.8
    screen = qapp.primaryScreen().availableGeometry()
    app.settings.window_geometry = [screen.left(), screen.top(), 560, 620]
    app.restore_geometry()
    assert app.main.width() == 480
    app.settings.window_geometry = [screen.left(), screen.top(), 510, 530]
    app.restore_geometry()
    assert app.main.width() == 510 and app.main.height() == min(530, screen.height() - 45)
    dialog.deleteLater()
    dispose(app, qapp)


def test_floating_title_drag_moves_window_and_keeps_draft(qapp, tmp_path, monkeypatch):
    """A real mouse gesture on the mark moves the frameless panel without editing or submitting input."""
    from PyQt5.QtCore import QPoint

    app = controller(tmp_path, monkeypatch)
    app.set_question("Draft before dragging")
    app.mini.move(100, 100)
    app.mini.show()
    qapp.processEvents()
    start = app.mini.pos()
    mark = app.mini.panel.mark
    QTest.mousePress(mark, Qt.LeftButton, pos=QPoint(12, 12))
    assert app.mini.drag_anchor is not None
    QTest.mouseMove(mark, QPoint(42, 32))
    qapp.processEvents()
    QTest.mouseRelease(mark, Qt.LeftButton, pos=QPoint(42, 32))
    assert app.mini.pos() != start and app.mini.drag_anchor is None
    assert app.question == "Draft before dragging" and not app.jobs
    dispose(app, qapp)


def test_floating_drag_clamps_negative_monitor_and_hide_ends_gesture(qapp, tmp_path, monkeypatch):
    """A monitor left of the primary keeps every edge reachable; a hidden panel cannot keep dragging."""
    from PyQt5.QtCore import QPoint, QRect
    from PyQt5.QtWidgets import QApplication

    app = controller(tmp_path, monkeypatch)
    app.mini.show()
    qapp.processEvents()
    bounds = QRect(-1280, -200, 1280, 720)

    class Monitor:
        def availableGeometry(self):
            return bounds

    monkeypatch.setattr(QApplication, "screenAt", lambda point: Monitor())
    app.mini.drag_anchor = QPoint(18, 14)
    app.mini.move_to_pointer(QPoint(-2000, -800))
    assert app.mini.pos() == bounds.topLeft()
    app.mini.move_to_pointer(QPoint(6000, 6000))
    assert app.mini.x() == bounds.right() - app.mini.width() + 1
    assert app.mini.y() == bounds.bottom() - app.mini.height() + 1
    app.mini.hide()
    assert app.mini.drag_anchor is None and not app.jobs
    dispose(app, qapp)


def test_chat_stream_shared_draft_repeated_send_and_memory(qapp, tmp_path, monkeypatch):
    """One streamed turn updates both views, includes approved memory, and ignores accidental double-send."""
    app = controller(tmp_path, monkeypatch)
    provider = FakeProvider()
    monkeypatch.setattr("maya.ui.app.create_provider", lambda settings, key: provider)
    app.history.remember("I prefer short Python examples")
    app.set_question("Explain this command")
    assert app.main.panel.composer.toPlainText() == app.mini.panel.composer.toPlainText()
    app.submit()
    app.submit()
    wait_until(qapp, lambda: app.generation is None and not app.jobs)
    assert len(app.messages) == 2 and len(provider.requests) == 1
    assert app.messages[-1].status == "complete"
    assert "chunk 4" in app.messages[-1].text
    assert "short Python" in provider.requests[0].system
    assert len(app.main.panel.view.cards) == len(app.mini.panel.view.cards) == 2
    assert app.history.messages(app.chat_id)[-1].text == app.messages[-1].text
    assert not app.main.panel.send.isEnabled(), "A finished turn leaves an empty draft"
    app.regenerate()
    wait_until(qapp, lambda: app.generation is None and not app.jobs)
    assert len(app.messages) == len(app.history.messages(app.chat_id)) == 2
    dispose(app, qapp)


def test_stop_preserves_partial_and_screen_off_strips_image(qapp, tmp_path, monkeypatch):
    """Stop preserves partial text and OFF clears screenshot reuse before another request."""
    app = controller(tmp_path, monkeypatch)
    provider = FakeProvider(100)
    monkeypatch.setattr("maya.ui.app.create_provider", lambda settings, key: provider)
    image = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(image).rectangle((0, 0, 40, 50), fill="black")
    attachment = prepare(image)
    app.pending_image = app.reuse_image = attachment
    app.set_question("Explain this command")
    # Even if a stale pending image exists, screen OFF makes the serialized request text-only.
    app.submit()
    wait_until(qapp, lambda: bool(app.messages[-1].text))
    app.stop()
    wait_until(qapp, lambda: app.generation is None and not app.jobs)
    assert app.messages[-1].status == "stopped" and app.messages[-1].text
    assert provider.requests[0].messages[-1].image is None
    app.settings.screen_enabled = True
    app.pending_image = app.reuse_image = app.last_image = attachment
    app.toggle_screen()
    assert app.pending_image is app.reuse_image is app.last_image is None
    dispose(app, qapp)


def test_secret_redaction_requires_review_and_empty_input(qapp, tmp_path, monkeypatch):
    """A redacted draft needs a second user Send; empty questions never create history records."""
    app = controller(tmp_path, monkeypatch)
    app.submit()
    assert not app.messages and app.chat_id is None
    app.set_question("Here is password=secret123")
    app.submit()
    assert "secret123" not in app.question and not app.messages
    dispose(app, qapp)


def test_model_picker_free_search_large_catalog(qapp):
    """The all/free filters have separate searches and handle hundreds of entries."""
    models = [
        Model(
            f"model-{index}",
            f"Model {index:03}",
            "openrouter",
            index % 3 == 0,
            10000 + index,
            free=index % 2 == 0,
        )
        for index in range(400)
    ]
    picker = ModelPicker(models, "model-6", time.time())
    assert picker.filters[0][3].count() == 400
    assert picker.filters[1][3].count() == 200
    picker.filters[1][0].setText("model-6")
    assert picker.filters[1][3].count() < 200
    assert picker.filters[0][3].count() == 400
    picker.filters[1][1].setChecked(True)
    assert all(
        picker.filters[1][3].item(index).data(Qt.UserRole).vision
        for index in range(picker.filters[1][3].count())
    )
    picker.deleteLater()


def test_worker_does_not_retry_after_partial(qapp):
    """A partial failed response never triggers an automatic duplicate paid request."""

    class Broken:
        """Synthetic one-chunk failure used to assert retry policy boundaries."""

        calls = 0

        def stream(self, request, token):
            """Yield one chunk then report a transient failure."""
            self.calls += 1
            yield StreamEvent("text", "partial")
            raise MayaError("Interrupted", "network")

    provider = Broken()
    worker = Generation(provider, None, 2, 30)
    results = []
    worker.ended.connect(lambda *values: results.append(values))
    worker.start()
    wait_until(qapp, lambda: results and not worker.isRunning())
    assert provider.calls == 1 and results[0][0] == "error"
    worker.deleteLater()


def test_settings_about_attribution_and_key_mask(qapp, tmp_path):
    """About describes a neutral product and provider keys remain empty and password-masked."""
    from PyQt5.QtWidgets import QLineEdit, QLabel

    dialog = SettingsDialog(Settings(), FakeSecrets(), HistoryStore(tmp_path / "test.db"), tmp_path)
    assert dialog.key.echoMode() == QLineEdit.Password and not dialog.key.text()
    text = " ".join(widget.text() for widget in dialog.findChildren(QLabel))
    assert "Maya the Helper" in text and "empty profile and no saved memories" in text
    dialog.deleteLater()


def test_settings_button_opens_real_modal(qapp, tmp_path, monkeypatch):
    """Click the actual Settings button and inspect its modal event loop instead of constructing tabs only."""
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication, QPushButton

    app = controller(tmp_path, monkeypatch)
    app.main.show()
    qapp.processEvents()
    found = []

    def inspect_and_close():
        """Observe the opened settings dialog then close it without changing privacy or credentials."""
        dialog = QApplication.activeModalWidget()
        found.append(isinstance(dialog, SettingsDialog))
        if dialog:
            dialog.reject()

    target = next(
        widget
        for widget in app.main.findChildren(QPushButton)
        if widget.accessibleName() == "Settings" and widget.isVisible()
    )
    QTimer.singleShot(100, inspect_and_close)
    QTest.mouseClick(target, Qt.LeftButton)
    assert found == [True]
    dispose(app, qapp)


def test_orb_click_panel_and_redaction_mapping(qapp, tmp_path, monkeypatch):
    """Real widget clicks expand/collapse the orb; drawn black boxes alter source pixels."""
    from maya.ui.capture_ui import RedactionCanvas

    app = controller(tmp_path, monkeypatch)
    app.show_overlay()
    qapp.processEvents()
    QTest.mouseClick(app.orb, Qt.LeftButton)
    qapp.processEvents()
    assert app.mini.isVisible()
    assert app.mini.geometry().center().x() >= 0
    QTest.mouseClick(app.orb, Qt.LeftButton)
    assert not app.mini.isVisible()
    image = Image.new("RGB", (400, 200), "white")
    canvas = RedactionCanvas(image, True)
    canvas.resize(400, 240)
    canvas.show()
    qapp.processEvents()
    from PyQt5.QtCore import QPoint

    QTest.mousePress(canvas, Qt.LeftButton, pos=QPoint(40, 60))
    QTest.mouseMove(canvas, QPoint(100, 100))
    QTest.mouseRelease(canvas, Qt.LeftButton, pos=QPoint(100, 100))
    assert canvas.image.getpixel((60, 60)) == (0, 0, 0)
    assert image.getpixel((60, 60)) == (255, 255, 255)
    canvas.hide()
    canvas.deleteLater()
    dispose(app, qapp)


def test_compact_dimensions_navigation_and_long_profile(qapp, tmp_path, monkeypatch):
    """Normal and floating surfaces fit their advertised widths with visible, clickable controls."""
    app = controller(tmp_path, monkeypatch)
    app.main.show()
    app.mini.show()
    qapp.processEvents()
    assert app.main.width() == 480
    assert app.main.height() == min(560, qapp.primaryScreen().availableGeometry().height() - 45)
    assert not app.main.sidebar.isVisible()
    assert app.mini.width() == 360 and app.mini.height() == 440
    for panel in (app.main.panel, app.mini.panel):
        assert panel.rect().contains(panel.send.geometry())
        assert panel.rect().contains(panel.model.geometry())
    QTest.mouseClick(app.main.panel.navigation, Qt.LeftButton)
    qapp.processEvents()
    assert app.main.sidebar.isVisible() and app.main.width() == 656
    QTest.mouseClick(app.main.panel.navigation, Qt.LeftButton)
    qapp.processEvents()
    assert not app.main.sidebar.isVisible() and app.main.width() == 480
    app.settings.custom_profiles = {
        "custom:123456abcdef": {"name": "A" * 80, "instruction": "Explain carefully"}
    }
    app.instructions.custom_profiles = app.settings.custom_profiles
    app.settings.skill = "custom:123456abcdef"
    app.config_changed.emit()
    qapp.processEvents()
    assert app.main.width() == 480 and app.mini.width() == 360
    assert app.main.panel.skill.currentData() == app.mini.panel.skill.currentData() == app.settings.skill
    dispose(app, qapp)


def test_settings_edit_memory_and_stage_custom_profiles(qapp, tmp_path, monkeypatch):
    """The actual editor updates a selected memory and keeps cancelled profile changes out of original settings."""
    history = HistoryStore(tmp_path / "test.db")
    history.remember("Short answers", "general")
    original = Settings()
    dialog = SettingsDialog(original, FakeSecrets(), history, tmp_path)
    dialog.memory_list.setCurrentRow(0)
    identifier = history.memories()[0]["id"]
    assert dialog.memory_text.text() == "Short answers"
    dialog.memory_text.setText("Explain with Python examples")
    dialog.scope.setCurrentIndex(dialog.scope.findData("python"))
    dialog.edit_memory()
    saved = history.memories()[0]
    assert saved["id"] == identifier and saved["text"] == "Explain with Python examples"
    assert saved["scope"] == "python"
    dialog.profile_name.setText("Exam revision")
    dialog.profile_instruction.setPlainText("Give one practice question")
    assert dialog.save_profile()
    custom_id = next(iter(dialog.settings.custom_profiles))
    assert dialog.scope.findData(custom_id) >= 0
    assert not original.custom_profiles
    dialog.reject()
    assert not original.custom_profiles
    dialog.deleteLater()


def test_main_settings_save_includes_typed_profile(qapp, tmp_path):
    """Typing a valid profile then pressing the main Save preserves it without a second intermediate save."""
    dialog = SettingsDialog(Settings(), FakeSecrets(), HistoryStore(tmp_path / "test.db"), tmp_path)
    dialog.profile_name.setText("My writing")
    dialog.profile_instruction.setPlainText("Preserve my meaning; explain corrections.")
    dialog.save()
    assert dialog.result() == dialog.Accepted
    assert len(dialog.settings.custom_profiles) == 1
    dialog.deleteLater()


def test_history_dialog_search_empty_open_rename_and_delete(qapp, tmp_path, monkeypatch):
    """Debounced search finds message text; empty states disable actions and selected edits affect one chat."""
    from PyQt5.QtWidgets import QInputDialog, QMessageBox

    history = HistoryStore(tmp_path / "test.db")
    first = history.create_chat("Excel question")
    history.add_message(first, Message("assistant", "VLOOKUP failure"))
    history.create_chat("Python question")
    dialog = HistoryDialog(history)
    dialog.search.setText("VLOOKUP")
    wait_until(qapp, lambda: dialog.listing.count() == 1)
    assert dialog.listing.currentItem().data(Qt.UserRole) == first
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Formula fix", True))
    dialog.rename()
    assert history.chats("Formula fix")[0]["id"] == first
    dialog.open_selected()
    assert dialog.result() == dialog.Accepted and dialog.chosen == first
    dialog.search.setText("No result here")
    wait_until(qapp, lambda: dialog.listing.count() == 0)
    assert not dialog.open_button.isEnabled() and "No matching" in dialog.summary.text()
    dialog.search.clear()
    dialog.reload(first)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    deleted = []
    dialog.chat_deleted.connect(deleted.append)
    dialog.delete()
    assert deleted == [first] and len(history.chats()) == 1
    dialog.deleteLater()


def test_screen_on_image_request_and_history_excludes_bytes(qapp, tmp_path, monkeypatch):
    """An explicitly attached image reaches a vision request once; SQLite keeps only its presence marker."""
    app = controller(tmp_path, monkeypatch)
    provider = FakeProvider(1)
    monkeypatch.setattr("maya.ui.app.create_provider", lambda settings, key: provider)
    image = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(image).rectangle((0, 0, 40, 50), fill="black")
    app.settings.screen_enabled = True
    app.pending_image = prepare(image)
    app.submit()  # An approved screenshot alone gets a useful default question.
    wait_until(qapp, lambda: app.generation is None and not app.jobs)
    request = provider.requests[0]
    assert request.messages[-1].image == app.pending_image
    assert request.messages[-1].text
    with app.history.connection() as db:
        assert db.execute("SELECT had_image FROM messages WHERE role='user'").fetchone()[0] == 1
    assert all(message.image is None for message in app.history.messages(app.chat_id))
    app.set_question("Explain a detail")
    app.submit()
    wait_until(qapp, lambda: app.generation is None and not app.jobs)
    assert sum(message.image is not None for message in provider.requests[-1].messages) == 1
    dispose(app, qapp)


def test_failed_database_send_preserves_draft_and_no_request(qapp, tmp_path, monkeypatch):
    """A persistence failure occurs before draft clearing or generation, so retry never loses user text."""
    app = controller(tmp_path, monkeypatch)
    provider = FakeProvider()
    monkeypatch.setattr("maya.ui.app.create_provider", lambda settings, key: provider)

    def fail(*args):
        raise sqlite3.OperationalError("synthetic disk-full")

    monkeypatch.setattr(app.history, "begin_turn", fail)
    app.set_question("Explain my code")
    app.submit()
    assert app.question == "Explain my code" and not app.messages
    assert not provider.requests and app.generation is None
    dispose(app, qapp)


def test_history_off_regenerate_preserves_saved_turn(qapp, tmp_path, monkeypatch):
    """Turning history OFF prevents further writes, including an in-memory regenerated turn."""
    app = controller(tmp_path, monkeypatch)
    provider = FakeProvider(1)
    monkeypatch.setattr("maya.ui.app.create_provider", lambda settings, key: provider)
    app.set_question("First question")
    app.submit()
    wait_until(qapp, lambda: app.generation is None and not app.jobs)
    saved = app.history.messages(app.chat_id)
    app.settings.save_history = False
    app.regenerate()
    wait_until(qapp, lambda: app.generation is None and not app.jobs)
    assert app.history.messages(app.chat_id) == saved
    assert app.messages[-1].id is None
    dispose(app, qapp)


@pytest.mark.parametrize("kind,success,calls", [("network", True, 2), ("auth", False, 1)])
def test_worker_retry_only_transient_before_output(qapp, kind, success, calls):
    """A pre-output network error retries; an authentication error stops immediately."""

    class InitialFailure:
        calls = 0

        def stream(self, request, token):
            self.calls += 1
            if self.calls == 1:
                raise MayaError("Synthetic failure", kind)
            yield StreamEvent("text", "Recovered")
            yield StreamEvent("finish", "complete")

    provider = InitialFailure()
    worker = Generation(provider, None, 1, 10)
    results = []
    worker.ended.connect(lambda *values: results.append(values))
    worker.start()
    wait_until(qapp, lambda: results and not worker.isRunning())
    assert provider.calls == calls
    assert (results[0][0] == "complete") is success
    worker.deleteLater()


def test_many_code_blocks_fit_small_panel_and_copy(qapp):
    """Long language names and many fences keep one compact Copy code control, retaining exact code text."""
    from maya.ui.widgets import MessageCard

    text = "\n".join(f"```{'python' * 20}\nprint({i})\n```" for i in range(60))
    card = MessageCard(Message("assistant", text))
    card.resize(330, 600)
    card.show()
    qapp.processEvents()
    assert card.width() == 330
    assert card.copy_code.isVisible() and len(card.code_menu.actions()) == 50
    card.code_menu.actions()[1].trigger()
    assert qapp.clipboard().text() == "print(1)\n"
    card.hide()
    card.deleteLater()


def test_compact_reset_and_capture_blocks_new_chat(qapp, tmp_path, monkeypatch):
    """Reset an expanded window without losing its draft; a pending capture blocks conversation switches."""
    app = controller(tmp_path, monkeypatch)
    app.main.show()
    app.set_question("Keep this draft")
    app.main.toggle_navigation()
    app.compact_window()
    qapp.processEvents()
    assert app.main.width() == 480 and not app.main.sidebar.isVisible()
    assert app.question == "Keep this draft" and app.settings.window_geometry[2] == 480
    app.capturing = True
    app.new_chat()
    assert app.question == "Keep this draft"
    app.capturing = False
    dispose(app, qapp)


def test_missing_model_and_unknown_vision_leave_previous_turn(qapp, tmp_path, monkeypatch):
    """Rejected model/vision validation never truncates a saved turn or clears the replacement draft."""
    app = controller(tmp_path, monkeypatch)
    app.messages = [Message("user", "Old question"), Message("assistant", "Old answer")]
    app.draft_edit = True
    app.set_question("Replacement question")
    app.selected_model = None
    app.submit()
    assert len(app.messages) == 2 and app.question == "Replacement question"
    app.selected_model = Model("unknown", "Unknown", "compatible", None)
    image = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(image).rectangle((0, 0, 40, 50), fill="black")
    app.settings.screen_enabled = True
    app.pending_image = prepare(image)
    app.submit()
    assert app.draft_edit and app.messages[-1].text == "Old answer"
    assert app.generation is None
    dispose(app, qapp)


def test_minimum_windows_with_screenshot_and_code_response(qapp, tmp_path, monkeypatch):
    """A visible image, feedback menu, and fenced code do not force either mode wider than its minimum."""
    app = controller(tmp_path, monkeypatch)
    image = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(image).rectangle((0, 0, 40, 50), fill="black")
    attachment = prepare(image)
    app.settings.screen_enabled = True
    app.pending_image = attachment
    app.attachment_changed.emit()
    app.messages = [
        Message("user", "Explain the screenshot", image=attachment),
        Message("assistant", "Try:\n```python\nprint('hello')\n```\nThen check the output."),
    ]
    app.messages_reset.emit(app.messages)
    app.main.resize(400, 450)
    app.mini.resize(320, 360)
    app.main.show()
    app.mini.show()
    qapp.processEvents()
    assert app.main.width() == 400 and app.main.height() == 450
    assert app.mini.width() == 320 and app.mini.height() == 360
    for panel in (app.main.panel, app.mini.panel):
        assert panel.rect().contains(panel.attachment.geometry())
        assert panel.rect().contains(panel.remove_attachment.geometry())
        assert panel.rect().contains(panel.send.geometry())
        assert panel.view.scroll.horizontalScrollBar().maximum() == 0
    app.main.toggle_navigation()
    qapp.processEvents()
    assert app.main.height() == 450  # Navigation scrolls instead of forcing the client taller.
    dispose(app, qapp)


def test_manual_model_and_vision_preference_survive_endpoint_scoped_restart(qapp, tmp_path, monkeypatch):
    """Manual IDs restore without a catalog; unknown vision needs explicit confirmation and stays host-scoped."""
    app = controller(tmp_path, monkeypatch)
    app.settings.provider = "compatible"
    app.settings.urls["compatible"] = "http://127.0.0.1:1234/v1"
    app.use_model(Model("local-model", "local-model", "compatible", True))
    saved = app.store.load()
    app.settings = saved
    app.load_cache()
    assert app.selected_model.id == "local-model" and app.selected_model.vision is True
    app.settings.urls["compatible"] = "http://127.0.0.1:4321/v1"
    app.load_cache()
    assert app.selected_model is None
    app.settings.urls["compatible"] = "http://127.0.0.1:1234/v1"
    discovered = Model("local-model", "Discovered", "compatible", None, 32000, 8192)
    app.models = [discovered]
    app.use_model(Model("local-model", "Discovered", "compatible", True, 32000, 8192))
    assert app.default_model([discovered]).vision is True
    assert app.default_model([discovered]).context == 32000
    assert app.default_model([Model("local-model", "Text only", "compatible", False)]).vision is False
    dispose(app, qapp)


def test_failed_catalog_refresh_ignores_older_credentials_result(qapp, tmp_path, monkeypatch):
    """A queued catalog from a cancelled old credential cannot overwrite a newer refresh that failed to start."""
    from threading import Event

    app = controller(tmp_path, monkeypatch)
    release = Event()

    class DelayedCatalog:
        def list_models(self, token):
            release.wait(2)
            return [Model("old-key-model", "Old key", "gemini")]

    monkeypatch.setattr("maya.ui.app.create_provider", lambda *args: DelayedCatalog())
    app.refresh_models()

    def invalid_key(*args):
        raise MayaError("New credential is missing", "credentials")

    monkeypatch.setattr("maya.ui.app.create_provider", invalid_key)
    app.refresh_models()
    release.set()
    wait_until(qapp, lambda: not app.jobs)
    assert not app.models
    assert "missing" in app.main.panel.notice_text
    dispose(app, qapp)


def test_cache_write_failure_keeps_discovered_models(qapp, tmp_path, monkeypatch):
    """Local cache failure does not discard a valid provider catalog or prevent model selection."""
    app = controller(tmp_path, monkeypatch)

    class Catalog:
        def list_models(self, token):
            return [Model("discovered", "Discovered", "gemini", True)]

    monkeypatch.setattr("maya.ui.app.create_provider", lambda *args: Catalog())

    def fail(*args):
        raise sqlite3.OperationalError("synthetic read-only cache")

    monkeypatch.setattr(app.history, "cache_models", fail)
    app.refresh_models()
    wait_until(qapp, lambda: not app.jobs)
    assert app.selected_model.id == "discovered" and len(app.models) == 1
    assert "could not be cached" in app.main.panel.notice_text
    dispose(app, qapp)


def test_memory_and_history_disk_failures_preserve_editor(qapp, tmp_path, monkeypatch):
    """Failed saves retain typed memory; an unreadable history list disables mutations with a safe explanation."""
    from PyQt5.QtWidgets import QMessageBox

    history = HistoryStore(tmp_path / "test.db")
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[-1]))
    dialog = SettingsDialog(Settings(), FakeSecrets(), history, tmp_path)

    def fail(*args):
        raise sqlite3.OperationalError("synthetic disk-full with secret123")

    monkeypatch.setattr(history, "remember", fail)
    dialog.memory_text.setText("Keep this preference")
    dialog.add_memory()
    assert dialog.memory_text.text() == "Keep this preference"
    assert messages and "secret123" not in messages[-1]
    monkeypatch.setattr(history, "chats", fail)
    picker = HistoryDialog(history)
    assert not picker.open_button.isEnabled() and "Could not read" in picker.summary.text()
    dialog.deleteLater()
    picker.deleteLater()


def test_capture_off_during_hide_delay_takes_no_pixels(qapp, tmp_path, monkeypatch):
    """Turning Screen OFF during the compositor delay restores Maya and prevents the capture worker entirely."""
    app = controller(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr("maya.ui.app.capture", lambda *args: calls.append(args))
    app.main.show()
    app.settings.screen_enabled = True
    app.capture_screen()
    assert app.capturing
    app.toggle_screen()
    wait_until(qapp, lambda: not app.capturing)
    assert not calls and app.main.isVisible() and app.pending_image is None
    dispose(app, qapp)


def test_capture_error_restores_windows_and_keeps_draft(qapp, tmp_path, monkeypatch):
    """A capture failure returns the original window and question so text-only help remains usable."""
    app = controller(tmp_path, monkeypatch)

    def unavailable(*args):
        raise MayaError("No display is available", "capture")

    monkeypatch.setattr("maya.ui.app.capture", unavailable)
    app.main.show()
    app.set_question("Explain my error")
    app.settings.screen_enabled = True
    app.capture_screen()
    wait_until(qapp, lambda: not app.capturing and not app.jobs)
    assert app.main.isVisible() and app.question == "Explain my error"
    assert "No display" in app.main.panel.notice_text
    dispose(app, qapp)


def test_capture_requires_real_preview_accept_or_discard(qapp, tmp_path, monkeypatch):
    """The full capture flow cannot attach a new image until the actual review dialog is explicitly accepted."""
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication
    from maya.ui.capture_ui import ImagePreview

    app = controller(tmp_path, monkeypatch)
    source = Image.new("RGB", (200, 100), "white")
    ImageDraw.Draw(source).rectangle((0, 0, 80, 50), fill="navy")
    monkeypatch.setattr("maya.ui.app.capture", lambda *args: (source, {}))
    app.main.show()
    app.settings.screen_enabled = True
    app.set_question("Explain this screen")
    decisions = [True, False]
    observed = []
    timer = QTimer()

    def review():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, ImagePreview) and decisions:
            observed.append(app.generation is None)
            if decisions.pop(0):
                assert app.pending_image is None
                dialog.accept()
            else:
                dialog.reject()

    timer.timeout.connect(review)
    timer.start(10)
    app.capture_screen()
    wait_until(qapp, lambda: app.pending_image is not None and not app.jobs)
    assert app.pending_image == app.last_image and app.generation is None
    app.capture_screen()
    wait_until(qapp, lambda: len(observed) == 2 and not app.jobs)
    assert app.pending_image is None and app.reuse_image is None
    assert app.question == "Explain this screen" and observed == [True, True]
    timer.stop()
    dispose(app, qapp)


def test_region_selection_scaled_reversed_release_and_escape(qapp):
    """Logical rectangles map to source pixels even with reversed dragging and no final mouse-move event."""
    from PyQt5.QtCore import QPoint
    from maya.ui.capture_ui import RegionSelector

    source = Image.new("RGB", (800, 400), "white")
    selector = RegionSelector(source, qapp.primaryScreen())
    selector.resize(400, 200)
    selector.show()
    qapp.processEvents()
    QTest.mousePress(selector, Qt.LeftButton, pos=QPoint(100, 100))
    QTest.mouseRelease(selector, Qt.LeftButton, pos=QPoint(20, 20))
    assert selector.result() == selector.Accepted
    assert selector.selected.size == (162, 162)
    cancelled = RegionSelector(source, qapp.primaryScreen())
    cancelled.show()
    QTest.keyClick(cancelled, Qt.Key_Escape)
    assert cancelled.selected is None and cancelled.result() == cancelled.Rejected
    selector.deleteLater()
    cancelled.deleteLater()
