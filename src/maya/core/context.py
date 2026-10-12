"""Inspectable answer context shared by local review and provider submission."""

from dataclasses import dataclass, replace
import hashlib
import json

from .config import Settings
from .prompts import InstructionManager, Skill, build_request
from .safety import redact
from .types import ImageAttachment, Message, Model, Request


@dataclass(frozen=True)
class AnswerContext:
    """A detached request and its provenance; credentials and transport headers are absent."""

    question: str
    request: Request
    skill: Skill
    memories: tuple[str, ...]
    history_total: int
    signature: str


def prepare_context(
    question: str,
    image: ImageAttachment | None,
    model: Model,
    settings: Settings,
    instructions: InstructionManager,
    skill: Skill,
    memories: list[str],
    previous: list[Message],
    window_title: str = "",
    editing: bool = False,
    chat_id: int | None = None,
) -> AnswerContext:
    """Build once, sanitize included text when enabled, and fingerprint relevant reviewed inputs.

    Older live Message objects are copied by build_request. The frozen image contains immutable
    bytes. Redaction affects the outgoing copy; existing history is never overwritten here.
    """
    # Sanitize raw preferences before JSON quoting; escaped assignment syntax must not hide a secret.
    safe_memories = [redact(item)[0] for item in memories] if settings.redact_text else memories
    system_settings = (
        replace(
            settings,
            **{
                name: redact(getattr(settings, name))[0]
                for name in ("display_name", "language", "response_style")
            },
        )
        if settings.redact_text
        else settings
    )
    system_skill = replace(skill, instruction=redact(skill.instruction)[0]) if settings.redact_text else skill
    system = instructions.system(system_skill, system_settings, safe_memories)
    request = build_request(model, system, previous + [Message("user", question)], image, settings)
    if settings.redact_text:
        request = replace(
            request,
            system=redact(request.system)[0],
            messages=tuple(replace(message, text=redact(message.text)[0]) for message in request.messages),
        )
    controls = {
        name: getattr(settings, name)
        for name in (
            "provider",
            "skill",
            "custom_profiles",
            "classifier_enabled",
            "classifier_model",
            "classifier_timeout",
            "screen_enabled",
            "remember_enabled",
            "save_history",
            "redact_text",
            "temperature",
            "max_output",
            "context_budget",
            "timeout",
            "retries",
        )
    }
    state = {
        "controls": controls,
        "endpoint": settings.urls[settings.provider],
        "gemini_endpoint": settings.urls["gemini"],
        "window": window_title if settings.skill == "auto" else "",
        "editing": editing,
        "chat_id": chat_id,
        "question": question,
        "model": model.__dict__,
        "system": request.system,
        "messages": [(m.role, m.text, m.status, m.id) for m in request.messages],
        "image": hashlib.sha256(image.data).hexdigest() if image else "",
        # Detect memory changes even when identical text has been redacted in the outbound copy.
        "memories": memories,
    }
    signature = hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return AnswerContext(question, request, skill, tuple(safe_memories), len(previous), signature)
