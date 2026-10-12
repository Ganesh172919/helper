"""Validated non-secret settings, saved atomically outside the source tree."""

from dataclasses import asdict, dataclass, field, fields
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from .types import MayaError
from .safety import redact


# --- Endpoint validation prevents credentials in URLs and accidental plaintext remote traffic. ---
DEFAULT_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "openrouter": "https://openrouter.ai/api/v1",
    "compatible": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "ollama": "http://127.0.0.1:11434",
}
PROVIDERS = {
    "gemini": "Google Gemini",
    "openrouter": "OpenRouter",
    "compatible": "OpenAI-compatible",
    "anthropic": "Anthropic",
    "ollama": "Local Ollama",
}


def validate_url(value: str) -> str:
    """Return a clean base URL; raise MayaError for credentials, queries, or insecure remote URLs."""
    if not isinstance(value, str) or any(ch.isspace() or ord(ch) < 32 for ch in value.strip()):
        raise MayaError("Use a valid base URL without whitespace or control characters.", "config")
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise MayaError("Use a valid base URL and port (1–65535).", "config") from exc
    if (
        not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in {"http", "https"}
        or port == 0
    ):
        raise MayaError("Use a base URL without credentials, query strings, or fragments.", "config")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise MayaError("Remote providers require HTTPS. HTTP is allowed only on localhost.", "config")
    return value.strip().rstrip("/")


def data_directory() -> Path:
    """Resolve an optional MAYA_DATA_DIR override, otherwise the user's local application directory."""
    if value := os.getenv("MAYA_DATA_DIR"):
        return Path(value).expanduser().resolve()
    base = os.getenv("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "MayaHelper"


# --- Preferences never contain API keys; version validation is centralized. ---
@dataclass
class Settings:
    """Defaults favor explicit capture, bounded context, and user-controlled memory."""

    provider: str = "gemini"
    models: dict[str, str] = field(default_factory=dict)
    model_preferences: dict[str, dict] = field(default_factory=dict)
    urls: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_URLS))
    screen_enabled: bool = False
    capture_scope: str = "monitor"
    skill: str = "auto"
    custom_profiles: dict[str, dict[str, str]] = field(default_factory=dict)
    classifier_enabled: bool = False
    classifier_model: str = ""
    classifier_timeout: int = 8
    temperature: float = 0.7
    max_output: int = 4096
    context_budget: int = 16000
    timeout: int = 120
    retries: int = 2
    image_edge: int = 1568
    remember_enabled: bool = True
    save_history: bool = True
    redact_text: bool = True
    language: str = "Auto (match my question)"
    response_style: str = "Clear, practical explanations with examples"
    display_name: str = ""
    mode: str = "normal"
    pin_main: bool = True
    reduce_motion: bool = False
    overlay_opacity: float = 0.96
    orb_size: int = 58
    orb_opacity: float = 0.9
    orb_position: list[int] = field(default_factory=list)
    window_geometry: list[int] = field(default_factory=list)
    hotkey: str = "Alt+Shift+N"
    capture_hotkey: str = "Alt+Shift+S"
    screen_hotkey: str = "Alt+Shift+C"

    def validate(self) -> None:
        """Reject invalid persisted/UI values early; raises MayaError with a repairable explanation."""
        if self.provider not in PROVIDERS:
            raise MayaError("Unknown provider. Choose a supported provider in Settings.", "config")
        bounds = {
            "temperature": (0, 2),
            "max_output": (128, 65536),
            "context_budget": (2048, 200000),
            "timeout": (15, 600),
            "retries": (0, 3),
            "image_edge": (512, 4096),
            "orb_size": (44, 84),
            "orb_opacity": (0.35, 1),
            "overlay_opacity": (0.65, 1),
            "classifier_timeout": (2, 30),
        }
        for name, (low, high) in bounds.items():
            value = getattr(self, name)
            is_integer = name not in {"temperature", "orb_opacity", "overlay_opacity"}
            if (
                type(value) not in {int, float}
                or not math.isfinite(value)
                or (is_integer and type(value) is not int)
                or not low <= value <= high
            ):
                raise MayaError(f"{name} must be between {low} and {high}.", "config")
        for name in (
            "screen_enabled",
            "remember_enabled",
            "save_history",
            "redact_text",
            "classifier_enabled",
            "pin_main",
            "reduce_motion",
        ):
            if type(getattr(self, name)) is not bool:
                raise MayaError(f"{name} must be true or false.", "config")
        if (
            not isinstance(self.classifier_model, str)
            or len(self.classifier_model) > 200
            or (
                self.classifier_model
                and not re.fullmatch(r"(?:models/)?gemini-[A-Za-z0-9._-]+", self.classifier_model)
            )
        ):
            raise MayaError("Use a Gemini model ID from your discovered catalog for routing.", "config")
        if self.mode not in {"normal", "overlay"} or self.capture_scope not in {
            "monitor",
            "all",
            "window",
            "region",
            "last",
        }:
            raise MayaError("Invalid display or capture mode.", "config")
        if not isinstance(self.models, dict) or not isinstance(self.urls, dict):
            raise MayaError("Invalid provider settings.", "config")
        for provider, model in self.models.items():
            if (
                provider not in PROVIDERS
                or not isinstance(model, str)
                or len(model) > 200
                or any(ch.isspace() for ch in model)
            ):
                raise MayaError("Invalid saved model ID.", "config")
        for provider, url in DEFAULT_URLS.items():
            self.urls[provider] = validate_url(self.urls.get(provider, url))
        if not isinstance(self.model_preferences, dict) or set(self.model_preferences) - set(PROVIDERS):
            raise MayaError("Invalid saved model preferences.", "config")
        for provider, preference in self.model_preferences.items():
            if not isinstance(preference, dict) or set(preference) != {
                "id",
                "endpoint",
                "manual",
                "vision_confirmed",
            }:
                raise MayaError("Invalid saved model preference.", "config")
            identifier = preference["id"]
            if (
                not isinstance(identifier, str)
                or not identifier
                or len(identifier) > 200
                or any(ch.isspace() for ch in identifier)
            ):
                raise MayaError("Invalid saved model ID.", "config")
            validate_url(preference["endpoint"])
            if type(preference["manual"]) is not bool or type(preference["vision_confirmed"]) is not bool:
                raise MayaError("Invalid saved model capability preference.", "config")
            if preference["manual"] and provider not in {"compatible", "ollama"}:
                raise MayaError(
                    "Manual model IDs are supported only for compatible and local providers.", "config"
                )
        # Native provider keys must never be redirected by a damaged config file.
        for provider in ("gemini", "openrouter", "anthropic"):
            if self.urls[provider] != DEFAULT_URLS[provider]:
                raise MayaError(
                    f"The {provider} endpoint is fixed; use the compatible adapter for custom URLs.", "config"
                )
        if urlsplit(self.urls["ollama"]).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise MayaError(
                "Local Ollama requires a localhost URL. Use the compatible adapter for a remote server.",
                "config",
            )
        for name in (
            "display_name",
            "language",
            "response_style",
            "skill",
            "hotkey",
            "capture_hotkey",
            "screen_hotkey",
        ):
            if not isinstance(getattr(self, name), str) or len(getattr(self, name)) > 1000:
                raise MayaError(f"Invalid {name}.", "config")
        # Saved profiles are bounded text preferences, never executable tools or plugins.
        for name in ("display_name", "language", "response_style"):
            if redact(getattr(self, name))[1]:
                raise MayaError(
                    "Keep recognizable credentials out of personal preferences; use Providers.", "config"
                )
        if not isinstance(self.custom_profiles, dict) or len(self.custom_profiles) > 20:
            raise MayaError("Save at most 20 custom task profiles.", "config")
        names = set()
        for identifier, profile in self.custom_profiles.items():
            if not isinstance(identifier, str) or not re.fullmatch(r"custom:[a-f0-9]{12}", identifier):
                raise MayaError("Invalid custom task profile ID.", "config")
            if not isinstance(profile, dict) or set(profile) != {"name", "instruction"}:
                raise MayaError("A custom profile needs a name and instructions.", "config")
            for key, limit in (("name", 80), ("instruction", 4000)):
                value = profile[key]
                if not isinstance(value, str) or not value.strip() or len(value) > limit:
                    raise MayaError(f"Profile {key} must contain 1–{limit:,} characters.", "config")
            name = profile["name"].strip().casefold()
            if redact(profile["name"] + "\n" + profile["instruction"])[1]:
                raise MayaError("Do not save recognizable secrets in task profiles.", "config")
            if name in names:
                raise MayaError("Use a different name for each custom task profile.", "config")
            names.add(name)
        for name in ("orb_position", "window_geometry"):
            value = getattr(self, name)
            if (
                not isinstance(value, list)
                or not all(type(x) is int for x in value)
                or len(value) not in {0, 2 if name == "orb_position" else 4}
            ):
                raise MayaError(f"Invalid {name}.", "config")


class ConfigStore:
    """One settings file with atomic replace and explicit recovery for malformed files."""

    def __init__(self, directory: Path):
        """Create a writable local data directory; errors are surfaced by application startup."""
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "settings.json"

    def load(self) -> Settings:
        """Return defaults on first run; raise MayaError rather than silently overriding broken settings."""
        if not self.path.exists():
            return Settings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            names = {item.name for item in fields(Settings)}
            settings = Settings(**{key: value for key, value in raw.items() if key in names})
            settings.validate()
            return settings
        except (ValueError, TypeError, AttributeError, OSError) as exc:
            raise MayaError(
                "Settings could not be read. Rename settings.json in the data folder and restart.", "config"
            ) from exc

    def save(self, settings: Settings) -> None:
        """Validate, flush, and atomically replace settings; secrets are not accepted fields."""
        settings.validate()
        temp = self.path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as stream:
            json.dump(asdict(settings), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(self.path)
