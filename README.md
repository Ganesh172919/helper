# Maya the Helper

Maya brings explanations into the desktop work you are already doing. Ask about a coding
agent's command, an Excel formula, an unfamiliar dialog, or a paragraph in a PDF. Use ordinary
chat or attach a screenshot you have reviewed. Responses stream into a normal window or a
compact panel beside a floating flower icon.

This Python implementation adapts a Win32 overlay reference into a native desktop application.
Every new installation starts with an empty profile, empty memories and Screen OFF.

## Run locally

Windows 10/11, Python 3.11–3.14; verified here with **Python 3.13.7 on Windows**.

```powershell
git clone <repository-url> maya-the-helper
cd maya-the-helper
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m maya
```

After installation, launch from the repository folder:

```powershell
.\.venv\Scripts\python.exe -m maya
```

Open **Settings → Providers**, choose Gemini or OpenRouter, paste your key into the
masked field, and press **Save & refresh models**. Choose a model in the chat toolbar. Keys go
to Windows Credential Manager, never the repository. Gemini is the default provider. Discovered
Gemini 3.8 Flash and 3.5 Flash-Lite receive priority; unavailable models are never fabricated.

## What is implemented

- A 480 × 560 main window, 360 × 440 floating panel, collapsible navigation, topmost orb and tray.
- A glowing sculpted flower with a 3D appearance, warm paper/jade styling and visible-only active animation.
- A grouped composer, keyboard focus border, consistent line icons and a rounded floating reader.
- Clear model setup guidance, quieter message actions and expandable screen controls in both modes.
- Three-step provider setup, temporary typed-key reveal, model-search empty states and reduced motion.
- Persistent main-window Pin, adjustable floating translucency and a draggable quick-panel header.
- Configurable shortcuts, remembered placement, compact-size reset and a single app instance.
- Streaming Gemini/OpenRouter, plus explicit OpenAI-compatible, Anthropic and local Ollama adapters.
- Dynamic searchable catalogs, separate OpenRouter free search, vision filter, and context badges.
- Explicit monitor/all-monitor/visible-window/region capture, review, black-box redaction and image bounds.
- Screen ON/OFF, shared drafts, Stop, Regenerate, Continue, Edit, Copy, code-block copy, Markdown export.
- Search titles/message text, rename/delete conversations, and export the visible chat to Markdown.
- SQLite approved memories with scope editing, an empty-state summary and confirmed Forget all.
- 34 built-in skills, a searchable instruction library and saved custom profiles.
- Optional Gemini skill classification, instruction preview, local fallback and draft-preserving Stop.
- Local outgoing-context review, separate Gemini/final-answer approvals and stale-review rejection.
- Opt-in floating clipboard viewer with reference scroll keys, translucency and explicit Use in chat.
- Native capture exclusion for Maya windows, dialogs and menus, with a readable privacy status.
- Endpoint-scoped manual model choices and verified image-capability preferences survive restart.
- Masked OS-backed keys, bounded requests/retries, safe error messages and partial-response preservation.
- Endpoint-bound environment keys, credential validation and escaped dynamic tooltip text.

There is no account/login flow, telemetry, Maya backend, Docker, Kubernetes, CI/CD, Rust code,
or automatic command execution. The assistant helps you understand; you decide what to do.

## Shortcuts

| Shortcut | Action |
| --- | --- |
| Alt+Shift+N | Show/hide current mode |
| Alt+Shift+S | Capture when Screen is ON |
| Alt+Shift+C | Toggle Screen ON/OFF |
| Alt+Shift+Up / Down | Scroll clipboard viewer when open, otherwise answer |
| Enter / Shift+Enter | Send / newline |
| Esc in quick panel | Collapse |

Change the first three in Settings. Conflicts are reported. Closing the normal window keeps
Maya in the tray; use **Quit Maya** to stop workers and exit.

## Verification and limits

**268 automated tests pass**, covering protocol parsing, API wire formats, Gemini routing/fallbacks, clipboard controls, SQLite recovery, privacy defaults,
real Qt state transitions, and real loopback HTTP cancellation. A live public OpenRouter
catalog and physical screen capture have been exercised. Cloud generation with real keys,
installed local models, mixed-DPI hardware and packaged distribution require separate validation.
This is a working local development release; see the [engineering report](docs/ENGINEERING_REPORT.md)
for evidence and limitations. No benchmark or universal application compatibility is claimed.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m maya --smoke-test
```

## Read the project

- [Setup and launch](docs/SETUP.md)
- [User guide](docs/USER_GUIDE.md)
- [Architecture, mind map and request sequence](docs/ARCHITECTURE.md)
- [Gemini smart routing and system instructions](docs/SMART_ROUTING.md)
- [Provider protocols and official references](docs/PROVIDERS.md)
- [Privacy and security](docs/SECURITY.md)
- [Testing and manual checklist](docs/TESTING.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Reference audit](docs/REFERENCE_ANALYSIS.md)
- [Design decisions and roadmap](docs/DECISIONS.md)
- [Release validation roadmap](docs/DEVELOPMENT_ROADMAP.md)
- [Next-version improvement plan](docs/NEXT_VERSION_IMPROVEMENTS.md)
- [Future Rust boundaries and contracts](docs/ROADMAP_RUST.md)
- [Engineering report and requirement coverage](docs/ENGINEERING_REPORT.md)
- [Learn to maintain it](docs/BUILD_IT_YOURSELF.md)

Runtime data lives in `%LOCALAPPDATA%\MayaHelper`, outside the repository. `MAYA_DATA_DIR` can
override it. No personal profile, memory seed, history database or credentials are bundled.
Use Settings → Memory to add preferences or Forget all to start over.

Optional environment setup: copy [.env.example](.env.example) to `.env`, then enter your own keys.
Only `.env.example` belongs in Git. Maya loads allowlisted values from this folder’s `.env` without
overriding existing process variables. OS-stored credentials have priority. Use `--env-file PATH`
for another explicit file; verification flags skip `.env` entirely.

Before publishing, run `scripts/check_sharing.py` with the project's Python environment. It reviews
working files and staged versions without changing Git or printing matching sensitive values.
See the sharing guide for its scope and the separate review of history and personal facts.

See [screen-sharing behavior and upgrade plan](docs/SCREEN_SHARING.md) and
[sharing a fresh clone](docs/SHARING.md) before publishing or recording.

Maya's source is licensed under [Apache 2.0](LICENSE). Third-party dependencies retain their
own licenses; see [NOTICE](NOTICE) and the sharing guide before redistributing a bundled app.
