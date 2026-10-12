# Privacy and security

Maya runs locally and directly calls the provider you select. There is no Maya backend or
telemetry. Cloud requests may contain the typed question, bounded conversation, approved
memories and a reviewed screenshot. The provider's own logging/retention policies apply.
Use local Ollama when you need the selected model request to remain on localhost.
Keep **Smart routing → Use Gemini** OFF for a wholly local Ollama workflow: enabling it adds
a separate Google classification request, even if the answer provider is local.

## Credentials

Windows Credential Manager holds stored keys. Account identifiers include provider and endpoint
hashes, so a key stored for one compatible host is not silently reused for another host. Native
Gemini/OpenRouter/Anthropic endpoints are fixed. Remote compatible URLs require HTTPS and cannot
contain embedded credentials, query strings or fragments. Redirects are not followed. Keys use
headers, never query strings. The UI never pre-fills stored secrets; logging excludes keys,
prompts, raw provider errors and screenshots. Failed OS credential storage never silently writes
a plaintext key file.

Credentials are validated before storage and use: 1–4,096 printable ASCII characters, with no
embedded whitespace or control characters. Native credential access independently requires the
fixed provider URL. The key editor only reveals newly typed input on an explicit Show action;
focus loss, tab/window hiding, provider changes or a 30-second timeout masks it again. Cancel
clears unsaved input. This does not promise forensic erasure of process memory.

Provider HTTP clients use `trust_env=False`: shell proxy and certificate-override variables do
not implicitly affect requests. TLS verification stays enabled and redirects remain disabled.
Explicit corporate proxy/custom-CA configuration is not implemented; do not bypass network policy
to work around that limitation. See the official [HTTPX environment-variable documentation](https://www.python-httpx.org/environment_variables/).

Environment credentials are an explicit alternative. A normal launch loads allowlisted values
from the current folder's optional `.env`, or the exact `--env-file` path; existing process values
are preserved. There is no ancestor search, variable expansion or arbitrary environment injection.
The empty `.env.example` is versioned; `.env` and its variants are Git-ignored. A user-created
`.env` is plaintext, so OS credential storage is preferable on shared machines. Verification flags
skip `.env` and disable all credential reads. Removing a saved key does not unset an environment
key. A shared Windows account can access that account's
Credential Manager; this is not an application sandbox or an extra authentication boundary.

`MAYA_COMPATIBLE_API_KEY` is bound to `MAYA_COMPATIBLE_BASE_URL`, including its API path.
If the base variable is empty/absent, the key is usable only at the default OpenAI compatible URL.
Changing the selected endpoint cannot reuse that environment key. For another host, explicitly
set the matching base URL or save a separate OS credential for it. Stored OS credentials retain
priority. Unknown providers and invalid native destinations are rejected before backend access.

## Screenshots

Screen defaults OFF. No background screenshot monitor or continuous watch mode is implemented.
Only Capture/shortcut actions acquire pixels. Every new capture passes through review. Black-box
redaction changes the actual pending image, not just its displayed overlay. Screenshots stay in
memory and are absent from SQLite and exported Markdown. Turning Screen OFF clears pending and
reuse state, but cannot recall an already-submitted request. Providers with unknown image support
need a user's verified override or a different model.

Windows capture exclusion is best-effort. A lifecycle guard applies it to Maya's own windows,
new dialogs, menus and replacement native handles. More → Screen-share privacy distinguishes
confirmed native affinity, an older monitor-only fallback, failed requests and unavailable read-back.
API confirmation is not a guarantee for every recorder. Own windows are also hidden for Maya's own captures.
See [SCREEN_SHARING](SCREEN_SHARING.md) for the supported boundary and compatibility plan.
Protected applications can yield blank frames; Maya reports that and does not bypass protection.
Screenshot redaction is manual; there is no OCR-based secret detection. Text redaction catches
recognizable key/token/password patterns but cannot identify every secret. Review context yourself.
Quoted assignments and JSON credential fields are included, with entire quoted values redacted.
Recognizable secrets are also rejected in name/language/style preferences and task profiles.

## Local data and untrusted content

**Review request context** is local and credential-free until explicit approval. It shares the
prepared answer Request with submission rather than rebuilding an approved body afterward. Relevant
draft/model/profile/memory/history/image/settings changes invalidate the review. The Gemini-enabled
workflow separately approves classification and the final answer; cancellation does not start an
answer or create a saved turn. This opt-in workflow is not a blanket approval of future requests.

With redaction enabled, raw memory/preferences are sanitized before JSON serialization, and included
history is sanitized in the outbound copy. Saved originals remain local and unchanged. Review refuses
recognizable raw credentials when redaction is disabled. It never displays authorization headers or
fetches saved keys for inspection. Screenshot text is not automatically scanned for secrets.

History/memories are plaintext local SQLite. Disable saving new history in Preferences, delete
selected chats through History, and forget selected memories or use the confirmed Forget all action
through Memory. Forget all uses SQLite secure deletion for current rows; it retains chats and keys.
New installs contain no profile or memory seeds. Normal deletion
does not promise forensic erasure of disk backups/free pages. Backups need the same care as other
personal files. Screenshot memory can remain in RAM/swap until reclaimed by the OS.

Window titles help local profile selection; opt-in Gemini classification also sends a redacted,
bounded title and question excerpt with profile descriptions. It sends no screenshot, history or
memory to the classifier. Invalid IDs/JSON, non-finite scores, extra/duplicate fields and incomplete
results fall back to local routing. Confidence is a model estimate, not a measured correctness guarantee.

The floating clipboard viewer starts with Watch OFF. Only enabling Watch while visible subscribes
to clipboard text updates. Hide/close/pause disables it and clears preview text. There is no clipboard
history or automatic provider request; **Use in chat** explicitly copies the reviewed preview into a
draft. Recognizable-secret masking has the same limits as typed redaction. Plain text display prevents
clipboard HTML from fetching resources. Preview data can remain in RAM/swap until reclaimed.

Captured/pasted content and memory
are untrusted data in the system prompt; embedded commands are not granted authority. Prompt
instructions reduce injection risk but cannot guarantee a model will always follow them. The
app has no command runner, filesystem editing agent or OS click tool, so model output cannot
perform those actions. A narrow local refusal rule rejects obvious malware/credential-theft
requests; broader safety depends on the provider/model and system instructions. Do not treat
the local classifier as a comprehensive moderation engine.

Markdown cannot fetch embedded local/remote resources. Only explicitly clicked HTTP(S) links
open externally; no file/script/application schemes are opened. The app never auto-pastes.
Dynamic tooltip markup is escaped so it displays literally rather than loading embedded resources.
Clicked web links additionally require a valid host and a bounded URL. Unknown-model image-input
confirmation resets when the chosen model or manual ID changes; a previous checkbox is not reused.
SQLite queries are parameterized. Event/image/request sizes and retry counts are bounded.

No live exploit resistance, penetration test, privacy compliance certification, medical safety,
or universal anti-recording guarantee is claimed. See TESTING and ENGINEERING_REPORT for evidence.
