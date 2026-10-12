# Setup

The tested environment is Windows, CPython 3.13.7, PyQt5 5.15.11, Qt 5.15.2, HTTPX 0.28.1,
Pillow 12.3.0, MSS 10.2.0, keyring 25.7.0 and python-dotenv 1.2.4. Runtime package versions were checked on
10 October 2026. PyQt5's Windows Qt runtime is older than Qt6; it follows the Qt5 fallback
specified in the build brief. Do not silently switch GUI bindings or mix Qt5 and Qt6 objects.

```powershell
cd C:\path\to\maya-the-helper
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m maya
```

The installed `maya-helper` GUI entry point and `scripts/run_dev.ps1` run the same application.
Using the explicit environment Python avoids activation-policy problems. Internet access is
needed for dependency installation and cloud AI calls; already-installed local Ollama can work
without internet. No Maya account, server process, database server or administrator privileges
are needed for ordinary use.

## Keys and models

1. Open Settings → Providers.
2. Choose Google Gemini (default) or OpenRouter.
3. Paste your own key into the masked field. Blank preserves the existing credential.
4. Save & refresh models. Authentication errors appear in the chat notice.
5. Open Choose model. Search All models or OpenRouter's Free models tab.
6. Ask a short text question. Enable Screen only when you want screenshot context.

Compatible endpoints accept a base URL ending at the API root, for example
`https://api.openai.com/v1` or `http://127.0.0.1:1234/v1`. Choose a manual model ID only
when discovery is unavailable; verify image capability before enabling the override. Local
Ollama defaults to `http://127.0.0.1:11434` and lists already-installed models. Manual selections
and explicit image-capability confirmations are restored only for their matching endpoint.

Windows Credential Manager is preferred. An optional private file is also supported:

```powershell
Copy-Item .env.example .env
```

Edit `.env` locally with your own `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY` or
`MAYA_COMPATIBLE_API_KEY`. Normal launches read only `.env` in the current working folder;
`--env-file PATH` chooses another explicit file. There is no parent-directory search. Only those
four key names, `MAYA_COMPATIBLE_BASE_URL` and `MAYA_DATA_DIR` are allowed, the file is bounded to 64 KiB, and variable expansion
is disabled. Existing process variables take priority over file values; OS-stored keys take
priority over environment keys. Empty values are ignored. The file is plaintext and Git-ignored;
only the empty `.env.example` belongs in Git. Removing a stored key does not remove an environment
key. Do not paste real keys into source files, docs, Git or chat transcripts.

For a custom compatible endpoint, set `MAYA_COMPATIBLE_BASE_URL` to the same API base URL you
select in Settings. Without it, the compatible environment key is bound only to the default
OpenAI endpoint. A changed host or API path needs its own explicit binding or stored OS key.
HTTP proxy and custom-CA environment variables are ignored by provider clients; explicit corporate
proxy/certificate configuration is currently unsupported. TLS verification remains enabled.

For verification without reading saved or environment keys, use `python -m maya --no-credentials`.
`--smoke-test` also disables credential access and uses disposable data. Both flags skip `.env`
loading, including its data-folder override. Normal launches use
your configured credentials. A separate `MAYA_DATA_DIR` alone does not isolate OS credentials.

Safe settings example (an excerpt; missing fields receive neutral defaults):

```json
{
  "provider": "gemini",
  "screen_enabled": false,
  "remember_enabled": true,
  "display_name": "",
  "response_style": "Clear, practical explanations with examples",
  "window_geometry": [],
  "custom_profiles": {},
  "model_preferences": {}
}
```

API keys belong in Settings → Providers, never this JSON. Fresh installs do not contain
another user’s private data. If a virtual environment was created with `uv venv` without pip,
run `.\.venv\Scripts\python.exe -m ensurepip --upgrade` before using the pip commands above.

## Data and backup

Default directory: `%LOCALAPPDATA%\MayaHelper`.

- `settings.json`: non-secret settings; atomic replacement.
- `history.sqlite3` plus WAL/SHM: plaintext local text history, approved memories, feedback, catalog.
- `diagnostics.log`: bounded safe exception types and stack locations.
- `instance.lock`: owned while Maya runs.

To use another writable data folder, set `MAYA_DATA_DIR` before launch. To back up, Quit Maya
first, then copy the data folder using normal file operations. Credentials remain in Windows
Credential Manager and are not included in a database backup.

## Packaging later

Python development execution is the verified delivery. When ready, install the optional build
tools and use an onedir build first:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --onedir --name MayaHelper --paths src --hidden-import keyring.backends.Windows run_maya.py
```

Test `dist\MayaHelper\MayaHelper.exe` separately: startup, credential read/write, all adapters,
capture, tray, shortcuts, second launch and shutdown. This executable has not been built or
validated in this session. PyQt is GPLv3/commercial; Qt has separate LGPL/GPL/commercial terms.
Review bundled dependency notices and terms before distribution. Do not infer executable
packaging success from Python or wheel success.
