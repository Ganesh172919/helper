"""Read-only review of the working files Git would offer for sharing.

This catches common private-file mistakes; it is not a complete secret scanner and does not
inspect past commits, credential storage or local application data.
Only relative file names and issue types are printed, never matching text or key values.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import subprocess


MAX_TEXT_BYTES = 1024 * 1024
PRIVATE_DIRS = {
    ".venv",
    ".secrets",
    ".maya-data",
    "maya-data",
    "local-data",
    "artifacts",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}
# Credential-shaped patterns intentionally exclude generic password examples in regression tests.
SECRET_PATTERNS = (
    r"\bAIza[\w-]{30,}\b",
    r"\bsk-(?:or-v1-)?[\w-]{16,}\b",
    r"\b(?:ghp_|github_pat_)[\w]{20,}\b",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
)
HOME_PATH = re.compile(r"(?i)(?<![\w/\\])(?:[a-z]:[\\/]Users[\\/]|/(?:home|Users)/)[^\s\\/\"'<>]+")


@dataclass(frozen=True)
class Finding:
    """An issue reported without including sensitive content."""

    path: str
    reason: str


def git_output(root: Path, *arguments: str) -> bytes:
    """Use literal arguments and bounded Git calls; raw diagnostics may contain private paths."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments], capture_output=True, timeout=15, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Git is unavailable or did not finish; no sharing audit was completed.") from exc
    if result.returncode:
        raise RuntimeError("Git could not list this checkout; no sharing audit was completed.")
    return result.stdout


def private_path(path: PurePosixPath) -> bool:
    """Reject private files even when force-added; ignored untracked files never enter the list."""
    name = path.name.casefold()
    is_template = name.startswith(".env.") and name.endswith(".example")
    return (
        bool(PRIVATE_DIRS.intersection(part.casefold() for part in path.parts[:-1]))
        or name == ".env"
        or (name.startswith(".env.") and not is_template)
        or name == "settings.json"
        or (name.startswith("credentials") and name.endswith(".json"))
        or bool(re.search(r"\.(?:db|sqlite|sqlite3)(?:[-.].*)?$|\.log$|\.py[cod]$", name))
    )


def empty_template(text: str) -> bool:
    """Require templates to contain only comments and empty assignments, including quoted empties."""
    return all(
        not line.strip()
        or line.lstrip().startswith("#")
        or re.fullmatch(r"\s*[A-Z][A-Z0-9_]*\s*=\s*(?:\"\"|'')?\s*(?:#.*)?", line)
        for line in text.splitlines()
    )


def inspect_text(name: str, text: str) -> list[Finding]:
    """Apply the same rules to current and staged versions, keeping the matching values private."""
    issues = []
    if PurePosixPath(name).name.casefold().startswith(".env.") and not empty_template(text):
        issues.append(Finding(name, "environment template has a value or invalid assignment"))
    if HOME_PATH.search(text):
        issues.append(Finding(name, "personal home-directory path"))
    if any(re.search(pattern, text) for pattern in SECRET_PATTERNS):
        issues.append(Finding(name, "credential-shaped content"))
    return issues


def audit_repository(root: Path) -> tuple[int, list[Finding]]:
    """Inspect the current candidate files without reading excluded private data or changing Git."""
    root = root.resolve()
    actual = Path(git_output(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if actual != root:
        raise RuntimeError("Choose the repository root so the complete candidate list is reviewed.")
    names = sorted(
        set(
            git_output(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
            .decode("utf-8")
            .split("\0")
        )
        - {""}
    )
    findings = []
    reviewed = 0
    working = {}
    for name in names:
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or private_path(relative):
            findings.append(Finding(name, "private file is in the Git candidate list"))
            continue
        file = root.joinpath(*relative.parts)
        # Never follow symlinks (including linked parent directories) into somebody's private files.
        if any(parent.is_symlink() for parent in (file, *file.parents) if parent != root):
            findings.append(Finding(name, "linked file requires a separate review"))
            continue
        if not file.exists():  # A tracked deletion will disappear once it is staged.
            continue
        try:
            if not file.is_file() or file.stat().st_size > MAX_TEXT_BYTES:
                findings.append(Finding(name, "large or non-file content requires a separate review"))
                continue
            with file.open("rb") as stream:
                raw = stream.read(MAX_TEXT_BYTES + 1)
            if len(raw) > MAX_TEXT_BYTES:
                findings.append(Finding(name, "large content requires a separate review"))
                continue
            text = raw.decode("utf-8-sig")
        except (OSError, UnicodeError):
            findings.append(Finding(name, "unreadable or binary content requires a separate review"))
            continue
        reviewed += 1
        working[name] = raw
        findings.extend(inspect_text(name, text))
    # A repaired working copy may still have a filled template/key staged for the next commit.
    # Read bounded blobs by object ID, never interpret a path as a Git revision or shell command.
    entries = git_output(root, "ls-files", "--stage", "-z").decode("utf-8").split("\0")
    for entry in filter(None, entries):
        metadata, name = entry.split("\t", 1)
        mode, object_id, stage = metadata.split()
        if private_path(PurePosixPath(name)):
            continue  # Already reported by the candidate-path check without reading its contents.
        label = f"index {stage}: {name}"
        if mode not in {"100644", "100755"}:
            findings.append(Finding(label, "linked or submodule content requires a separate review"))
            continue
        if int(git_output(root, "cat-file", "-s", object_id)) > MAX_TEXT_BYTES:
            findings.append(Finding(label, "large content requires a separate review"))
            continue
        raw = git_output(root, "cat-file", "blob", object_id)
        if raw == working.get(name):
            continue
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            findings.append(Finding(label, "binary content requires a separate review"))
            continue
        reviewed += 1
        findings.extend(Finding(label, issue.reason) for issue in inspect_text(name, text))
    return reviewed, findings


def main() -> int:
    """Exit nonzero for findings or an incomplete audit; never print raw exception diagnostics."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    options = parser.parse_args()
    try:
        count, findings = audit_repository(options.repo)
    except (RuntimeError, UnicodeError) as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else "Git file names could not be decoded.")
        return 2
    for finding in findings:
        # repr keeps unusual/newline file names on one line; file contents are never printed.
        print(f"{finding.path!r}: {finding.reason}")
    print(f"Reviewed {count} text file versions (working tree and Git index); {len(findings)} issue(s).")
    print("Review history and personal facts separately before publishing.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
