# Future Rust boundaries

This is a design note, not a Rust implementation. Maya currently runs entirely in Python.
The goal is to retain a working desktop experience while replacing one tested boundary at a time.

## Preserve these contracts

`core/types.py` defines Model, Message, ImageAttachment, Request, StreamEvent and MayaError.
The portable core imports neither Qt nor Windows platform code. The UI owns display/state;
provider adapters own HTTP wire formats; platform code owns capture exclusion, hotkeys and keys.

| Boundary | Python owner | Future replacement responsibility |
| --- | --- | --- |
| SSE / NDJSON | core/streaming.py | Incremental strict UTF-8 framing, bounded event/line size, EOF handling. |
| Context | core/prompts.py | Keep system/current turn, trim complete old pairs, attach one latest image. |
| Providers | core/providers.py | Same auth headers, serializers, safe errors, deadlines and no redirects. |
| Settings | core/config.py | Bounded validation and atomic non-secret JSON writes; retain compatible defaults. |
| Persistence | core/storage.py | Preserve SQLite schema, WAL/foreign keys, atomic turn replacement and scoped memories. |
| Credentials | platform/secrets.py | Endpoint-scoped OS storage; no plaintext fallback or incidental verification access. |
| Desktop | platform/windows.py, capture.py | Physical pixels, logical-coordinate mapping, native focus/hotkey/capture behavior. |
| UI | ui/* | Consume normalized events without provider-specific knowledge; keep both surfaces synchronized. |

Potential Rust libraries to evaluate at that future stage are serde/serde_json for data,
reqwest for HTTP, rusqlite for SQLite, and an OS credential library. Their versions, licenses,
platform support and APIs must be checked then. No Rust dependency has been added now.

## Example event contract

Synthetic examples contain no credentials or real user content:

```json
{"kind":"text","text":"An explanation chunk","data":{}}
```

```json
{"kind":"finish","text":"length","data":{}}
```

```json
{"kind":"usage","text":"","data":{"input_tokens":120,"output_tokens":80}}
```

Usage keys are provider-specific today; normalize them explicitly before making a cross-language
schema promise. Finish states are complete, length or safety; cancellation/network/deadline errors
carry a safe error kind and preserve partial text. A transport EOF without a finish marker is an
interruption, not a successful response. Images remain in memory and never become SQLite blobs.

## Migration order and acceptance

Port framing first using the same split-byte/Unicode/CRLF/oversize fixtures. Then port context
construction, provider serialization, settings and persistence. Compare complete wire requests
and normalized event sequences against Python, including errors and cancellation. Keep one
authoritative implementation per boundary and the existing UI while measuring startup, first
text, memory and responsiveness. Move Windows/UI code only after the portable boundaries agree.

Do not begin this work until the Python account and hardware tests in DEVELOPMENT_ROADMAP pass.
