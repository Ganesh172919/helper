"""Credential destinations, input validation and transport defaults use isolated synthetic data."""

import httpx
import pytest

from maya.core.config import DEFAULT_URLS, ConfigStore, Settings
from maya.core.providers import Transport
from maya.core.safety import redact
from maya.core.types import Cancellation, MayaError
from maya.platform.environment import ENV_NAMES, load_environment
from maya.platform.secrets import SecretStore, validate_key


class Vault:
    """No real credential backend is instantiated or accessed by these tests."""

    def __init__(self):
        self.values = {}
        self.calls = []

    def get_password(self, service, account):
        self.calls.append(("get", account))
        return self.values.get(account, "")

    def set_password(self, service, account, value):
        self.calls.append(("save", account))
        self.values[account] = value

    def delete_password(self, service, account):
        self.calls.append(("remove", account))
        self.values.pop(account, None)


@pytest.fixture
def secrets(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    store = SecretStore(enabled=False)
    store.enabled = True
    store.backend = Vault()
    return store


def test_compatible_environment_key_is_bound_to_one_destination(secrets, monkeypatch):
    monkeypatch.setenv("MAYA_COMPATIBLE_API_KEY", "synthetic-env-key")
    assert secrets.get("compatible", DEFAULT_URLS["compatible"]) == "synthetic-env-key"
    assert secrets.get("compatible", "https://other.example/v1") == ""
    monkeypatch.setenv("MAYA_COMPATIBLE_BASE_URL", "https://chosen.example/v1/")
    assert secrets.get("compatible", "https://chosen.example/v1") == "synthetic-env-key"
    for endpoint in [DEFAULT_URLS["compatible"], "https://other.example/v1", "https://chosen.example/v2"]:
        assert secrets.get("compatible", endpoint) == ""
    secrets.save("compatible", "https://other.example/v1", "synthetic-stored-key")
    assert secrets.get("compatible", "https://other.example/v1") == "synthetic-stored-key"


@pytest.mark.parametrize("provider", ["gemini", "openrouter", "anthropic", "unknown"])
def test_native_or_unknown_provider_rejects_credential_redirection(secrets, provider):
    for operation in [
        lambda: secrets.get(provider, "https://other.example/v1"),
        lambda: secrets.save(provider, "https://other.example/v1", "synthetic-key"),
        lambda: secrets.remove(provider, "https://other.example/v1"),
    ]:
        with pytest.raises(MayaError):
            operation()
    assert secrets.backend.calls == []


@pytest.mark.parametrize(
    "value", ["", " ", "two words", "bad\x00key", "bad\x7fkey", "bad\r\nheader", "unicode-హలో", "x" * 4097]
)
def test_invalid_keys_are_never_saved_or_echoed(secrets, value):
    with pytest.raises(MayaError) as error:
        secrets.save("gemini", DEFAULT_URLS["gemini"], value)
    assert not secrets.backend.calls
    if len(value) > 4:
        assert value not in str(error.value)


def test_valid_key_bounds_and_disabled_removal(secrets):
    assert validate_key("  synthetic-key  ") == "synthetic-key"
    assert len(validate_key("x" * 4096)) == 4096
    secrets.enabled = False
    with pytest.raises(MayaError, match="disabled"):
        secrets.remove("gemini", DEFAULT_URLS["gemini"])
    assert secrets.backend.calls == []


def test_invalid_process_key_fails_before_provider_use(secrets, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "bad\x7fkey")
    with pytest.raises(MayaError):
        secrets.get("gemini", DEFAULT_URLS["gemini"])


@pytest.mark.parametrize("value", ["http://remote.example/v1", "https://user:synthetic@example.test/v1"])
def test_invalid_env_binding_applies_no_partial_credentials(tmp_path, monkeypatch, value):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / ".env"
    path.write_text("GEMINI_API_KEY=synthetic-key\nMAYA_COMPATIBLE_BASE_URL=" + value, encoding="utf-8")
    with pytest.raises(MayaError):
        load_environment(path)
    import os

    assert "GEMINI_API_KEY" not in os.environ and "MAYA_COMPATIBLE_BASE_URL" not in os.environ


@pytest.mark.parametrize("field", ["display_name", "language", "response_style"])
def test_preferences_cannot_persist_recognizable_secrets(tmp_path, field):
    store = ConfigStore(tmp_path)
    original = Settings()
    store.save(original)
    candidate = Settings()
    setattr(candidate, field, 'A preference with "api_key": "synthetic private value"')
    with pytest.raises(MayaError):
        store.save(candidate)
    assert store.load() == original


@pytest.mark.parametrize(
    "source,value",
    [
        ('{"api_key": "synthetic secret with spaces", "task": "explain"}', "synthetic secret with spaces"),
        ("password='synthetic multi word passphrase'", "synthetic multi word passphrase"),
        ('access_token="synthetic\\"quoted value"', 'synthetic\\"quoted value'),
        ('{"password":"synthetic-value"}', "synthetic-value"),
    ],
)
def test_quoted_assignment_and_json_secret_redaction_is_complete(source, value):
    clean, changed = redact(source)
    assert changed and value not in clean and "synthetic" not in clean


def test_transport_ignores_implicit_proxy_ca_and_redirects(monkeypatch):
    for name in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
        monkeypatch.setenv(name, "not-a-valid-proxy")
    monkeypatch.setenv("SSL_CERT_FILE", "nonexistent-synthetic-ca.pem")
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer synthetic-key"
        return httpx.Response(302, headers={"location": "https://other.example/collect"})

    transport = Transport(
        "https://chosen.example/v1", {"Authorization": "Bearer synthetic-key"}, httpx.MockTransport(handler)
    )
    with pytest.raises(MayaError):
        transport.get("/models", Cancellation())
    assert len(calls) == 1 and calls[0].url.host == "chosen.example"
