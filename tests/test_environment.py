"""Private environment files are opt-in inputs, never fixtures containing real credentials."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
from dotenv import dotenv_values

from maya.core.types import MayaError
from maya.platform.environment import ENV_NAMES, load_environment


@pytest.fixture
def private_environment(monkeypatch):
    """Ensure tests cannot read or overwrite real provider variables."""
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    yield
    for name in ENV_NAMES:
        os.environ.pop(name, None)


def test_environment_quotes_allowlist_no_expansion_and_precedence(tmp_path, monkeypatch, private_environment):
    path = tmp_path / ".env"
    path.write_text(
        'GEMINI_API_KEY="fake-env-key"\nOPENROUTER_API_KEY=lower-priority\n'
        'ANTHROPIC_API_KEY="literal-${TOKEN}"\nQT_QPA_PLATFORM=untrusted\n'
        "MAYA_DATA_DIR='folder with spaces'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-process-key")
    monkeypatch.setenv("TOKEN", "do-not-expand")
    original_qt = os.getenv("QT_QPA_PLATFORM")
    loaded = load_environment(path)
    assert set(loaded) == {"GEMINI_API_KEY", "ANTHROPIC_API_KEY", "MAYA_DATA_DIR"}
    assert os.getenv("GEMINI_API_KEY") == "fake-env-key"
    assert os.getenv("OPENROUTER_API_KEY") == "fake-process-key"
    assert os.getenv("ANTHROPIC_API_KEY") == "literal-${TOKEN}"
    assert os.getenv("MAYA_DATA_DIR") == "folder with spaces"
    assert os.getenv("QT_QPA_PLATFORM") == original_qt


@pytest.mark.parametrize("bad", ['"private value"', '"line1\\nline2"', '"bad\x00key"'])
def test_invalid_key_does_not_partially_apply_or_echo_values(tmp_path, private_environment, bad):
    path = tmp_path / ".env"
    path.write_text("GEMINI_API_KEY=fake-valid\nANTHROPIC_API_KEY=" + bad, encoding="utf-8")
    with pytest.raises(MayaError) as error:
        load_environment(path)
    assert "private value" not in str(error.value) and "line1" not in str(error.value)
    assert not os.getenv("GEMINI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY")


def test_absent_file_does_not_search_parents(tmp_path, private_environment):
    (tmp_path / ".env").write_text("GEMINI_API_KEY=fake-parent", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    assert load_environment(child / ".env") == ()
    assert not os.getenv("GEMINI_API_KEY")
    with pytest.raises(MayaError, match="does not exist"):
        load_environment(child / ".env", required=True)


@pytest.mark.parametrize("raw", [b"x" * 65537, b"GEMINI_API_KEY=\xff"], ids=["oversized", "invalid-utf8"])
def test_environment_size_and_encoding_limits(tmp_path, private_environment, raw):
    path = tmp_path / ".env"
    path.write_bytes(raw)
    with pytest.raises(MayaError):
        load_environment(path)
    assert not os.getenv("GEMINI_API_KEY")


def test_bom_blank_template_and_unknown_values_do_not_create_variables(tmp_path, private_environment):
    path = tmp_path / ".env"
    path.write_bytes(b"\xef\xbb\xbfGEMINI_API_KEY=\nUNRELATED_SECRET=fake-ignore\n")
    assert load_environment(path) == ()
    assert "GEMINI_API_KEY" not in os.environ and "UNRELATED_SECRET" not in os.environ
    values = dotenv_values(Path(__file__).parents[1] / ".env.example")
    assert set(values) == ENV_NAMES and all(value == "" for value in values.values())


def test_smoke_and_no_credentials_skip_explicit_environment_file(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "maya",
            "--smoke-test",
            "--no-credentials",
            "--env-file",
            str(tmp_path / "absent"),
        ],
        capture_output=True,
        timeout=8,
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
