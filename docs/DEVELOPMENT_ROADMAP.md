# Local release and validation roadmap

Updated 12 October 2026.

The Python development application is runnable locally. The remaining release gates are real
provider-account and hardware checks, rather than unfinished placeholder implementations.
See [ENGINEERING_REPORT](ENGINEERING_REPORT.md) for the actual evidence and requirements matrix.
The proposed v0.2 development cycle is in [NEXT_VERSION_IMPROVEMENTS](NEXT_VERSION_IMPROVEMENTS.md),
with priorities, completion criteria and a verification plan.

| Stage | Current state | Completion evidence |
| --- | --- | --- |
| Reference audit and product scope | Complete | Original Win32 source inspected and preserved; conflicts recorded in REFERENCE_ANALYSIS/DECISIONS. |
| Portable core and Windows UI | Complete for local scope | Request/stream/store contracts, native chat/orb/tray, compact layouts, credential boundary and capture pipeline. |
| Gemini/OpenRouter plus explicit extensions | Implemented; protocol-tested | Actual adapter serializers/parsers exercised with HTTPX mocks; public OpenRouter catalog fetched live. |
| Local regression checks | Complete | 268 passing tests, lint/format/compile/dependency checks and disposable native startup. |
| Optional Gemini routing and clipboard viewer | Complete locally | 34 built-in skills, custom instruction preview, allowlisted JSON classifier/fallbacks, draft-preserving Stop and opt-in reference clipboard controls. Real-key routing quality still needs validation. |
| Sculpted identity and smaller topmost UI | Complete locally | 480 × 560 main / 360 × 440 quick panel, persistent Pin, floating translucency, header drag, visible-only bloom and native Windows minimum-layout regression. |
| Fresh-clone privacy and sharing | Complete locally | Neutral source/profile, empty local memories, confirmed Forget all, private .env/template, Apache 2.0 and Git publish-list audit. |
| Outgoing-context review | Complete locally | Credential-free preview, shared prepared Request, separate routing/final consent, stale-input rejection, text sanitation and native affinity check. Live account behavior remains a separate gate. |
| Screen-share lifecycle protection | Implemented and locally tested | Own-window/dialog/menu guard, handle replacement, honest affinity read-back and native Windows check. Actual recorder compatibility remains a separate gate. |
| Documentation and learning | Complete | Setup, architecture diagrams, user/security/testing guides, source reading exercises and Rust contracts. |
| Real account generation | Requires user-provided credentials | Configure keys in the app; verify incremental text, vision, quota errors, Stop and follow-ups for each account. |
| Broader Windows hardware | Requires physical checks | Mixed DPI, secondary monitors, protected/elevated applications and longer sessions. |
| Actual screen-sharing tools | Requires recorder checks | Follow SCREEN_SHARING for versioned full-screen/window-mode checks and a manual hide fallback. |
| Packaged executable | Future stage | Follow SETUP packaging procedure; separately run the full manual checklist on the executable. |

## Next validation session

1. Configure Gemini in Settings → Providers; discover models and send one short text question.
2. Verify a harmless reviewed screenshot with a discovered vision model; test Stop/Continue.
3. Repeat for OpenRouter, including the current free-model filter and an available free model.
4. Test compatible/Anthropic accounts only when their own credentials are available. Test installed
   Ollama models separately; the application does not start the server or download models.
5. Record provider/model/date, outcome and safe error kind in the engineering report. Never record keys.
6. Run the hardware checklist before describing the app as broadly production-validated.

## Later enhancements

Multiple-key rotation, additional authentication schemes/headers, optional fullscreen auto-hide,
opt-in watch/change detection, OCR/direct file readers, image-inclusive exports and startup
registration are future features. None are prerequisites for ordinary explicit screenshot/text
help. Keep any watch workflow visibly opt-in; stateless image requests still need image context.

Python remains the only implementation language. Use the [Rust roadmap](ROADMAP_RUST.md) after
the Python workflows have passed the account and hardware validation gates. Do not add Docker,
Kubernetes, CI/CD or an authentication backend to this local-first release.
