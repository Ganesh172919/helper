"""The sharing audit checks real Git candidate lists without echoing private file contents."""

from pathlib import Path
import subprocess
import sys

import pytest

from scripts.check_sharing import audit_repository


@pytest.fixture
def repository(tmp_path):
    """Use an isolated checkout without commits, configured remotes, hooks or personal Git identity."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / ".gitignore").write_text(
        ".env\n.env.*\n!.env.example\nartifacts/\n*.db*\n*.log\n.secrets/\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("A neutral project.\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("GEMINI_API_KEY=\n", encoding="utf-8")
    return tmp_path


def test_clean_candidates_exclude_private_local_files(repository):
    (repository / ".env").write_text("GEMINI_API_KEY=private-synthetic-value", encoding="utf-8")
    (repository / "history.db").write_bytes(b"private database")
    (repository / "artifacts").mkdir()
    (repository / "artifacts" / "private.txt").write_text("private preview", encoding="utf-8")
    count, findings = audit_repository(repository)
    assert count == 3 and not findings


@pytest.mark.parametrize("name", [".env", ".env.production", "history.db-wal", "credentials.json"])
def test_forced_private_files_are_rejected_without_reading_them(repository, name):
    path = repository / name
    path.write_text("private-synthetic-value", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "-f", name], check=True, capture_output=True)
    _, findings = audit_repository(repository)
    assert len(findings) == 1 and findings[0].path == name and "private file" in findings[0].reason
    assert "private-synthetic-value" not in str(findings)


@pytest.mark.parametrize("value", ["synthetic-private", '"synthetic-private"', '"${PRIVATE_KEY}"'])
def test_filled_template_fails_without_echoing_values(repository, value):
    (repository / ".env.example").write_text("GEMINI_API_KEY=" + value, encoding="utf-8")
    _, findings = audit_repository(repository)
    assert len(findings) == 1 and "template" in findings[0].reason and value not in str(findings)


def test_home_paths_and_key_shapes_are_reported_without_values(repository):
    # Construct synthetic sensitive-looking data so these regression fixtures are shareable too.
    home = "C:" + chr(92) + "Users" + chr(92) + "synthetic" + chr(92) + "draft.txt"
    secret = "AIza" + "a" * 35
    (repository / "README.md").write_text(home + "\n" + secret, encoding="utf-8")
    _, findings = audit_repository(repository)
    assert {item.reason for item in findings} == {"personal home-directory path", "credential-shaped content"}
    assert home not in str(findings) and secret not in str(findings)


def test_scroll_navigation_words_are_not_personal_paths(repository):
    (repository / "README.md").write_text("Wheel/arrows/page/home/end; Page/Home/End.", encoding="utf-8")
    assert not audit_repository(repository)[1]


@pytest.mark.parametrize("name", [".env.example", "README.md"])
def test_repaired_working_file_cannot_hide_private_staged_content(repository, name):
    path = repository / name
    value = "sk-" + "b" * 32
    path.write_text("GEMINI_API_KEY=" + value, encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", name], check=True, capture_output=True)
    path.write_text("GEMINI_API_KEY=\n" if name.endswith("example") else "Neutral text", encoding="utf-8")
    _, findings = audit_repository(repository)
    assert findings and all(item.path == "index 0: " + name for item in findings)
    assert "credential-shaped content" in {item.reason for item in findings} and value not in str(findings)


def test_deleted_working_file_still_checks_staged_content(repository):
    path = repository / "README.md"
    value = "github_pat_" + "b" * 40
    path.write_text(value, encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", path.name], check=True, capture_output=True)
    # Simulate a working deletion without filesystem deletion or publishing the index.
    path.rename(repository / "README.private-backup")
    (repository / ".gitignore").write_text("README.private-backup\n", encoding="utf-8")
    _, findings = audit_repository(repository)
    assert any(item.path == "index 0: README.md" and "credential-shaped" in item.reason for item in findings)
    assert value not in str(findings)


@pytest.mark.parametrize("raw", [b"x" * (1024 * 1024 + 1), b"\xff\xfe"], ids=["large", "binary"])
def test_unreviewable_files_require_manual_review(repository, raw):
    (repository / "extra.txt").write_bytes(raw)
    _, findings = audit_repository(repository)
    assert len(findings) == 1 and "separate review" in findings[0].reason


def test_audit_cli_exit_codes_and_safe_diagnostics(repository):
    script = Path(__file__).parents[1] / "scripts" / "check_sharing.py"

    def run(folder):
        return subprocess.run(
            [sys.executable, str(script), "--repo", str(folder)], capture_output=True, text=True, timeout=15
        )

    assert run(repository).returncode == 0
    value = "synthetic-value-never-print"
    (repository / ".env.example").write_text("GEMINI_API_KEY=" + value, encoding="utf-8")
    result = run(repository)
    assert result.returncode == 1 and value not in result.stdout + result.stderr
    assert run(repository / "not-a-checkout").returncode == 2
