"""Explicit, bounded .env support: provider keys stay private and never become app preferences."""

from io import StringIO
import os
from pathlib import Path

from dotenv import dotenv_values

from maya.core.types import MayaError
from maya.core.config import validate_url
from .secrets import validate_key


ENV_NAMES = frozenset(
    {
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "MAYA_COMPATIBLE_API_KEY",
        "MAYA_DATA_DIR",
        "MAYA_COMPATIBLE_BASE_URL",
    }
)


def load_environment(path: Path, required: bool = False) -> tuple[str, ...]:
    """Read exactly one file, validate before applying, and preserve existing process variables.

    Unknown variables are ignored. Expansion is disabled so credentials cannot interpolate another
    environment secret. Nothing searches parent directories, executes shell code or logs values.
    """
    try:
        with path.open("rb") as stream:
            raw = stream.read(65537)
    except FileNotFoundError as exc:
        if not required:
            return ()
        raise MayaError("The requested environment file does not exist.", "config") from exc
    except OSError as exc:
        raise MayaError("Could not read the environment file. Check its permissions.", "config") from exc
    if len(raw) > 65536:
        raise MayaError("The environment file exceeds the 64 KiB limit.", "config")
    try:
        values = dotenv_values(stream=StringIO(raw.decode("utf-8-sig")), interpolate=False)
    except (UnicodeError, ValueError) as exc:
        raise MayaError("Use a UTF-8 environment file with KEY=value entries.", "config") from exc
    pending = {}
    for name, value in values.items():
        if name not in ENV_NAMES or name in os.environ or not value:
            continue
        if "\0" in value or "\n" in value or "\r" in value:
            raise MayaError(f"Use one line for {name} in the environment file.", "config")
        try:
            if name == "MAYA_COMPATIBLE_BASE_URL":
                value = validate_url(value)
            elif name != "MAYA_DATA_DIR":
                if any(character.isspace() for character in value):
                    raise MayaError("Whitespace is not allowed.", "credentials")
                value = validate_key(value)
        except MayaError as exc:
            raise MayaError(
                f"Use a valid {'base URL' if name == 'MAYA_COMPATIBLE_BASE_URL' else 'key'} for {name}.",
                "config",
            ) from exc
        pending[name] = value
    # An invalid later entry must not leave some credentials or a data-directory override applied.
    os.environ.update(pending)
    return tuple(pending)
