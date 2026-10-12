"""Mocked HTTP integration exercises real adapters and serializers with no cloud credentials or cost."""

import json

import httpx
import pytest

from maya.core.config import DEFAULT_URLS, Settings
from maya.core.providers import (
    AnthropicProvider,
    CompatibleProvider,
    GeminiProvider,
    OllamaProvider,
    OpenRouterProvider,
    create_provider,
    normalize_http,
)
from maya.core.types import Cancellation, ImageAttachment, MayaError, Message, Model, Request


# --- HTTP fixtures validate wire shapes, not just adapter method return values. ---
def stream_response(events, ndjson=False):
    """Return a realistic SSE or NDJSON response containing comments and terminal events."""
    text = (
        "\n".join(json.dumps(event) for event in events)
        if ndjson
        else (": keepalive\r\n\r\n" + "".join("data: " + json.dumps(event) + "\r\n\r\n" for event in events))
    )
    return httpx.Response(200, content=text.encode(), headers={"content-type": "text/event-stream"})


def request(provider):
    """Use a harmless synthetic image and question to inspect actual outbound request data."""
    image = ImageAttachment(b"fake-image", "image/png", 10, 10, "digest")
    return Request(
        Model(
            "models/test" if provider == "gemini" else "test",
            "Test",
            provider,
            True,
            parameters=("temperature", "max_tokens"),
        ),
        "Fixed system rules",
        (Message("user", "Explain", image=image),),
    )


def test_gemini_pagination_filter_auth_and_stream():
    """Google uses key headers, native systemInstruction, inlineData and candidate text events."""
    calls = []

    def handler(req):
        """Validate Google wire requests and return paginated catalog/stream fixtures."""
        calls.append(req)
        assert req.headers["x-goog-api-key"] == "fake-private-key"
        assert "fake-private-key" not in str(req.url)
        if req.method == "GET":
            if "pageToken" in req.url.params:
                return httpx.Response(
                    200,
                    json={
                        "models": [
                            {"name": "models/embedding", "supportedGenerationMethods": ["embedContent"]}
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-3.8-flash",
                            "displayName": "Flash",
                            "supportedGenerationMethods": ["generateContent"],
                            "inputTokenLimit": 100000,
                            "outputTokenLimit": 10000,
                        }
                    ],
                    "nextPageToken": "page2",
                },
            )
        body = json.loads(req.content)
        assert body["systemInstruction"]["parts"][0]["text"] == "Fixed system rules"
        assert body["contents"][0]["parts"][1]["inlineData"]["mimeType"] == "image/png"
        assert req.url.params["alt"] == "sse"
        return stream_response(
            [
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": "private thought", "thought": True}, {"text": "Hello "}]
                            }
                        }
                    ]
                },
                {"candidates": [{"content": {"parts": [{"text": "world"}]}, "finishReason": "STOP"}]},
            ]
        )

    provider = GeminiProvider(
        "gemini", DEFAULT_URLS["gemini"], "fake-private-key", httpx.MockTransport(handler)
    )
    models = provider.list_models(Cancellation())
    assert len(models) == 1 and models[0].vision
    events = list(provider.stream(request("gemini"), Cancellation()))
    assert "".join(event.text for event in events if event.kind == "text") == "Hello world"
    assert calls[1].url.params["pageToken"] == "page2"


def test_openrouter_free_vision_validation_and_partial_error():
    """Free pricing uses metadata, /key validates access, and an in-band error retains earlier text."""
    calls = []

    def handler(req):
        """Return representative OpenRouter metadata and an interrupted provider stream."""
        calls.append(req.url.path)
        if req.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {"is_free_tier": True}})
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "free-vision",
                            "pricing": {"prompt": "0", "completion": "0"},
                            "architecture": {"input_modalities": ["text", "image"]},
                        },
                        {"id": "paid", "pricing": {"prompt": "0.01", "completion": "0"}},
                        {"id": "unknown"},
                        {"id": "fallback:free"},
                    ]
                },
            )
        body = json.loads(req.content)
        assert body["stream"] is True and body["messages"][1]["content"][1]["type"] == "image_url"
        return stream_response(
            [
                {"choices": [{"delta": {"content": "partial"}}]},
                {"error": {"code": 429, "message": "echo-secret"}},
            ]
        )

    provider = OpenRouterProvider(
        "openrouter", DEFAULT_URLS["openrouter"], "fake", httpx.MockTransport(handler)
    )
    provider.validate_key(Cancellation())
    models = provider.list_models(Cancellation())
    assert [model.id for model in models if model.free] == ["free-vision", "fallback:free"]
    assert not models[2].free and models[0].vision
    iterator = provider.stream(request("openrouter"), Cancellation())
    assert next(iterator).text == "partial"
    with pytest.raises(MayaError) as error:
        list(iterator)
    assert error.value.kind == "rate_limit" and "echo-secret" not in str(error.value)
    assert calls[0].endswith("/key")


@pytest.mark.parametrize(
    "adapter,name,events",
    [
        (
            CompatibleProvider,
            "compatible",
            [
                {"choices": [{"delta": {"content": "Okay"}}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            ],
        ),
        (
            AnthropicProvider,
            "anthropic",
            [
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Okay"}},
                {"type": "message_stop"},
            ],
        ),
        (
            OllamaProvider,
            "ollama",
            [{"message": {"content": "Okay"}}, {"message": {}, "done": True, "eval_count": 1}],
        ),
    ],
)
def test_extension_adapters_stream(adapter, name, events):
    """Dedicated extension adapters genuinely stream their documented protocol formats."""

    def handler(req):
        """Inspect native request shapes and return one finished response."""
        body = json.loads(req.content)
        assert body["stream"]
        if name == "anthropic":
            assert req.headers["anthropic-version"] == "2023-06-01"
            assert body["system"] == "Fixed system rules"
        if name == "ollama":
            assert body["messages"][1]["images"]
        return stream_response(events, ndjson=name == "ollama")

    provider = adapter(name, DEFAULT_URLS[name], "fake", httpx.MockTransport(handler))
    result = list(provider.stream(request(name), Cancellation()))
    assert [event.text for event in result if event.kind == "text"] == ["Okay"]
    assert any(event.kind == "finish" for event in result)


def test_http_error_redaction_no_redirect_and_missing_key():
    """Permanent auth failures are clear, sensitive provider messages are discarded, and redirects fail."""
    settings = Settings()
    with pytest.raises(MayaError, match="API key"):
        create_provider(settings, "")
    assert normalize_http(401).kind == "auth"
    assert normalize_http(429, "7").retry_after == 7
    provider = CompatibleProvider(
        "compatible",
        "https://example.com/v1",
        "fake",
        httpx.MockTransport(
            lambda req: httpx.Response(302, headers={"location": "https://unrelated.example"})
        ),
    )
    with pytest.raises(MayaError):
        provider.list_models(Cancellation())


def test_missing_finish_marker_is_interruption():
    """Truncated responses cannot be reported as completed just because the socket closed."""
    provider = CompatibleProvider(
        "compatible",
        "https://example.com/v1",
        "fake",
        httpx.MockTransport(lambda req: stream_response([{"choices": [{"delta": {"content": "partial"}}]}])),
    )
    with pytest.raises(MayaError, match="unexpectedly"):
        list(provider.stream(request("compatible"), Cancellation()))
