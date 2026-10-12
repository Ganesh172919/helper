# Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\python.exe -m maya --smoke-test
```

Tests set Qt's offscreen platform and use temporary SQLite files. They never read your configured
cloud keys and never send your screenshots, memories or questions to providers. HTTP integration
uses synthetic fixtures; one loopback server checks real quiet-socket cancellation.
The subprocess checks use `--no-credentials` or an explicitly disabled SecretStore. Smoke tests
also disable credential access. Current result: **268 passed** on the verified laptop environment.

| Suite | Evidence |
| --- | --- |
| `test_core.py` | SSE byte splits/Unicode/CRLF/comments/multiline/EOF/limits, URLs, defaults, settings, SQLite recovery/cascades, memory ranking/cache identity, context trim, profiles, redaction, refusal, images, hotkeys |
| `test_providers.py` | Real adapter request serialization with HTTPX mocks, Gemini pagination/auth/thought filtering, free/vision metadata, authenticated OpenRouter validation, native Anthropic/Ollama/compatible streams, missing finish markers, safe errors |
| `test_routing.py` | Native Gemini structured JSON payload, discovered-only model selection, custom skill, bounded/redacted data, invalid/duplicate/extra fields, confidence types, truncation, auth/quota/network fallbacks and cancellation |
| `test_ui.py` | Real Qt widgets/QThreads; compact and minimum layouts with images/code; shared drafts/views; preview accept/discard; OFF during capture delay; region mapping; streaming/stop; manual model restoration; stale refresh rejection; memory/profile/history editors; disk failures; retry boundaries; About/key masking |
| `test_network.py` | Real local HTTP SSE server remains quiet after one chunk; Stop and overall deadline interrupt reads with distinct statuses |
| `test_startup.py` | Real isolated processes; second launch cannot recover an active stream; Quit during generation saves the partial text and exits without destroying a running QThread |
| `test_environment.py` | File allowlist, precedence, no expansion, atomic validation, UTF-8/BOM, size/invalid-key boundaries, empty template and verification flags skipping .env |
| `test_privacy.py` | Empty-install defaults, confirmed/cancelled Forget all, chats retained, dialog/menu/handle lifecycle, guard shutdown and honest failed/fallback statuses |
| `test_sharing.py` | Real isolated Git candidates/index, ignored local files, forced private files, filled templates, staged secrets after working repairs/deletions, safe diagnostics, size/binary review and CLI exit codes |
| `test_security.py` | Endpoint-bound environment keys, native/unknown destination rejection before backend access, invalid stored/process keys, atomic invalid .env binding, secret-free preferences, quoted JSON/assignment redaction and ignored proxy/CA/redirect settings |
| `test_context.py` | Detached history copies, raw-before-JSON sanitation, relevant-input fingerprints, actual image-byte identity and bounded/redacted classifier preview payload |

The Qt suite additionally covers Gemini routing into a separate answer provider, scoped memory only in
the answer, single-flight Send, edit/Stop/profile/screen/settings races, classifier-disabled/manual/no-key
fallbacks, invalid answer rejection before routing, Quit during classification, instruction preview and
opt-in clipboard debounce/plain-text/masking/size limits/scrolling/hide/pause. Loopback tests also hold
a model-catalog socket quiet to verify Stop and the short classification deadline.

The latest UI checks verify Pin persistence without losing a draft, opacity validation/migration,
inspection-only capture drawers, prompt chips, icon transparency/size variants, stopped idle/hidden
animations, title dragging and negative-coordinate clamping. A separate native Windows subprocess
uses real fonts and confirms the Win32 topmost flag, capture-affinity read-back of `0x11`, visible welcome prompts and stable 320 × 360
geometry with synthetic chat, capture controls, an attachment and a long notice. Its credentials are
disabled and it does not read the user's clipboard or send any provider request.
Another native subprocess verifies `0x11` on main/quick/orb/clipboard windows, settings, history,
a menu and a notice, including both Pin transitions. This read-back test skips unsupported
Windows builds; fallback reporting remains covered by synthetic fixtures.
The compact notice's details dialog is checked for complete plain text, even when a notice contains
HTML-like characters; opening it starts no network or capture job.

The latest design checks exercise cloud setup versus cached/manual/local model paths, preserved
drafts during setup, multiline keyboard input, composer focus, disabled Send/Capture while paused,
both screen drawers without implicit consent, long status/notice minimum layouts, and an opaque
floating header with transparent corners. Native widget renders were inspected for main, navigation,
conversation, floating, minimum-size, settings and glowing icon views. Idle/hidden animation still stops.
Additional checks exercise local instruction search without saving/requesting, the new Gemini skill
allowlist, memory summaries and disabled actions, and safe recovery after memory loading/clearing errors.
Setup/picker checks additionally cover typed-key reveal and masking on blur/hide/timeout/Cancel,
endpoint edits clearing input, independent search reset and empty results, model-specific image
confirmation, persisted reduced motion during activity, and Send availability for text/reviewed images.
Tooltip rendering verifies literal markup with no embedded image object; explicit web links need valid hosts.
Context-review tests verify zero credential reads/writes/jobs on opening/cancellation, exact prepared
Request reuse, stale draft/model/memory/history/window/image/profile rejection, separate Gemini/final
approvals, final-review mutations and pause, memory races during routing, outgoing history sanitation,
raw-credential refusal, Screen OFF and immutable screenshot bytes, and keyboard reading without consent.
The native Windows affinity subprocess now also verifies `0x11` on the context-review dialog.

An initial combined native-render/test run hit timing limits under concurrent activity. The final
full suite was run serially and passed, including the quiet-socket and native-process checks.
Run native visual inspection separately from the regression suite on a busy laptop.

A wheel was installed with dependencies into a fresh virtual environment outside the checkout.
Its metadata/license notices, absence of private files, empty defaults/memories, dependency check
and native smoke startup passed. A bundled executable remains unverified.

## Manual laptop checklist

1. Launch normal mode; confirm controls remain reachable at your DPI and display size.
2. Configure each provider's own key in Settings; Save & refresh; choose a listed model.
3. Send “Reply with one short sentence explaining what Maya helps with.” Confirm incremental text.
4. Send a longer explanation; Stop; Regenerate; Continue. Verify partial and final statuses.
5. Refresh Gemini; compare listed IDs with your provider account. Verify denied model/quota errors.
6. OpenRouter Free models: independent search, vision-only and context sorting; generate with a current free model.
7. Screen OFF: Capture disabled; no screenshot enters requests. Screen ON: capture/preview/discard/retake.
8. Capture a harmless test page, black out a box, attach, and ask a vision model about visible content.
9. Test current monitor, all monitors, active window, negative-coordinate displays and region crops.
10. Test 100/125/150/200% scaling on real multi-monitor hardware; disconnect a monitor and restart.
11. Drag orb, click to expand, type, Escape, Full window. Confirm shared draft/model/attachment and click-away behavior.
12. Test shortcuts and a deliberate conflict; closing to tray; paused state; second launch; Quit during generation.
13. Save/correct/forget a memory, disable its use, and test a later response. Inspect text-only saved history.
14. Export Markdown, copy code blocks, open an intentional web link, and confirm embedded resources stay blocked.
15. Drop network during a stream; retain text; no automatic replay after visible output. Reconnect and retry.
16. Separately test a packaged executable before sharing it.
17. Add/edit/delete a custom profile; save/cancel Settings; confirm both modes reflect the saved collection.
18. Search text absent from the chat title; rename/delete a result; confirm only the chosen chat changes.
19. Choose a manual compatible model and verified image support, restart, then change endpoint; confirm host-scoped restoration.
20. At minimum width, attach an image and open code/feedback menus; navigation must scroll without forcing a taller window.
21. Enable Smart routing with a Gemini key; verify a task's selected instruction via Why this skill, then select a profile directly to bypass routing.
22. Stop/edit/turn Screen OFF while routing; keep the draft and confirm no late answer starts. Test routing quota/invalid model with local fallback.
23. Open the clipboard viewer; verify OFF reads no copied content. Enable Watch with synthetic text, then wheel/arrows/page/home/end/global scroll, Use in chat, hide/pause and reopen OFF.
24. Pin/unpin the main window, restart, and adjust floating opacity. Drag the reader header, then hide it during a gesture; verify the draft and controls remain available.
25. More → Screen-share privacy: inspect every visible surface. Make a private recording with your actual sharing tool; check windows, menus and dialogs, then use the hide fallback if needed.
26. Confirm a fresh installation starts with empty memories/name/profiles. Test Forget all cancellation and acceptance, retaining chat history.
27. Copy the empty environment template, add synthetic values and verify process/OS precedence; never publish the filled file.
28. Search the instruction library by a partial name. Check its preview without changing the chat profile or starting a request.
29. Run `scripts/check_sharing.py` before publishing and again after staging; review history and personal facts separately.

Tests cannot replace real account/quota or hardware behavior. Do not report the manual checklist as
passed merely because the relevant code exists. Live-key generation results and hardware gaps are
explicit in the engineering report. No synthetic replies are presented as real provider output.
