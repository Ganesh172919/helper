# Learn to maintain Maya

Read the code by following one action rather than trying to understand every file at
once. Your supplied notes say you want more scaffolding when reading a cold codebase and want
to write a substantial part yourself. These exercises are for your learning; the shipped app
does not depend on unfinished exercises.

## First reading path

1. Start at `main.py`: where are settings loaded, and why does the lock precede database recovery?
2. Follow `AppController.submit()`: identify validation, profile, memory and request construction.
3. Read `build_request()`: explain why dropping full old pairs is better than dropping arbitrary turns.
4. Read `Generation.run()`: find the exact point after which automatic retries are forbidden.
5. Follow `GeminiProvider.stream()`: compare one wire fixture with Google's official request schema.
6. Follow `receive_delta()` → `flush()` → `MessageCard.refresh()`: why buffer UI repaints?
7. Follow `generation_ended()` → `HistoryStore.update_message()`: how is partial output preserved?
8. Follow `TaskRouter.route()` → `begin_answer()`: how does an ID choose instructions without changing fixed rules?
9. Follow `ClipboardWindow.set_watching()` → `hideEvent()`: why does hiding detach and clear the viewer?

Draw that path on paper and put a breakpoint at each step. Keep tests open beside source files.
Use a synthetic provider from `test_ui.py` when learning; it needs no key and creates no API cost.

## Small exercises with meaningful verification

| Exercise | What you learn | Useful check |
| --- | --- | --- |
| Extend the shipped Git skill with a focused conflict example | Dataclasses, classification and scoped prompts | A real example selects it and explicit user override still wins. |
| Trace the shipped memory scope editor; add a scope filter | SQLite updates, validation and UI state | Filtering never changes a memory's saved scope. |
| Show normalized token usage beside latency | Provider schemas and event normalization | Gemini/OpenRouter fixtures map to the same visible fields; unknown usage stays unknown. |
| Trace the shipped history search; add a date filter | Parameterized queries and signal wiring | Date filtering narrows results without altering messages. |
| Add a maximum answer-width preference | Readability and layout constraints | Narrow/large displays still reach input and controls. |
| Implement an extra compatible provider preset | Authentication boundaries and endpoint validation | No stored key is reused across different endpoints. |
| Add image comparison for an explicitly enabled watch feature | Image hashes and privacy-controlled state | OFF takes zero captures; unchanged images trigger no new requests. |

## Debugging habits

Write down expected behavior, reproduce the smallest failing input, inspect the layer that owns
it, then fix the cause. Add a regression test for significant failures. For a UI failure, pump
the Qt event loop rather than guessing from source. For an API failure, inspect a synthetic wire
request, not a real secret-filled request body. For SQLite, use temporary databases.

Use type hints and short public docstrings. Explain non-obvious reasons in comments. Avoid adding
frameworks merely to sound advanced. A small application with measured verification is a better
interview demonstration than a large unverified architecture.

## Explain the project in an interview

Describe the context-switching problem, the explicit screenshot + task instruction + question
flow, how queued signals keep the UI responsive, why credentials use OS storage, why memory is
approved/local, and how error states preserve partial work. State test evidence precisely and
distinguish mocked protocols from live authenticated generation. Describe your own contributions honestly; do not invent users, rankings or metrics.
