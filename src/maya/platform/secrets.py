"""OS-backed key storage; there is no plaintext credential fallback."""

import hashlib
import os
import sys
import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from maya.core.config import DEFAULT_URLS, PROVIDERS, validate_url
from maya.core.types import MayaError


# --- Credential accounts include the endpoint to prevent reuse at another host. ---
def validate_key(value: str) -> str:
    """Accept bounded printable ASCII header credentials; errors never include the supplied value."""
    if not isinstance(value, str) or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise MayaError("Use a key without control characters or line breaks.", "credentials")
    key = value.strip()
    if not key or len(key) > 4096 or any(not 33 <= ord(ch) <= 126 for ch in key):
        raise MayaError("Use a key of 1–4,096 printable ASCII characters without spaces.", "credentials")
    return key


def credential_endpoint(provider: str, endpoint: str) -> str:
    """Fix native destinations and reject unknown providers before any credential lookup/write."""
    if provider not in PROVIDERS:
        raise MayaError("Choose a supported provider before accessing credentials.", "credentials")
    endpoint = validate_url(endpoint)
    if provider in {"gemini", "openrouter", "anthropic"} and endpoint != DEFAULT_URLS[provider]:
        raise MayaError("Native provider credentials require their fixed endpoint.", "credentials")
    return endpoint


class SecretStore:
    """Use Windows Credential Manager; optional environment credentials are read, never printed."""

    SERVICE = "MayaTheHelper"

    def __init__(self, enabled: bool = True):
        """Select Windows' native backend explicitly; refuse persistence if secure storage is absent."""
        self.backend = None
        self.enabled = enabled
        if not enabled:
            return
        if sys.platform == "win32":
            from keyring.backends.Windows import WinVaultKeyring

            self.backend = WinVaultKeyring()
        else:
            candidate = keyring.get_keyring()
            if candidate.__class__.__module__.startswith(
                ("keyring.backends.macOS", "keyring.backends.SecretService")
            ):
                self.backend = candidate

    @staticmethod
    def account(provider: str, endpoint: str) -> str:
        """Derive an endpoint-specific account name without embedding the actual key."""
        return (
            provider + ":" + hashlib.sha256(credential_endpoint(provider, endpoint).encode()).hexdigest()[:20]
        )

    def get(self, provider: str, endpoint: str) -> str:
        """Read the matching stored key or explicit provider environment variable; never log it."""
        if not self.enabled:
            return ""
        endpoint = credential_endpoint(provider, endpoint)
        if provider == "ollama":
            return ""
        if self.backend:
            try:
                value = self.backend.get_password(self.SERVICE, self.account(provider, endpoint))
                if value:
                    return validate_key(value)
            except KeyringError as exc:
                raise MayaError("Windows Credential Manager could not read this key.", "credentials") from exc
        env = {
            "gemini": "GEMINI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        if provider == "compatible":
            # A generic environment token must not silently follow an edited custom endpoint.
            bound = os.getenv("MAYA_COMPATIBLE_BASE_URL", "") or DEFAULT_URLS["compatible"]
            if credential_endpoint(provider, bound) != endpoint:
                return ""
        value = os.getenv(env.get(provider, "MAYA_COMPATIBLE_API_KEY"), "")
        return validate_key(value) if value else ""

    def save(self, provider: str, endpoint: str, key: str) -> None:
        """Store a nonempty key in OS storage; raise rather than write an insecure local file."""
        if not self.enabled:
            raise MayaError("Credential access is disabled for this verification session.", "credentials")
        endpoint = credential_endpoint(provider, endpoint)
        key = validate_key(key)
        if provider == "ollama":
            raise MayaError("Local Ollama does not use a saved API key.", "credentials")
        if not self.backend:
            raise MayaError(
                "Secure credential storage is unavailable. Set an environment variable for this session.",
                "credentials",
            )
        try:
            self.backend.set_password(self.SERVICE, self.account(provider, endpoint), key)
        except KeyringError as exc:
            raise MayaError("Windows Credential Manager could not save this key.", "credentials") from exc

    def remove(self, provider: str, endpoint: str) -> None:
        """Delete only this application's matching credential; environment values must be removed separately."""
        if not self.enabled:
            raise MayaError("Credential access is disabled for this verification session.", "credentials")
        endpoint = credential_endpoint(provider, endpoint)
        if self.backend and provider != "ollama":
            try:
                self.backend.delete_password(self.SERVICE, self.account(provider, endpoint))
            except PasswordDeleteError:
                return
            except KeyringError as exc:
                raise MayaError(
                    "Windows Credential Manager could not remove this key.", "credentials"
                ) from exc


def catalog_identity(endpoint: str, key: str) -> str:
    """Fingerprint credentials in memory; caches store only the hash, never the key."""
    return hashlib.sha256((endpoint + "\0" + key).encode()).hexdigest()
