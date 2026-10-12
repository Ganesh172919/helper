# Provider contracts

Official documentation was checked on **10 October 2026**. Model discovery is runtime data,
not a hardcoded catalog. Catalog access does not prove a model can generate for a particular
account, region, subscription, balance or quota. A user must complete a real generation test.

| Provider | Authentication | Discovery | Streaming |
| --- | --- | --- | --- |
| Gemini | `x-goog-api-key` | `GET /v1beta/models`, paginated | `POST models/{id}:streamGenerateContent?alt=sse` |
| OpenRouter | Bearer | `GET /api/v1/models`; `/key` verifies key | `POST /api/v1/chat/completions` |
| Compatible | Optional Bearer on localhost; required for remote | `GET /models` or manual ID | `POST /chat/completions` |
| Anthropic | `x-api-key`, version header | `GET /v1/models`, paginated | `POST /v1/messages` |
| Local Ollama | None | `/api/tags` and `/api/show` | `/api/chat`, NDJSON |

Gemini sends system instructions in the native field and images in inline data. Thought parts
are skipped. Stop/MAX_TOKENS/safety endings become explicit UI statuses. GenerateContent models
are filtered for the text-help workflow. The Models endpoint does not report input modalities:
vision is inferred only for documented Gemini text families; other families remain unknown.
Google's current catalog includes Gemini 3.8 Flash and Gemini 3.5 Flash-Lite. These are default
preferences only if discovered; the user's valid explicit selection wins. [Google Models API](https://ai.google.dev/api/models),
[content generation API](https://ai.google.dev/api/generate-content), [model catalog](https://ai.google.dev/gemini-api/docs/models.md).

OpenRouter model records expose input modalities, context/output limits, supported parameters,
and prices. A model is free when prompt and completion prices are both zero, or it carries the
`:free` suffix. Missing pricing is not interpreted as free. Images use a data URL. Requests only
include temperature/max-token parameters advertised in metadata. SSE keepalives and in-band
errors are handled. The public catalog is separate from authenticated `/key` validation.
[Models metadata](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties),
[streaming protocol](https://openrouter.ai/docs/api_reference/streaming),
[API key information](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key).

The compatible adapter implements **Chat Completions**, not every provider's proprietary API.
It covers endpoints that genuinely implement that protocol. OpenAI's native host uses
`max_completion_tokens`; other compatible hosts use `max_tokens`. Temperature is omitted because
reasoning-model support varies. Generic discovery usually lacks modality/limit metadata, so
conservative defaults and an explicit verified-vision override are used. Some model IDs may not
support Chat Completions; choose a compatible one. [Official OpenAI chat reference](https://developers.openai.com/api/reference/resources/chat),
[model listing](https://developers.openai.com/api/reference/resources/models/methods/list).
Manual IDs and verified image-capability choices persist for the chosen base URL. An endpoint
change invalidates those preferences. Fresh catalog metadata declaring text-only input cannot
be overridden by an old unknown-model confirmation. A manual ID is still validated by the
provider when you submit; it is never described as discovered or guaranteed accessible.

Anthropic uses native Messages blocks, separate system text, base64 image input, text_delta,
message_delta usage, and message_stop. Default context/output limits are conservative when list
metadata omits them. Thinking/tool blocks are unused. [Messages streaming](https://platform.claude.com/docs/en/build-with-claude/streaming),
[model listing](https://platform.claude.com/docs/en/api/models/list).

Ollama lists installed models and checks each model's capabilities before enabling images.
It does not install or pull models. Local requests carry standard chat messages, optional base64
images and generation options. Cold model loads may require a larger timeout. [Chat API](https://docs.ollama.com/api/chat),
[installed-model listing](https://docs.ollama.com/api/tags), [model information](https://docs.ollama.com/api/show).

Every adapter yields `StreamEvent(text/usage/finish)` or raises safe `MayaError`. The HTTP
transport validates TLS, forbids redirects, bounds JSON/SSE data and normalizes errors without
displaying provider messages that may echo secrets. HTTP 400/401/403/404/402 do not automatically
retry. Network/5xx/429 may retry before visible output only. No cloud keys are sent to Maya servers.

Known limits: no arbitrary custom auth headers, automatic key rotation, file-upload APIs, voice,
tool execution, Responses API, Vertex AI service accounts, OAuth, image generation, audio or
embedding workflow. Add a dedicated adapter/test when a new protocol is needed. Universal API
compatibility is not claimed. GUI settings are the supported route for BYOK.
