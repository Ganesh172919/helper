# Maya the Helper — engineering report

Verification date: **12 October 2026**. Delivery: locally installed Python development release.
The implementation has AI-assisted changes. Local test evidence is reported separately from
real provider-account and hardware validation; no benchmark or adoption claim is made.

## Outcome

Maya provides normal and floating desktop chat with genuine incremental provider adapters,
explicit reviewed screenshots, dynamic model selection, task instructions and approved local
memory. The latest compact layout starts at 480 × 560, with a 360 × 440 quick panel and hidden
navigation. It fits smaller work areas; minimum-size regression checks include image attachments,
code/feedback menus and scrolling navigation. The Downloads reference is preserved unchanged.
The main header now has persistent Pin and a sculpted Maya icon with a 3D appearance. The quick
panel supports title dragging and adjustable translucency. Real native font checks guard against
layout-driven window growth during streaming; Read details and tooltips expose complete notices.

The UI refinement adds warm paper surfaces, an editorial welcome title, consistent line icons,
a grouped drafting/action well and quieter message controls. A beveled jade base, ceramic petal
faces and a bounded gold halo give the Maya mark depth. Glow breathes only during visible work;
idle and hidden timers remain stopped. Screen drawers start collapsed in both modes, empty cloud
catalogs offer direct setup, and manual/local model paths stay available. Rounded floating corners
remain transparent while the header has an opaque backing. Long notices open complete plain text;
statuses elide without losing their accessible description.
The settings header now shares the flower mark. Instruction search previews 34 skills locally;
the Memory tab shows an empty state/count and disables unavailable deletion actions. Three added
profiles cover networking, assistive tools and forms, with shared grounding rules retained.

The 12 October refinement adds a three-step provider setup, current-endpoint credential status,
temporary typed-key reveal and masking, model match/empty states and independent filter reset.
Image confirmation resets on model changes. Send waits for a question or screen-gated attachment.
Reduced motion is persisted and stops decorative activity timers while retaining text status.
Environment keys now bind to one compatible base URL; native credential access rejects redirected
destinations. Key validation, quoted-secret redaction, escaped tooltips and direct verified-TLS
transport defaults strengthen the existing boundaries. These are regression-tested improvements,
not a penetration-test or universal model-safety claim.

Optional outgoing-context review now shows the trimmed answer history, instructions, memories and
approved image without reading keys or making a request. Gemini-enabled review has separate routing
and final-answer approval; the approved Request is reused for generation. Relevant-input changes
invalidate consent. Raw preferences are sanitized before JSON quoting, included history is sanitized
in the outgoing copy, and Enter while reading cannot implicitly approve a request. Native capture
affinity is also verified for the new review dialog.

Local verification uses synthetic replies and temporary data. Real cloud generation remains
unverified. No test suite can establish every possible edge case.

## Environment and commands

Windows, CPython 3.13.7; PyQt5 5.15.11 / Qt 5.15.2, HTTPX 0.28.1, Pillow 12.3.0, MSS 10.2.0,
keyring 25.7.0, python-dotenv 1.2.4, pytest 9.1.1 and ruff 0.17.0. Runtime versions are pinned in pyproject.toml and
requirements.txt. Pip was added to the existing unseeded virtual environment with ensurepip.

| Check | Observed result |
| --- | --- |
| `python -m pytest -q` | **268 passed**; real Qt/QThreads, temporary SQLite, mocked HTTP wire formats and real loopback sockets/processes. |
| `ruff check src tests scripts/check_sharing.py` | Passed. |
| `ruff format --check src tests run_maya.py scripts/check_sharing.py` | Passed. |
| `python -m compileall -q src` | Passed. |
| `python -m pip check` | No broken requirements. |
| `python -m maya --smoke-test` | Real disposable native Qt startup/shutdown, exit 0; saved/environment credential access disabled. |
| Public OpenRouter catalog through the real adapter, 10 October | 458 models, 19 free, 296 vision-capable at that snapshot; no key, question, memory or screenshot was sent. Counts can change. |
| Native UI rendering | Normal 480 × 560, quick panel 360 × 440, navigation, settings, Smart routing (680 × 660) and clipboard viewer (480 × 320) rendered and visually inspected. |
| Native compact-window regression | Real Windows subprocess confirms the Win32 topmost bit and capture-affinity `0x11`, visible welcome chips and stable 320 × 360 reader with synthetic chat, capture controls, an image and a long notice; keys disabled, no provider calls. |
| Native capture guard | Real affinity `0x11` verified on main/quick/orb/clipboard windows, settings, history, a menu and a notice; Pin off/on reapplies it to the current handle. No recorder compatibility inferred. |
| Wheel and clean installation | Wheel contains Apache 2.0 LICENSE/NOTICE, no personal author fields or private files; installed with dependencies into a fresh virtual environment and passed empty-default/memory and native startup checks. |
| Git publish-list audit | No known personal name, home-directory paths, private .env, database, logs or generated artifacts in candidate files; empty template is shareable. Existing initial commit has no matching private name in author/committer fields. |
| Repeatable sharing audit | Working/index text versions passed private-path/template/home-path/key-shape checks. Regression tests catch older staged keys after a working repair or deletion. Past commits and arbitrary personal facts need separate review. |
| Security/UX regressions | Synthetic vault and HTTP fixtures verify destination isolation, credential/input validation, redaction and proxy/CA/redirect defaults. Qt tests verify masking, literal tooltips, per-model image confirmation, reduced motion and input-aware Send. |
| Current local application | Restarted at the compact placement; Maya the Helper responds and startup/diagnostic logs are empty. |
| Physical screen capture, earlier local check | MSS captured 1366 × 768 and prepared a bounded in-memory image; no image was transmitted. |
| Windows Credential Manager, earlier local check | Synthetic credential at a unique test endpoint saved, read and removed using WinVaultKeyring; no real key displayed or altered. |

`scripts/run_tests.ps1` runs the dependency, lint, format, compile, test and smoke checks together.
Screenshots used for layout inspection are ignored local artifacts, not fabricated product replies.
Qt offscreen is used for interaction tests; native Windows rendering is used for visual inspection.
An initial run alongside native visual rendering and concurrent test activity hit timing limits.
After updating the assertion for intentional empty-draft Send behavior, a serial full run passed
all checks. Native renders were inspected separately; no product deadline was weakened to pass.

## Reference coverage and deliberate resolutions

Both specifications and all supplied pasted narrative/code were considered. The repeated
narrative supplies the same product request; it does not add another functional reference program.
The detailed build specification ends at FR-PROV-7. Its absent later sections cannot be invented.
The latest name, Python-only local scope and compact-size instruction take precedence over the
earlier working names. See REFERENCE_ANALYSIS and DECISIONS for the audit and rationale.

| Requirement group | Implemented behavior and evidence | Practical boundary |
| --- | --- | --- |
| FR-WIN-1–5 | Normal/quick/orb, shared draft/state, tray, remembered placement, local lock/show channel; Qt and subprocess tests. | Alt+Shift+N preserves reference show/hide behavior; mode buttons switch normal/orb. |
| FR-ORB-1–2,4–5 | Drag/snap, size/opacity, state ring/badge plus text, right-click actions, per-screen clamping. | Mixed-DPI/disconnected physical-monitor coverage still needs hardware tests. |
| FR-ORB-3 | Configurable idle opacity and size. | Optional fullscreen auto-hide deferred. |
| FR-CAP-1–8,10 | Monitor/all/window/region/last capture, OFF gate, own-window hiding/exclusion, image preparation, uniform-frame rejection, preview/thumb/remove and real-pixel black boxes. Tests cover preview accept/discard, failure restoration, OFF during delay, scaling math and negative-coordinate selection. | Capture reads visible pixels, not hidden app data; protected/occluded content remains limited. No OCR redaction. |
| FR-CAP-9 | A prepared-image digest is available; latest image is kept in memory for explicit follow-ups. | Watch/perceptual change detection deferred. Stateless providers need the latest image again for grounded follow-ups. |
| FR-CHAT-1–7 | Streaming Markdown, explicit link/copy/code/feedback menus, paired context trim, Send/Stop/Edit/Regenerate/Continue/New/export, shared drafts and language preferences. | Quick prompts use a menu to retain compact width. A screenshot alone supplies a useful default; Screen ON alone does not silently capture. |
| FR-STR-1–7 | Split-byte SSE and bounded NDJSON, queued QThreads, 45 ms display batching, distinct stop/deadline errors, partial preservation, pre-output retry and local latency. Real quiet-socket Stop/deadline and Quit-during-generation tests pass. | Repeated Send is ignored during a request; Stop precedes a new chat. Cloud billing cannot be cancelled by a client guarantee. |
| FR-PROV-1–7 | Five real adapters, dynamic catalogs, authenticated OpenRouter key check, free/vision/context filters, key-scoped TTL cache, manual compatible/local IDs and endpoint-scoped confirmed vision. Wire-format and catalog tests pass. | Discovery does not guarantee per-model generation access. No custom auth headers, OAuth or automatic key rotation. |
| Instructions and personalization | 34 built-ins, up to 20 custom profiles, instruction preview, optional Gemini classifier with local fallback, explicit scoped memory add/edit/forget, confirmed Forget all and local feedback. | Classifier selects existing instructions only. Extra Google request is opt-in; real-key selection quality remains unverified. No automatic training or measured benchmark. |
| Latest Win32 functionality request | Optional topmost/translucent clipboard viewer, native text notifications, reference scroll/show-hide keys, explicit draft transfer; real Qt synthetic clipboard tests. | Watch OFF initially; hide/pause clears it. No automatic collection into history, provider submission or auto-paste. Native movable/resizable tool frame replaces raw GDI popup. |
| Privacy and security | OS keys, fixed native URLs, HTTPS remote hosts, no redirects, safe error/log values, OFF default, mandatory capture review and no command execution. Tests reject recognizable secrets in memories/profiles. | Plaintext local history; manual screenshot redaction and narrow abuse rules are not comprehensive DLP/moderation. |
| Fresh clone and private configuration | Neutral source/About/footer/metadata, no memory seeds, reset local profile/memories, empty versioned .env template, bounded allowlisted loader and Git-ignored private values. | Existing OS credentials remain private to this account. Backups and external cloud data are not erased. |
| Screen-share upgrade | Global own-Qt-surface lifecycle guard reapplies exclusion to dialogs/menus/handle changes; native read-back and fallback/unavailable reporting. | Real screen-sharing tools have not been exercised; native acceptance cannot establish universal invisibility. |
| Docs, learning and future port | Setup/user/security/testing/troubleshooting guides, Mermaid mind map/sequence, source reading exercises, roadmap and Rust boundary contracts. | No Rust, CI/CD, Docker, Kubernetes, account backend or packaged executable. |

## Significant regressions verified

- A second launch cannot change an active stream marker to interrupted before obtaining the lock.
- Stop and the overall deadline unblock a quiet socket and preserve partial text with distinct states.
- Quit cancels an active QThread and saves partial output before the process exits.
- Transient failures retry only before output; permanent auth failures and partial streams never auto-replay.
- Failed turn insertion/regeneration rolls back atomically; old answers and typed drafts remain intact.
- History OFF prevents later writes, including deletion/replacement of an earlier saved turn.
- Failed cache writes retain discovered models; stale old-credential results cannot overwrite a later refresh.
- Manual model/vision choices survive restart only at their own endpoint; declared text-only metadata wins.
- Screen OFF suppresses stale image input and prevents a delayed capture worker from acquiring pixels.
- New captures need real preview acceptance; discard clears pending/reusable context; capture failure restores UI.
- Memory edits retain IDs and scopes; duplicates/secrets are rejected; database errors preserve editor text.
- Classification output is bounded and allowlisted; malformed JSON/IDs/scores, duplicate/extra fields, missing finish, auth/quota failures and uncertainty fall back locally.
- A separate answer provider receives the selected skill and scoped memory; the classifier sees neither screenshot, memory nor history.
- Stop, draft/config/profile/screen/image changes and Quit invalidate pending classification; stale decisions cannot start an answer or create a saved turn.
- Opt-in clipboard watching coalesces updates, masks recognizable secrets, handles empty/non-text/large content and clears subscriptions/content on hide/pause.
- Literal title/message search, rename/delete, custom profile save/cancel, and compact minimum layouts work.
- Pin persists without losing a draft; the previous default geometry migrates to the smaller default while custom dimensions remain intact.
- Floating opacity rejects invalid/non-finite input. Header dragging clamps to negative-coordinate monitor bounds and stops on hide.
- Icon sizes retain transparent corners; orb/header animation timers stop while hidden/idle. Welcome chips only prefill a draft.
- Algorithms, statistics, engineering, business literacy, meeting notes and health terminology have distinct system instructions and local-route checks.
- Files/data formats, audio/video editing, CAD and customer support add distinct instructions and question-first local-route tests.
- Forget all requires confirmation, retains chats and is safe on an empty database. New installs have no seeded profile or memories.
- Environment loading validates before updating, preserves process values, rejects oversized/invalid UTF-8 or multiline keys, skips unknown variables and disables expansion; verification flags skip the file.
- Capture guards cover new menus/dialogs and visible replacement handles, stop cleanly and distinguish failed, monitor-only and unverified requests.
- Malformed settings, URLs/ports, split UTF-8, oversized unclosed lines, missing finish markers, empty input,
  unsupported image models, huge/uniform images and repeated submissions have focused regression checks.

## Remaining validation and limits

Real Gemini classification and Gemini/OpenRouter generation/image understanding remain unverified until a user configures
keys and resumes live testing. Anthropic/compatible accounts and installed Ollama models need their
own tests. The public catalog proves only live metadata transport/parsing. Google's current
[model catalog](https://ai.google.dev/gemini-api/docs/models) lists Gemini 3.8 Flash and 3.5 Flash-Lite;
Maya selects those preferences only when discovery returns them, preserving explicit choices.

Hardware checks still needed: physical secondary/negative-coordinate monitors, 125/150/200% mixed
DPI, protected/elevated apps, exclusive fullscreen, click-away focus behavior across common desktop
apps, hotkey conflicts with other tools, and long sessions. No universal desktop compatibility or
screen-recorder exclusion guarantee is claimed. Native capture exclusion also hides the assistant
from some external UI screenshots; its own widget renders were used for visual QA.

PyInstaller packaging is documented but not installed/built/validated here. Maya's original source
now uses Apache License 2.0. PyQt/Qt and other dependencies retain separate licenses; their distribution
terms still apply to bundled builds. Multiple-key
rotation, custom headers, watch/OCR/direct file integrations and autostart are explicitly deferred.

Next steps are in DEVELOPMENT_ROADMAP and the manual checklist in TESTING. Local implementation
and documentation are complete for this release scope; account/hardware evidence must be recorded
before calling the app broadly production-validated.
