# Sharing a fresh clone

The repository contains neutral application defaults. A new installation has an empty display
name, no custom profiles, no approved memories and Screen OFF. It does not contain another user's
keys or chat history. Existing installations retain their own local data outside the checkout.

## Start locally

```powershell
git clone <repository-url> maya-the-helper
cd maya-the-helper
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m maya
```

Use Settings → Providers to save your own key in Windows Credential Manager. Gemini is the
default; model IDs come from discovery. For a file-based alternative, copy `.env.example` to
`.env` and edit it locally. The template has empty values. See [SETUP](SETUP.md) for variable
precedence, `--env-file`, and isolated verification flags.

## What belongs in Git

Share source, tests, scripts, documentation, `pyproject.toml`, `requirements.txt`, `LICENSE`,
`NOTICE` and `.env.example`. The ignore rules exclude `.env` variants, databases, logs, local
data directories, generated previews, build products and virtual environments. An ignore rule
does not remove a file that was already committed.

Review the candidate file list before staging:

```powershell
git status --short --untracked-files=all
git ls-files --cached --others --exclude-standard
git check-ignore .env artifacts .venv
git add --dry-run .
```

Do not copy `%LOCALAPPDATA%\MayaHelper` or Windows Credential Manager entries into the project.
That data folder contains plaintext history and non-secret preferences. `MAYA_DATA_DIR` can
point elsewhere, so check that location too. Use Settings → Memory → Forget all to clear approved
memories; it deliberately retains chats and keys. Use History to delete chats you no longer need.
Old backups or previously submitted cloud requests are unaffected by local deletion.

## Existing Git history and identity

Removing details from current files does not change older commits. Check previous README
versions, author names/emails, commit messages and remotes before publishing. Configure a
repository-specific Git identity for future commits if you want a public alias and a GitHub
no-reply email. Confirm the exact no-reply address in your own GitHub settings. Do not share a
history containing leaked keys; revoke exposed keys even after removing the affected files.

This release does not rewrite Git history, create commits or push to a remote. A fresh public
repository can start from the reviewed source if you do not intend to publish the existing history.

## License and redistribution

Maya's original source uses [Apache License 2.0](../LICENSE), with project notices in
[NOTICE](../NOTICE). Dependencies retain their own licenses. In particular,
[PyQt is GPLv3/commercial](https://www.riverbankcomputing.com/software/pyqt/intro), while
[Qt has separate open-source obligations](https://www.qt.io/development/open-source-lgpl-obligations).
Apache 2.0 on Maya's source does not relicense those components.
Review the official dependency terms before shipping a bundled executable. A Python wheel and
a PyInstaller executable have different contents; test and document each artifact separately.

## Verify the release

```powershell
& scripts/run_tests.ps1
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir artifacts/wheels
.\.venv\Scripts\python.exe scripts/check_sharing.py
```

The read-only sharing check reviews the working Git candidates and distinct staged text versions.
It flags force-added private files, filled environment templates, personal home-directory paths
and recognizable provider/token/private-key shapes. It prints file names and issue types, never
matching values. Binary, large, linked and unreadable files require separate review. An older
sensitive staged version still fails even after you fix the working copy. No files, index entries,
commits or credentials are changed. Run it again after staging your intended changes.

This is a bounded project check, not a complete secret scanner. It does not recognize every name,
email, password or biography, or inspect old commits. Review those separately before publishing.

The suite uses temporary data, disabled credential access, mocked providers and local loopback
servers. It verifies parsing, routing, privacy defaults, cancellation, SQLite and Qt behavior.
Real-key cloud generation and actual screen-recorder compatibility are separate checks; follow
[TESTING](TESTING.md) and [SCREEN_SHARING](SCREEN_SHARING.md).

Keep generated previews and test artifacts local. Never include filled `.env` files, databases,
raw provider responses, screenshots with personal content or credential exports in a GitHub issue.
