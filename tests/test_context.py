"""Prepared context is detached, bounded and inspectable without credentials or network access."""

from dataclasses import replace

from maya.core.config import Settings
from maya.core.context import prepare_context
from maya.core.prompts import InstructionManager
from maya.core.routing import classification_payload
from maya.core.types import ImageAttachment, Message, Model


def context(settings=None, previous=None, memories=None, question="Explain this command", image=None):
    settings = settings or Settings()
    manager = InstructionManager(settings.custom_profiles)
    skill = manager.select(settings.skill, question, "Synthetic terminal")
    return prepare_context(
        question,
        image,
        Model("test", "Test", "gemini", True, 30000, 4096),
        settings,
        manager,
        skill,
        memories or [],
        previous or [],
        "Synthetic terminal",
    )


def test_context_copies_history_and_redacts_only_outgoing_text():
    previous = [
        Message("user", "Earlier question"),
        Message("assistant", '"api_key": "synthetic private value"'),
    ]
    candidate = context(previous=previous, memories=['"password": "synthetic memory secret"'])
    assert "synthetic" not in candidate.request.messages[1].text
    assert "synthetic memory secret" not in candidate.request.system
    assert "synthetic private value" in previous[1].text
    previous[0].text = "Changed outside the prepared request"
    assert candidate.request.messages[0].text == "Earlier question"
    assert candidate.history_total == 2 and len(candidate.request.messages) == 3


def test_context_signature_tracks_relevant_inputs_but_ignores_window_chrome():
    settings = Settings()
    original = context(settings)
    settings.pin_main = False
    settings.reduce_motion = True
    settings.orb_position = [100, 100]
    assert context(settings).signature == original.signature
    settings.screen_enabled = True
    assert context(settings).signature != original.signature
    assert context(question="Another question").signature != original.signature
    assert context(memories=["Prefer shorter answers"]).signature != original.signature


def test_signature_uses_actual_image_bytes_and_request_image_is_not_aliased():
    first = ImageAttachment(b"first", "image/png", 1, 1, "same-metadata-digest")
    second = replace(first, data=b"second")
    a, b = context(image=first), context(image=second)
    assert a.signature != b.signature
    assert a.request.messages[-1].image is first


def test_classification_preview_is_the_bounded_redacted_payload():
    manager = InstructionManager()
    payload = classification_payload(
        manager, 'password="synthetic private value" ' + "x" * 4000, "window" * 100
    )
    assert set(payload) == {"question_excerpt", "window_title", "available_profiles"}
    assert len(payload["question_excerpt"]) <= 2000 and len(payload["window_title"]) <= 200
    assert "synthetic private value" not in str(payload)
    assert len(payload["available_profiles"]) == 34
