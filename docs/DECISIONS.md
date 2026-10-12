# Decisions and development roadmap

| Decision | Why | Alternative / limit |
| --- | --- | --- |
| Maya the Helper is the product name | The final product specification takes precedence over Vysper/ShareScreen working names. | The repository stays `helper`. |
| PyQt5 native UI | The reference is raw Win32 with no named GUI framework; the supplied build brief asks for PyQt5 fallback. | Qt6 is a future migration; no web frontend is introduced. |
| HTTPX REST adapters | One transport supports documented SSE/NDJSON and mockable wire tests with few dependencies. | Provider SDKs are useful later if needed; no obsolete Gemini SDK is used. |
| Gemini/OpenRouter first, extra explicit adapters | Later requirements ask for broader BYOK and localhost support. | No claim of arbitrary global API-key compatibility. |
| Streaming is primary | Immediate progressive answers reduce waiting. | The reference clipboard viewer is optional, local and explicitly enabled each session; it never auto-submits. |
| Gemini routing is opt-in | The product requirements call for an LLM classifier to choose task instructions. | Adds a separate Google call and potential cost; explicit profile overrides bypass it. Timeout/error/uncertain output falls back locally. |
| Classifier output is an allowlisted ID | Existing rules and approved skill instructions remain authoritative. | Classifier cannot generate system prompts, tools or executable functions. |
| Neutral fresh-install profile | Maya is for everyone; the product has a neutral About page. | No personal facts or memory seed are bundled; users add their own preferences. |
| Private .env as an explicit alternative | An empty template helps fresh clones configure their own providers. | OS credentials remain preferred; no parent search, expansion, unknown variables or verification-time loading. |
| Apache 2.0 for original source | A permissive source license with patent terms was selected for this release. | Third-party licenses still apply; PyQt/Qt distribution terms are separate. |
| SQLite and user-approved memory | Local, inspectable, portable and easy to maintain. | No embeddings/server database or automatic facts extracted from private screenshots. |
| Screen OFF, explicit preview | Screenshots can contain unrelated private information. | No watch/passive multi-shot workflow in this version. |
| Native capture exclusion plus hide fallback | API support and recorder behavior vary. | Universal invisible/stealth recording claims would be misleading. |
| Capture a visible window rectangle | Safe read-only capture without injecting code into applications. | Hidden/occluded window capture and direct Excel/PDF APIs are future features. |
| Region selection on one monitor | Per-monitor mapping is tractable with mixed DPI. | Dragging a region across multiple mixed-DPI screens is not implemented. |
| One latest image per request | Stateless providers need image context for each grounded follow-up. | No duplicate historical image copies or undocumented server-side image cache. |
| QThread workers with 45 ms repaint buffer | Simple Qt ownership and responsive network handling. | No agent orchestration framework is required. |
| Compact default and hidden navigation | The product requirements call for a smaller window. Default 480 × 560 and quick panel 360 × 440 leave more of the work visible. | Quick prompts, feedback and code copying use menus; navigation scrolls at small heights. |
| Persistent Pin and stable floating geometry | Main chat starts topmost, and Pin can disable it; the quick panel stays above normal windows. | Framed settings remain separate; exclusive fullscreen and protected apps need physical checks. |
| Glowing code-native identity | Six shaped ceramic petals, a beveled jade base and warm halo give the requested 3D appearance throughout the native app. | Ordinary QPainter painting, no mesh/GPU dependency or downloaded artwork. Glow/bloom timers stop when hidden or idle. |
| Warm paper and clear action hierarchy | The welcome typography, grouped input well, quiet message controls and consistent line icons give the app a coherent visual voice. | Compact dimensions are retained; both screen drawers stay closed until opened, and consent still requires the inner switch. |
| Setup guidance preserves provider flexibility | Empty cloud catalogs open provider setup; cached/manual/local choices still open selection. | Send needs a selected model; drafting remains available. No hidden refresh or paid request is added. |
| Accessible compact status and notices | Status text elides with complete tooltips/descriptions; Read details opens full plain text in either mode. | Long errors cannot grow the outer window or interpret supplied HTML. |
| Atomic pending-turn replacement | A disk/write failure must not delete a previous answer or clear a replacement draft. | begin_turn commits both messages and any regeneration replacement together. |
| Endpoint-scoped manual and vision preferences | Compatible discovery may be unavailable or omit image capabilities. | Explicit choices survive restart only at their matching host; declared text-only metadata still wins. |
| Custom profiles staged; memory edits immediate | Profiles/preferences save together; memories have explicit Save new/Update/Forget actions. | The Memory tab explains immediate writes; deleted-profile memories remain inspectable. |
| Retry before visible output only | Avoid replaying partial paid responses. | User can explicitly regenerate/continue after errors. |
| No automatic command execution | Understanding a coding agent's commands is the stated core need. | Any future action mode needs a new explicit permission design. |
| Python local release first | The laptop workflow is the present deliverable. | Rust, installers, CI/CD, Docker/Kubernetes are outside this build. |

## Reference reconciliation

The Downloads program and pasted Python program are the same style of clipboard overlay; a
separate second functional program was not available. The detailed build brief ends at FR-PROV-7.
Later referenced sections are unavailable. This implementation combines the available source,
the full Vysper specification and the current product requirements. New references should be
compared with REFERENCE_ANALYSIS before modifying the working interaction flow.

The original source's non-activating topmost behavior, show/hide shortcut, scroll keys and capture
exclusion idea survive. The optional local clipboard panel restores the reference's text preview
alongside streaming chat. Qt owns safe drawing/event resources. Native calls have pointer-safe
signatures and checked shortcut outcomes.

## Current release boundaries

Implemented: normal/compact/orb/tray; provider adapters; dynamic catalogs/free filtering;
explicit image workflow; streaming/control/recovery; local history/approved memories; guides and
automated tests. Verification levels are recorded in ENGINEERING_REPORT.
The compact update also includes literal title/message search and conversation renaming, editable
memory scopes, saved custom profiles, model-choice persistence and regression coverage for disk failures.

Remaining validation: real-key generation for Gemini/OpenRouter/Anthropic/compatible providers,
installed Ollama models, longer sessions, mixed-DPI/negative-coordinate hardware, protected/elevated
application behavior, and packaged distribution. No performance benchmark has been conducted.

Deferred features: provider-specific multiple-key rotation, custom HTTP headers, watch/change
detection, fullscreen auto-hide, startup registration, OCR/file readers, attachments beyond
screenshots, export including images, and a comprehensive moderation service. These are not
presented as finished features. Avoid adding them until the current flows are validated with keys.

## Rust direction after Python stability

Keep the contracts in `core/types.py`: model metadata, request messages/system/image, normalized
text/usage/finish events and public error kinds. Port SSE framing, context budgeting, configuration
and provider serializers first; then SQLite persistence. Qt/UI code remains a separate consumer.
Potential libraries to evaluate then include reqwest, rusqlite, serde and OS credential libraries;
no Rust dependencies or code have been added now. Validate equivalent protocol fixtures on both
implementations before swapping a boundary. Do not prematurely replace the working Python app.
