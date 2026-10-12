# Maya the Helper — next-version improvements

Plan date: **12 October 2026**. Proposed release: **v0.2.0**.

This document proposes the next development cycle. The application remains v0.1.0 until the
changes are implemented and verified. Completed work and existing validation gaps are recorded
in [ENGINEERING_REPORT](ENGINEERING_REPORT.md) and [DEVELOPMENT_ROADMAP](DEVELOPMENT_ROADMAP.md).

## Release goal

Make Maya easier to start, clearer about the context it sends, and more reliable during everyday
desktop work. Keep the Python application small, local and useful to someone cloning it for the
first time. Prioritize dependable workflows before adding more features.

The last verified baseline, on 11 October, has 209 passing tests, 34 built-in skills, streaming
adapters, reviewed screenshots, approved SQLite memories and a glowing flower icon. Main chat
starts at 480 × 560; the floating panel starts at 360 × 440. Windows capture-affinity checks pass
locally. Real-key generation, actual recorder compatibility and broader hardware checks remain
separate validation work.

## Priorities and completion criteria

Progress on 12 October: setup guidance and model-search feedback were refined, reduced motion was
implemented, and credential/tooltip boundaries were strengthened. Outgoing-context review is now
implemented and locally verified, including separate Gemini/final approvals and stale-review rejection.
Skill-quality evaluation and the remaining account/hardware gates below are still planned work.

P0 items are release validation gates. P1 items are the proposed v0.2 improvements. P2 items are
later candidates; they should not delay the focused release.

| ID | Priority | Improvement | Done when |
| --- | --- | --- | --- |
| V1 | P0 | Validate Gemini and OpenRouter with real accounts | Model discovery, incremental text, reviewed vision input, Stop, Continue, quota errors and optional Gemini routing have recorded results. Keys stay in the app; no private prompts/images enter the report. |
| V2 | P0 | Verify Windows display and screen-sharing behavior | Supported physical configurations and actual recorder modes have versioned results. Unsupported/unverified cases remain clearly labelled and the manual hide fallback works. |
| U1 | P1 | Make first-run setup easier | A short setup path explains provider/key/model selection, preserves the draft when cancelled and starts no paid request without an explicit action. A fresh clone has no profile or memory seeds. |
| C1 | P1 | Add a review of outgoing context | Before Send, users can inspect the question, included history, chosen skill, approved memories and attached image. Classification and answer-provider context are shown separately; credentials are never displayed. |
| U2 | P1 | Refine compact accessibility and motion | Keyboard navigation, descriptive labels and focus recovery work in both modes. A reduced-motion preference disables decorative activity animation. Long content and notices keep controls reachable at minimum size. |
| Q1 | P1 | Evaluate skill selection and prompt quality | A versioned set of synthetic tasks covers ambiguous questions, competing window titles and harmful embedded instructions. Local routing is checked automatically; opt-in Gemini results report quality, latency and fallback rate separately. |
| R1 | P1 | Improve recovery and troubleshooting | Interrupted requests retain available text and drafts. Useful recovery actions explain the next step without automatic replay after visible output. A diagnostics export contains only allowlisted technical metadata. |
| M1 | P2 | Add reviewed memory export/import | A bounded, versioned file has a preview and explicit selection before import. Secrets and invalid scopes are rejected; duplicate handling is explained. Export warns that approved memories can contain personal information. |
| F1 | P2 | Add a small file-context workflow | Start with user-selected text/CSV files, bounded size and encoding checks, then a preview of exactly what will be submitted. PDF/spreadsheet readers are considered only after that workflow passes. |
| D1 | P2 | Prepare an executable distribution | A separate installed/bundled build passes startup, dependency/license review and the manual checklist on a clean machine. Successful wheel installation is not treated as executable validation. |

## Proposed implementation sequence

1. **Record the baseline and validate V1/V2.** Reproduce reported failures with safe fixtures and
   fix those before adding UI. Follow the existing [testing checklist](TESTING.md) and
   [screen-sharing plan](SCREEN_SHARING.md). Record untested configurations honestly.
2. **Build U1 and C1 together.** Make provider setup and the outgoing-context review consistent
   across normal and floating chat. Keep the ordinary Send path short; detailed context opens
   on demand rather than occupying the compact window.
3. **Refine U2.** Test keyboard-only use, screen-reader labels and real display scaling. Keep the
   existing flower identity, warm surfaces and restrained controls; avoid decorative clutter.
4. **Implement Q1 and R1.** Use synthetic tasks and fault injection to check routing, cancellation
   and recovery. Compare live classifier results only when a user explicitly enables testing.
5. **Verify and release.** Update documentation with observed results, build/install the wheel,
   run the sharing audit, and bump the version only when the agreed release gates pass.

Memory import, file readers and executable packaging can move to a later release if the P1 work
already fills the cycle. Avoid adding all three while the account/hardware checks are unfinished.

## Design and interaction notes

- Keep the current compact dimensions as the starting point. Fit content through clear grouping,
  scrolling and expandable details rather than making text or click targets smaller.
- Retain the sculpted Maya flower across the title, orb and settings. Keep idle/hidden animation
  stopped; reduced motion should preserve text status and a static icon during activity.
- Make Screen ON/OFF, selected model and active task understandable without relying on color.
  Opening a drawer, previewing a skill or viewing a setup page must not grant screenshot consent.
- Explain errors beside the affected workflow and preserve the user's work. Keep complete
  notice details available when a compact status is shortened.
- Test empty, loading, populated, paused, interrupted and failure states. Use synthetic example
  content in documentation/screenshots so the shared project stays neutral.

## Implementation areas

| Area | Starting files | Changes to consider |
| --- | --- | --- |
| Setup and shared chat | `src/maya/ui/settings.py`, `windows.py`, `app.py` | Setup steps, focus restoration and consistent normal/floating actions |
| Outgoing context | `src/maya/core/prompts.py`, `types.py`, `src/maya/ui/app.py` | One immutable request snapshot shared by preview and submission; invalidate/review when inputs change |
| Skills and classification | `src/maya/core/prompts.py`, `routing.py` | Synthetic evaluation cases, ambiguity handling and bounded, inspectable decisions |
| Motion and accessibility | `src/maya/ui/branding.py`, `widgets.py`, `windows.py`, `core/config.py` | Reduced-motion setting, readable status and keyboard/focus behavior |
| Recovery and diagnostics | `src/maya/core/providers.py`, `storage.py`, `src/maya/main.py` | Safe recovery actions and a small metadata-only diagnostics export |
| Native window privacy | `src/maya/ui/privacy.py`, `src/maya/platform/windows.py` | Fix evidence-backed lifecycle issues and report actual compatibility |

If settings or database fields change, add a versioned migration with a rollback/recovery path.
Test an existing v0.1 installation as well as an empty install. Preserve chats, approved memories,
provider choices and endpoint-scoped credentials; never copy keys into settings or SQLite.

## Verification plan

Add tests for behavior introduced by each improvement, rather than targeting an arbitrary test count.

| Scenario | Expected result |
| --- | --- |
| Cancel setup after typing a draft | Draft remains available; no provider request starts |
| Change model/profile/memory/image after context review | Review updates or is invalidated; submission uses the current approved request snapshot |
| Classifier enabled with a different answer provider | The separate Gemini excerpt is explained; history, memories and image stay out of classification |
| Reduced motion during capture or streaming | Decorative timers stop; text status and functional updates continue |
| Minimum-size layout, large fonts and long notices | Send/Stop/capture controls stay reachable; full details remain accessible |
| Disconnect network or hit quota mid-stream | Existing text survives; no automatic duplicate generation starts |
| Disk full, locked database or migration failure | Existing records remain intact; actionable error and recovery path are available |
| Diagnostics export | No keys, question text, memory contents, screenshots or personal home paths appear |
| Unsupported capture affinity or recorder behavior | Maya reports the limitation and provides the hide workflow; no invisibility guarantee is inferred |
| Fresh checkout and upgraded installation | Fresh defaults are empty; upgrade retains approved local data and valid preferences |

Run the existing local checks after code changes:

```powershell
& scripts/run_tests.ps1
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir artifacts/wheels
.\.venv\Scripts\python.exe scripts/check_sharing.py
```

Test the resulting wheel outside the checkout. Record provider/model, Windows build, display scale,
recorder version/mode and date for manual checks. Distinguish mocked, loopback, native and real-account
evidence. See [SHARING](SHARING.md) before publishing source or test artifacts.

## Scope boundaries

Keep this cycle in Python, with Gemini/OpenRouter as the primary providers and existing explicit
adapters supported. Select real model IDs from discovery. Add instructions only when they improve
a demonstrated task; classifier output must remain an allowlisted skill, not executable code.

Maintain local storage, user-approved memory and explicit reviewed screenshot submission. Passive
screen watching, automatic command execution, silent key rotation, cloud memory and broad file
indexing require separate designs. Capture exclusion remains best effort; broader compatibility
must come from actual recorder tests rather than hooks into other processes.

Rust migration stays a later phase described in [ROADMAP_RUST](ROADMAP_RUST.md). Keep Docker,
Kubernetes, CI/CD and account/login infrastructure outside this local release. No implementation
dates, quality benchmarks or universal compatibility claims are promised by this plan.
