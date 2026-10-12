"""Regression checks for privacy defaults, persistence, memory retrieval, context budgets, and streams."""

import json

import pytest
from PIL import Image, ImageDraw

from maya.capture import monitor_at, prepare
from maya.core.config import ConfigStore, Settings, validate_url
from maya.core.prompts import InstructionManager, build_request, preferred_model
from maya.core.safety import redact, refusal
from maya.core.storage import HistoryStore
from maya.core.streaming import parse_sse, parse_ndjson
from maya.core.types import Cancellation, MayaError, Message, Model
from maya.platform.secrets import SecretStore, catalog_identity
from maya.platform.windows import WindowsDesktop


@pytest.mark.parametrize(
    "question,identifier",
    [
        ("Trace this binary search algorithm", "algorithms"),
        ("Explain this confidence interval", "statistics"),
        ("Check the units in this circuit", "engineering"),
        ("Explain this accounting term", "business"),
        ("Summarise these meeting notes", "meeting"),
        ("Explain this medical term", "health"),
        ("Why is this CSV malformed?", "files"),
        ("Explain the frame rate on this timeline", "media"),
        ("Explain this AutoCAD sketch constraint", "cad"),
        ("Draft a support reply to this customer complaint", "support"),
        ("Explain this DNS error", "network"),
        ("Help me navigate with the keyboard", "access"),
        ("Explain this form field", "forms"),
    ],
)
def test_expanded_domain_profiles_preserve_shared_rules(question, identifier):
    """Question-specific instructions remain bounded guidance under common grounding and safety rules."""
    from maya.core.prompts import BASE_RULES

    manager = InstructionManager()
    skill = manager.select("auto", question, "Visual Studio Code")
    assert skill.id == identifier and skill.chips
    system = manager.system(skill, Settings(), ["Use clear examples"])
    assert BASE_RULES in system and skill.instruction in system and "Use clear examples" in system


@pytest.mark.parametrize(
    "name,value", [("pin_main", 1), ("overlay_opacity", 0.1), ("overlay_opacity", float("nan"))]
)
def test_overlay_preference_validation(name, value):
    settings = Settings()
    setattr(settings, name, value)
    with pytest.raises(MayaError):
        settings.validate()


# --- SSE framing tests use adversarial byte splits instead of mirroring implementation lines. ---
@pytest.mark.parametrize("size", [1, 2, 3, 7, 10000])
def test_sse_split_unicode_comments_multiline_crlf(size):
    """Split a real protocol example at every byte size including inside UTF-8 and CRLF."""
    data = '\ufeff: keepalive\r\nevent: delta\r\ndata: {"text":\r\ndata: "హలో 🌸"}\r\n\r\ndata: [DONE]\n\n'.encode()
    events = list(parse_sse(data[index : index + size] for index in range(0, len(data), size)))
    assert len(events) == 2
    assert events[0].event == "delta"
    assert json.loads(events[0].data)["text"] == "హలో 🌸"
    assert events[1].data == "[DONE]"


def test_sse_eof_invalid_and_oversized():
    """EOF flushes a valid pending event; corrupt or unbounded event data fails clearly."""
    assert list(parse_sse([b"data: final"]))[0].data == "final"
    with pytest.raises(MayaError, match="UTF-8"):
        list(parse_sse([b"data: \xff\n\n"]))
    with pytest.raises(MayaError, match="oversized"):
        list(parse_sse([b"data: " + b"x" * 100], limit=20))


@pytest.mark.parametrize(
    "value",
    [
        "https://user:secret@example.com/v1",
        "http://remote.example/v1",
        "https://api.example/v1?key=secret",
        "file:///data",
        "javascript:alert(1)",
    ],
)
def test_bad_endpoint_rejected(value):
    """Keys cannot enter URLs or remote plaintext connections."""
    with pytest.raises(MayaError):
        validate_url(value)


def test_config_defaults_atomic_and_validation(tmp_path):
    """Screen defaults OFF, keys are absent from settings, and malformed files are recoverable errors."""
    store = ConfigStore(tmp_path)
    settings = store.load()
    assert not settings.screen_enabled
    store.save(settings)
    assert store.load() == settings
    assert "api_key" not in store.path.read_text()
    settings.timeout = 1
    with pytest.raises(MayaError):
        store.save(settings)
    store.path.write_text("{broken")
    with pytest.raises(MayaError, match="Rename"):
        store.load()


def test_native_provider_url_cannot_redirect():
    """Tampered configuration cannot redirect a native cloud key to an unrelated service."""
    settings = Settings()
    settings.urls["gemini"] = "https://example.com"
    with pytest.raises(MayaError, match="fixed"):
        settings.validate()


def test_history_recovery_cascade_cache_and_memory(tmp_path):
    """SQLite recovers interrupted turns and scopes memory/catalog to actual request settings."""
    path = tmp_path / "history.db"
    store = HistoryStore(path)
    chat = store.create_chat("Explain pip install")
    user = Message("user", "What does this command do?")
    user.id = store.add_message(chat, user)
    assistant = Message("assistant", "Partial answer", "streaming")
    assistant.id = store.add_message(chat, assistant)
    store.rate(assistant.id, 1)
    store = HistoryStore(path)
    assert store.messages(chat)[-1].status == "interrupted"
    store.remember("I prefer short explanations", "general")
    store.remember("Explain formulas using examples", "excel")
    assert len(store.relevant_memories("formula", "excel")) == 2
    assert len(store.relevant_memories("code", "code")) == 1
    model = Model("id", "Name", "gemini", True)
    identity = catalog_identity("https://example.com", "fake-key")
    store.cache_models("gemini", [model], identity)
    assert store.cached_models("gemini", identity)[0] == [model]
    assert not store.cached_models("gemini", "different-key")[0]
    store.delete_chat(chat)
    assert not store.messages(chat)
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM feedback").fetchone()[0] == 0


def test_context_pair_trimming_current_image_and_uncertainty():
    """Old complete pairs are trimmed; newest question/system/image survive with no stale images."""
    settings = Settings(context_budget=2048, max_output=512)
    model = Model("test", "Test", "gemini", True, 8000, 512)
    messages = [Message("user", "x" * 2000), Message("assistant", "y" * 2000)] * 3 + [
        Message("user", "Latest")
    ]
    request = build_request(model, "Fixed rules", messages, None, settings)
    assert request.messages[-1].text == "Latest"
    assert len(request.messages) % 2 == 1
    assert len(request.messages) < len(messages)
    with pytest.raises(MayaError, match="exceeds"):
        build_request(model, "rules", [Message("user", "x" * 10000)], None, settings)


def test_profiles_and_primary_discovered_models():
    """Task selection follows real text; preferred named Gemini IDs must actually exist in discovery."""
    manager = InstructionManager()
    assert manager.select("auto", "Why does this Excel formula fail?").id == "excel"
    assert manager.select("auto", "What does pip install do?").id == "command"
    assert manager.select("study", "Excel").id == "study"
    models = [
        Model("models/gemini-3.5-flash-lite", "Lite", "gemini", True),
        Model("models/gemini-3.8-flash", "Flash", "gemini", True),
    ]
    assert preferred_model(models).name == "Flash"
    assert preferred_model(models, models[0].id).name == "Lite"
    assert preferred_model([]) is None


def test_redaction_and_narrow_refusal():
    """Defensive explanation is allowed while obvious secrets/explicit theft are handled locally."""
    clean, changed = redact("password=hunter2 token context sk-" + "a" * 30)
    assert changed and "hunter2" not in clean and "a" * 30 not in clean
    assert refusal("Explain what ransomware is and how to protect my laptop") is None
    assert refusal("Create ransomware that encrypts other people's files")
    assert refusal("What does rm -rf ./cache do?") is None


def test_image_limits_blank_and_negative_monitor_coordinates():
    """Capture prep never upscales, bounds bytes, and rejects uniform frames."""
    image = Image.new("RGB", (3200, 1800), "white")
    ImageDraw.Draw(image).rectangle((100, 100, 1800, 900), fill="navy")
    attachment = prepare(image, 1568, 500000)
    assert max(attachment.width, attachment.height) <= 1568
    assert len(attachment.data) <= 500000
    with pytest.raises(MayaError, match="blank"):
        prepare(Image.new("RGB", (300, 300), "black"))
    monitors = [
        {},
        {"left": 0, "top": 0, "width": 1920, "height": 1080},
        {"left": -1920, "top": -100, "width": 1920, "height": 1080},
    ]
    assert monitor_at(monitors, (-100, 30))["left"] == -1920


def test_cancellation_deadline_and_hotkey_parser():
    """Cancellation and deadline have distinct public errors; unsupported shortcuts are rejected."""
    token = Cancellation()
    token.cancel()
    with pytest.raises(MayaError) as stopped:
        token.check()
    assert stopped.value.kind == "cancelled"
    expired = Cancellation(-1)
    with pytest.raises(MayaError) as timed:
        expired.check()
    assert timed.value.kind == "timeout"
    assert WindowsDesktop.parse_hotkey("Alt+Shift+N")[1] == ord("N")
    with pytest.raises(MayaError):
        WindowsDesktop.parse_hotkey("Win+M")


def test_secret_accounts_scoped_to_endpoint():
    """A compatible provider cannot reuse a credential stored for a different base URL."""
    assert SecretStore.account("compatible", "https://one.example/v1") != SecretStore.account(
        "compatible", "https://two.example/v1"
    )


def test_custom_profiles_persist_select_and_keep_base_rules(tmp_path):
    """Saved user profiles survive restart; their preferences cannot remove shared safety instructions."""
    from maya.core.prompts import BASE_RULES

    identifier = "custom:123456abcdef"
    settings = Settings(
        custom_profiles={identifier: {"name": "Exam revision", "instruction": "Ask one practice question."}}
    )
    store = ConfigStore(tmp_path)
    store.save(settings)
    loaded = store.load()
    manager = InstructionManager(loaded.custom_profiles)
    skill = manager.select(identifier, "Excel formula")
    from maya.core.prompts import SKILLS

    assert skill.id == identifier and len(manager.profiles()) == len(SKILLS) + 1
    prompt = manager.system(skill, loaded, ["I prefer examples"])
    assert prompt.startswith(BASE_RULES)
    assert '"Ask one practice question."' in prompt and "I prefer examples" in prompt
    assert manager.select("custom:000000000000", "Excel formula").id == "excel"


@pytest.mark.parametrize(
    "profiles",
    [
        [],
        {"python": {"name": "Override", "instruction": "text"}},
        {"custom:123456abcdef": {"name": "", "instruction": "text"}},
        {"custom:123456abcdef": {"name": "a", "instruction": "x" * 4001}},
        {"custom:123456abcdef": {"name": "a", "instruction": "text", "script": "unsafe"}},
        {"custom:123456abcdef": {"name": "a", "instruction": "password=secret123"}},
        {
            "custom:123456abcdef": {"name": "A", "instruction": "text"},
            "custom:111111111111": {"name": " a ", "instruction": "text"},
        },
        {f"custom:{i:012x}": {"name": str(i), "instruction": "text"} for i in range(21)},
    ],
)
def test_custom_profile_invalid_config_rejected(profiles):
    """Corrupt, unbounded, duplicate, or secret-bearing profiles never become saved settings."""
    with pytest.raises(MayaError):
        Settings(custom_profiles=profiles).validate()


def test_memory_edit_scope_duplicates_missing_and_secrets(tmp_path):
    """Edits retain IDs, update retrieval scopes, and roll back duplicate or invalid changes."""
    store = HistoryStore(tmp_path / "history.db")
    store.remember("Use short examples")
    store.remember("Explain formulas")
    memory = store.memories()[-1]
    store.update_memory(memory["id"], "Use Python examples", "python")
    assert "Use Python examples" in store.relevant_memories("examples", "python")
    assert "Use Python examples" not in store.relevant_memories("examples", "excel")
    with pytest.raises(MayaError, match="already saved"):
        store.update_memory(memory["id"], "Explain formulas", "general")
    assert store.memories()[-1]["text"] == "Use Python examples"
    with pytest.raises(MayaError, match="no longer exists"):
        store.update_memory(999, "missing", "general")
    with pytest.raises(MayaError, match="passwords"):
        store.remember("password=secret123")
    assert len(store.memories()) == 2


def test_history_search_message_text_literal_wildcards_and_rename(tmp_path):
    """Find message text even when absent from titles; percent/underscore search stays literal."""
    store = HistoryStore(tmp_path / "history.db")
    first = store.create_chat("A SQL question")
    store.add_message(first, Message("assistant", "Check tax_rate = 12%"))
    second = store.create_chat("No matching details")
    store.add_message(second, Message("assistant", "12x and tax-rate"))
    assert [chat["id"] for chat in store.chats("tax_rate")] == [first]
    assert [chat["id"] for chat in store.chats("12%")] == [first]
    assert [chat["id"] for chat in store.chats("SQL")] == [first]
    assert not store.chats("' OR 1=1 --")
    store.rename_chat(first, "Renamed SQL example")
    assert store.chats("Renamed")[0]["id"] == first
    with pytest.raises(MayaError):
        store.rename_chat(first, " ")
    with pytest.raises(MayaError):
        store.rename_chat(999, "Missing")


def test_atomic_turn_replacement_rolls_back_on_database_failure(tmp_path):
    """A failed assistant insert preserves the original pair and does not leave a new orphan question."""
    import sqlite3

    store = HistoryStore(tmp_path / "history.db")
    chat, user_id, _ = store.begin_turn(
        None, Message("user", "Old question"), Message("assistant", "Old answer"), "gemini", "test"
    )
    with store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_answer BEFORE INSERT ON messages WHEN NEW.role='assistant' "
            "BEGIN SELECT RAISE(ABORT, 'synthetic disk failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        store.begin_turn(
            chat,
            Message("user", "New question"),
            Message("assistant", "", "streaming"),
            "gemini",
            "test",
            user_id,
        )
    assert [message.text for message in store.messages(chat)] == ["Old question", "Old answer"]
    with pytest.raises(sqlite3.IntegrityError):
        store.begin_turn(None, Message("user", "Another"), Message("assistant", ""), "gemini", "test")
    assert len(store.chats()) == 1


def test_verification_credentials_do_not_read_environment(monkeypatch):
    """Smoke/startup verification cannot accidentally use a user's saved or environment key."""
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-do-not-read")
    secrets = SecretStore(enabled=False)
    assert secrets.backend is None
    assert secrets.get("gemini", "https://generativelanguage.googleapis.com/v1beta") == ""
    with pytest.raises(MayaError, match="disabled"):
        secrets.save("gemini", "https://generativelanguage.googleapis.com/v1beta", "synthetic")


@pytest.mark.parametrize(
    "changes",
    [
        {"retries": True},
        {"max_output": 512.5},
        {"temperature": float("nan")},
        {"orb_position": [1, 2, 3, 4]},
        {"window_geometry": [1, 2]},
        {"models": {"gemini": "has spaces"}},
        {"models": {"unknown": "model"}},
    ],
)
def test_invalid_numeric_geometry_or_model_settings(changes):
    """JSON type confusion cannot create fractional retry counts or malformed native placement."""
    with pytest.raises(MayaError):
        Settings(**changes).validate()


@pytest.mark.parametrize(
    "url",
    [
        None,
        "https://api.example:bad/v1",
        "https://api.example:65536/v1",
        "https://api.example:0/v1",
        "https://bad host/v1",
        "https://api.example/\npath",
    ],
)
def test_invalid_url_ports_and_controls(url):
    """Malformed endpoints produce a safe configuration error before a transport is constructed."""
    with pytest.raises(MayaError):
        validate_url(url)


def test_ndjson_split_unicode_and_unclosed_size_limit():
    """Ollama framing handles split UTF-8 and rejects endless lines before receiving a newline."""
    data = '\ufeff{"text":"హలో 🌸"}\r\n\n{"done":true}'.encode()
    lines = list(parse_ndjson(data[index : index + 1] for index in range(len(data))))
    assert json.loads(lines[0])["text"] == "హలో 🌸" and json.loads(lines[1])["done"]
    with pytest.raises(MayaError, match="oversized"):
        list(parse_ndjson([b"x" * 11, b"x" * 11], limit=20))
    with pytest.raises(MayaError, match="UTF-8"):
        list(parse_ndjson([b"\xff"]))


def test_educational_malware_report_is_allowed():
    """The local gate permits an educational report while still rejecting explicit malware creation."""
    assert refusal("Write a report on ransomware prevention") is None
    assert refusal("Create an educational summary about ransomware") is None
    assert refusal("Write Python code for ransomware")


@pytest.mark.parametrize(
    "preference",
    [
        {"id": "test", "endpoint": "http://remote.example/v1", "manual": True, "vision_confirmed": True},
        {"id": "test", "endpoint": "http://127.0.0.1:1234/v1", "manual": True, "vision_confirmed": "yes"},
        {"id": "bad id", "endpoint": "http://127.0.0.1:1234/v1", "manual": True, "vision_confirmed": False},
        {"id": "test", "endpoint": "http://127.0.0.1:1234/v1", "manual": True},
    ],
)
def test_model_preference_validation(preference):
    """Persisted manual choices cannot bypass endpoint or capability-type validation."""
    with pytest.raises(MayaError):
        Settings(model_preferences={"compatible": preference}).validate()
