"""Provider adapters over bounded HTTP transport. No UI imports and no executable model tools."""

from abc import ABC, abstractmethod
import base64
from collections.abc import Iterator
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import json
import time
from threading import Timer
from urllib.parse import quote, urlsplit

import httpx

from .config import Settings, validate_url
from .streaming import parse_sse, parse_ndjson
from .types import Cancellation, MayaError, Model, Request, StreamEvent


# --- Error normalization deliberately ignores raw messages that may echo prompt text or keys. ---
def normalize_http(status: int, retry_after: str = "") -> MayaError:
    """Map HTTP status to a safe actionable error; respect numeric/date Retry-After values."""
    delay = 0.0
    try:
        delay = max(0, float(retry_after))
    except ValueError:
        try:
            delay = max(0, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            delay = 0
    messages = {
        400: (
            "The provider rejected this request. Check model capabilities, output limits, and context size.",
            "request",
        ),
        401: ("This API key is invalid or expired. Update it in Settings.", "auth"),
        402: (
            "The provider reports insufficient credits. Check your account or select a free model.",
            "quota",
        ),
        403: ("This key cannot access the requested model or API. Check provider permissions.", "auth"),
        404: ("The model or endpoint is unavailable. Refresh models and check the base URL.", "model"),
        413: ("The request is too large. Reduce the screenshot size or shorten the question.", "context"),
        429: (
            "Rate limit or quota reached. Wait, check provider quota, or choose another model.",
            "rate_limit",
        ),
    }
    message, kind = messages.get(
        status,
        (
            "The provider is temporarily unavailable. Try again shortly."
            if status >= 500
            else "The provider returned an unexpected HTTP status. Check the endpoint and model.",
            "server" if status >= 500 else "request",
        ),
    )
    return MayaError(message, kind, delay)


def parse_json(data: str) -> dict:
    """Parse a provider object and reject malformed/non-object events without exposing their contents."""
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError("not an object")
        return value
    except (ValueError, TypeError) as exc:
        raise MayaError(
            "The provider returned malformed JSON. The partial answer is kept.", "protocol"
        ) from exc


def error_payload(data: dict) -> MayaError:
    """Normalize in-band stream errors by numeric code; never display a provider's echoed message."""
    raw = data.get("error", {})
    code = raw.get("code", 500) if isinstance(raw, dict) else 500
    try:
        return normalize_http(int(code))
    except (ValueError, TypeError):
        return MayaError(
            "The provider interrupted this response. Check quota/model access and retry.", "server"
        )


class Transport:
    """HTTP sessions scoped to one operation with deadline, close-on-stop, and TLS validation."""

    def __init__(self, base: str, headers: dict[str, str], transport=None):
        """Accept an injectable httpx transport for deterministic integration tests."""
        self.base = validate_url(base)
        self.headers = headers
        self.transport = transport

    def client(self, token: Cancellation) -> httpx.Client:
        """Return a short-lived client; redirects are forbidden so keys cannot follow another host."""
        remaining = max(0.1, token.deadline - time.monotonic())
        return httpx.Client(
            headers=self.headers,
            transport=self.transport,
            timeout=httpx.Timeout(min(30, remaining), connect=min(10, remaining)),
            follow_redirects=False,
            # Do not let unrelated shell proxy/CA variables redirect private provider traffic.
            trust_env=False,
        )

    def get(
        self, path: str, token: Cancellation, params: dict | None = None, body: dict | None = None
    ) -> dict:
        """Fetch bounded JSON with GET or POST for discovery; network errors are normalized."""
        token.check()
        timer = Timer(max(0.1, token.deadline - time.monotonic()), token.cancel)
        timer.daemon = True
        timer.start()
        try:
            with self.client(token) as client:
                with client.stream(
                    "POST" if body is not None else "GET", self.base + path, params=params, json=body
                ) as response:
                    token.bind(response.close)
                    if response.status_code >= 300:
                        raise normalize_http(response.status_code, response.headers.get("retry-after", ""))
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        token.check()
                        data.extend(chunk)
                        if len(data) > 8 * 1024 * 1024:
                            raise MayaError("The model catalog is unexpectedly large.", "protocol")
                    token.check()
                    return parse_json(data.decode("utf-8"))
        except (httpx.HTTPError, OSError, RuntimeError) as exc:
            token.check()
            raise MayaError(
                "Could not connect to the provider. Check network, URL, and firewall settings.", "network"
            ) from exc
        except UnicodeError as exc:
            raise MayaError("The model catalog is not valid UTF-8.", "protocol") from exc
        finally:
            timer.cancel()
            token.bind(None)

    def events(self, path: str, body: dict, token: Cancellation, ndjson: bool = False) -> Iterator[dict]:
        """Stream SSE/NDJSON objects with hard deadline cleanup; no retries occur inside a partial response."""
        token.check()
        timer = Timer(max(0.1, token.deadline - time.monotonic()), token.cancel)
        timer.daemon = True
        timer.start()
        try:
            with self.client(token) as client:
                with client.stream("POST", self.base + path, json=body) as response:
                    token.bind(response.close)
                    if response.status_code >= 300:
                        raise normalize_http(response.status_code, response.headers.get("retry-after", ""))
                    if ndjson:
                        for line in parse_ndjson(response.iter_bytes()):
                            token.check()
                            yield parse_json(line)
                    else:
                        for event in parse_sse(response.iter_bytes()):
                            token.check()
                            if event.data.strip() == "[DONE]":
                                return
                            if event.data.strip():
                                yield parse_json(event.data)
        except (httpx.HTTPError, OSError, RuntimeError) as exc:
            token.check()
            raise MayaError(
                "The connection was interrupted. Your partial answer is kept; retry when connected.",
                "network",
            ) from exc
        finally:
            timer.cancel()
            token.bind(None)


# --- Abstract adapters keep API-specific request and event shapes out of the UI. ---
class BaseProvider(ABC):
    """Consistent catalog/key validation/generation boundary for every supported provider."""

    def __init__(self, name: str, base: str, key: str = "", transport=None):
        """Store only in-memory credentials; configure protocol-specific headers in subclasses."""
        self.name, self.base, self.key = name, base, key
        self.transport_override = transport

    @abstractmethod
    def list_models(self, token: Cancellation) -> list[Model]:
        """Return provider-discovered chat-capable model metadata or raise an actionable MayaError."""
        raise NotImplementedError("Subclasses supply the provider protocol")

    @abstractmethod
    def stream(self, request: Request, token: Cancellation) -> Iterator[StreamEvent]:
        """Yield normalized incremental events; subclasses implement provider protocol details."""
        raise NotImplementedError("Subclasses supply the provider protocol")

    def validate_key(self, token: Cancellation) -> None:
        """Validate credentials through an authenticated discovery request (not a fabricated local check)."""
        self.list_models(token)


class GeminiProvider(BaseProvider):
    """Google GenerateContent REST adapter with native system instructions and inline images."""

    def http(self) -> Transport:
        """Use a header for authentication so keys never enter request URLs."""
        return Transport(self.base, {"x-goog-api-key": self.key}, self.transport_override)

    def list_models(self, token: Cancellation) -> list[Model]:
        """Paginate and keep generateContent models; exclude specialized non-text-output families."""
        models, page, seen = [], "", set()
        while True:
            data = self.http().get(
                "/models", token, {"pageSize": 1000, **({"pageToken": page} if page else {})}
            )
            if not isinstance(data.get("models"), list):
                raise MayaError("Google returned an invalid model catalog.", "protocol")
            for item in data["models"]:
                name = item.get("name", "")
                if (
                    "generateContent" not in item.get("supportedGenerationMethods", [])
                    or not name
                    or any(label in name for label in ("tts", "audio", "image", "robotics", "computer-use"))
                ):
                    continue
                # The list endpoint lacks modality metadata. Gemini text families are documented multimodal;
                # other families stay unknown instead of claiming universal vision support.
                vision = True if name.startswith("models/gemini-") else None
                models.append(
                    Model(
                        name,
                        item.get("displayName", name),
                        self.name,
                        vision,
                        int(item.get("inputTokenLimit", 16384)),
                        int(item.get("outputTokenLimit", 4096)),
                    )
                )
            page = data.get("nextPageToken", "")
            if not page:
                break
            if page in seen or len(seen) >= 50:
                raise MayaError("Google returned a repeated model page. Try Refresh again later.", "protocol")
            seen.add(page)
        return models

    def stream(self, request: Request, token: Cancellation) -> Iterator[StreamEvent]:
        """Convert conversation roles and stream visible text; thought parts are not surfaced."""
        contents = []
        for message in request.messages:
            parts = [{"text": message.text}]
            if message.image:
                parts.append(
                    {
                        "inlineData": {
                            "mimeType": message.image.mime,
                            "data": base64.b64encode(message.image.data).decode(),
                        }
                    }
                )
            contents.append({"role": "model" if message.role == "assistant" else "user", "parts": parts})
        body = {
            "systemInstruction": {"parts": [{"text": request.system}]},
            "contents": contents,
            "generationConfig": {"temperature": request.temperature, "maxOutputTokens": request.max_output},
        }
        model = request.model.id.removeprefix("models/")
        finished = False
        for data in self.http().events(
            f"/models/{quote(model, safe='')}:streamGenerateContent?alt=sse", body, token
        ):
            if "error" in data:
                raise error_payload(data)
            if data.get("promptFeedback", {}).get("blockReason"):
                raise MayaError(
                    "Google blocked this request under its safety policy. Rephrase it for safe assistance.",
                    "safety",
                )
            for candidate in data.get("candidates", [])[:1]:
                for part in candidate.get("content", {}).get("parts", []):
                    if isinstance(part.get("text"), str) and not part.get("thought"):
                        yield StreamEvent("text", part["text"])
                if reason := candidate.get("finishReason"):
                    finished = True
                    mapped = {"STOP": "complete", "MAX_TOKENS": "length"}.get(reason, "safety")
                    yield StreamEvent("finish", mapped)
            if usage := data.get("usageMetadata"):
                yield StreamEvent("usage", data=usage)
        if not finished:
            raise MayaError(
                "Google ended the stream without a completion marker. Your partial answer is kept.",
                "protocol",
            )


def openai_messages(request: Request) -> list[dict]:
    """Encode a single latest image as a data URL; ordinary turns remain plain text."""
    messages = [{"role": "system", "content": request.system}]
    for message in request.messages:
        content = message.text
        if message.image:
            encoded = base64.b64encode(message.image.data).decode()
            content = [
                {"type": "text", "text": message.text},
                {"type": "image_url", "image_url": {"url": f"data:{message.image.mime};base64,{encoded}"}},
            ]
        messages.append({"role": message.role, "content": content})
    return messages


class CompatibleProvider(BaseProvider):
    """OpenAI Chat Completions compatible endpoints; unknown capabilities require manual confirmation."""

    def http(self) -> Transport:
        """Add authentication only when supplied; localhost servers may need no key."""
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        if self.name == "openrouter":
            headers["X-Title"] = "Maya the Helper"
        return Transport(self.base, headers, self.transport_override)

    def list_models(self, token: Cancellation) -> list[Model]:
        """Use /models discovery; compatible metadata can optionally declare modalities and limits."""
        data = self.http().get("/models", token)
        if not isinstance(data.get("data"), list):
            raise MayaError(
                "This endpoint did not return a model list. Enter a model ID manually.", "protocol"
            )
        return [
            Model(
                item["id"],
                item.get("name", item["id"]),
                self.name,
                True if "image" in item.get("input_modalities", []) else None,
                int(item.get("context_length", 16384)),
                int(item.get("max_output_tokens", 4096)),
            )
            for item in data["data"]
            if isinstance(item, dict) and item.get("id")
        ]

    def stream(self, request: Request, token: Cancellation) -> Iterator[StreamEvent]:
        """Consume content deltas, usage, and finish reasons; tool/reasoning deltas are not executed."""
        body = {"model": request.model.id, "messages": openai_messages(request), "stream": True}
        if self.name == "openrouter":
            params = request.model.parameters
            if "temperature" in params:
                body["temperature"] = request.temperature
            if "max_tokens" in params:
                body["max_tokens"] = request.max_output
        else:
            body["max_completion_tokens"] = (
                request.max_output if "api.openai.com" == urlsplit(self.base).hostname else None
            )
            if body["max_completion_tokens"] is None:
                del body["max_completion_tokens"]
                body["max_tokens"] = request.max_output
            # Avoid temperature errors on reasoning models; a generic endpoint cannot guarantee this knob.
        finished = False
        for data in self.http().events("/chat/completions", body, token):
            if "error" in data:
                raise error_payload(data)
            for choice in data.get("choices", [])[:1]:
                delta = choice.get("delta", {}).get("content")
                if isinstance(delta, str):
                    yield StreamEvent("text", delta)
                if reason := choice.get("finish_reason"):
                    finished = True
                    yield StreamEvent(
                        "finish", {"stop": "complete", "length": "length"}.get(reason, "safety")
                    )
            if usage := data.get("usage"):
                yield StreamEvent("usage", data=usage)
        if not finished:
            raise MayaError(
                "The provider ended the stream unexpectedly. Your partial answer is kept.", "protocol"
            )


class OpenRouterProvider(CompatibleProvider):
    """OpenRouter metadata supplies free pricing and image capabilities, unlike generic /models."""

    def validate_key(self, token: Cancellation) -> None:
        """Use /key because the public model catalog alone does not verify credentials."""
        self.http().get("/key", token)

    def list_models(self, token: Cancellation) -> list[Model]:
        """Read capability/pricing metadata; absent prices never imply free access."""
        data = self.http().get("/models", token)
        if not isinstance(data.get("data"), list):
            raise MayaError("OpenRouter returned an invalid model catalog.", "protocol")
        models = []
        for item in data["data"]:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            arch = item.get("architecture") or {}
            if "text" not in arch.get("output_modalities", ["text"]):
                continue
            pricing = item.get("pricing") or {}
            try:
                free = (
                    Decimal(str(pricing.get("prompt", "-1"))) == 0
                    and Decimal(str(pricing.get("completion", "-1"))) == 0
                )
            except InvalidOperation:
                free = False
            models.append(
                Model(
                    item["id"],
                    item.get("name", item["id"]),
                    self.name,
                    "image" in arch.get("input_modalities", []),
                    int(item.get("context_length") or 16384),
                    int((item.get("top_provider") or {}).get("max_completion_tokens") or 4096),
                    free or item["id"].endswith(":free"),
                    tuple(item.get("supported_parameters") or []),
                )
            )
        return models


class AnthropicProvider(BaseProvider):
    """Native Claude Messages adapter; system text is separate from conversational turns."""

    def http(self) -> Transport:
        """Use the documented version header and direct native API authentication."""
        return Transport(
            self.base, {"x-api-key": self.key, "anthropic-version": "2023-06-01"}, self.transport_override
        )

    def list_models(self, token: Cancellation) -> list[Model]:
        """Paginate authenticated model discovery; Claude models support image inputs."""
        models, after, seen = [], "", set()
        while True:
            data = self.http().get("/models", token, {"limit": 100, **({"after_id": after} if after else {})})
            if not isinstance(data.get("data"), list):
                raise MayaError("Anthropic returned an invalid model catalog.", "protocol")
            for item in data["data"]:
                if item.get("id"):
                    # Conservative defaults where this list endpoint does not supply limits.
                    models.append(
                        Model(item["id"], item.get("display_name", item["id"]), self.name, True, 200000, 4096)
                    )
            if not data.get("has_more"):
                return models
            after = data.get("last_id", "")
            if not after or after in seen or len(seen) >= 50:
                raise MayaError("Anthropic returned an invalid model page.", "protocol")
            seen.add(after)

    def stream(self, request: Request, token: Cancellation) -> Iterator[StreamEvent]:
        """Read text_delta events and message_stop; thinking/tool blocks remain unused."""
        messages = []
        for message in request.messages:
            content = [{"type": "text", "text": message.text}]
            if message.image:
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": message.image.mime,
                            "data": base64.b64encode(message.image.data).decode(),
                        },
                    }
                )
            messages.append({"role": message.role, "content": content})
        body = {
            "model": request.model.id,
            "system": request.system,
            "messages": messages,
            "max_tokens": request.max_output,
            "stream": True,
        }
        finished, reason = False, "complete"
        for data in self.http().events("/messages", body, token):
            kind = data.get("type")
            if kind == "error":
                raise error_payload(data)
            if kind == "content_block_delta" and data.get("delta", {}).get("type") == "text_delta":
                yield StreamEvent("text", data["delta"].get("text", ""))
            elif kind == "message_delta":
                stop = data.get("delta", {}).get("stop_reason")
                reason = "length" if stop == "max_tokens" else "safety" if stop == "refusal" else "complete"
                yield StreamEvent("usage", data=data.get("usage", {}))
            elif kind == "message_stop":
                finished = True
                yield StreamEvent("finish", reason)
        if not finished:
            raise MayaError(
                "Anthropic ended the stream unexpectedly. Your partial answer is kept.", "protocol"
            )


class OllamaProvider(BaseProvider):
    """Local Ollama adapter uses /api/tags, /api/show capability discovery, and NDJSON chat."""

    def http(self) -> Transport:
        """Use no cloud credential for the configured local model server."""
        return Transport(self.base, {}, self.transport_override)

    def list_models(self, token: Cancellation) -> list[Model]:
        """List installed models and inspect capabilities; no models are downloaded automatically."""
        data = self.http().get("/api/tags", token)
        if not isinstance(data.get("models"), list):
            raise MayaError("Ollama did not return installed models. Check the server URL.", "protocol")
        models = []
        for item in data["models"]:
            name = item.get("name")
            if not name:
                continue
            info = self.http().get("/api/show", token, body={"model": name})
            metadata = info.get("model_info", {})
            context = next(
                (int(value) for key, value in metadata.items() if key.endswith(".context_length")), 8192
            )
            models.append(
                Model(name, name, self.name, "vision" in info.get("capabilities", []), context, 4096, True)
            )
        return models

    def stream(self, request: Request, token: Cancellation) -> Iterator[StreamEvent]:
        """Stream local visible text and normalized usage; no auto-pull, tools, or shell actions."""
        messages = [{"role": "system", "content": request.system}]
        for message in request.messages:
            item = {"role": message.role, "content": message.text}
            if message.image:
                item["images"] = [base64.b64encode(message.image.data).decode()]
            messages.append(item)
        body = {
            "model": request.model.id,
            "messages": messages,
            "stream": True,
            "options": {"temperature": request.temperature, "num_predict": request.max_output},
        }
        finished = False
        for data in self.http().events("/api/chat", body, token, ndjson=True):
            if "error" in data:
                raise error_payload(data)
            if text := data.get("message", {}).get("content"):
                yield StreamEvent("text", text)
            if data.get("done"):
                finished = True
                yield StreamEvent(
                    "usage",
                    data={key: data[key] for key in ("eval_count", "prompt_eval_count") if key in data},
                )
                yield StreamEvent("finish", "length" if data.get("done_reason") == "length" else "complete")
        if not finished:
            raise MayaError(
                "Ollama stopped without completing. Check the local server and retry.", "protocol"
            )


def create_provider(settings: Settings, key: str, transport=None) -> BaseProvider:
    """Create one explicit adapter; cloud native providers require a key before any request."""
    name = settings.provider
    if name in {"gemini", "openrouter", "anthropic"} and not key:
        raise MayaError("Add your API key in Settings, then refresh the model list.", "credentials")
    if (
        name == "compatible"
        and not key
        and urlsplit(settings.urls[name]).hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise MayaError("This remote compatible endpoint requires an API key.", "credentials")
    classes = {
        "gemini": GeminiProvider,
        "openrouter": OpenRouterProvider,
        "compatible": CompatibleProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
    }
    return classes[name](name, settings.urls[name], key, transport)
