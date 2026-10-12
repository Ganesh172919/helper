"""Incremental UTF-8 SSE parsing shared by providers, independently testable with split bytes."""

import codecs
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from .types import MayaError


# --- Protocol framing handles comments, CRLF, split Unicode, and multiline fields. ---
@dataclass(frozen=True)
class SSEEvent:
    """One protocol event with its optional event type and combined data lines."""

    event: str
    data: str


def parse_sse(chunks: Iterable[bytes], limit: int = 1048576) -> Iterator[SSEEvent]:
    """Yield complete SSE events; raise MayaError on invalid UTF-8 or oversized events.

    Handles byte-level splits, CRLF/LF/CR newlines, comments, multiline data, and EOF flush.
    [DONE] remains a data value so adapters decide terminal semantics.
    """
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    buffer = ""
    data: list[str] = []
    event = "message"
    size = 0

    def consume(line: str) -> SSEEvent | None:
        """Consume a protocol line and emit only at an event boundary."""
        nonlocal event, size
        if not line:
            result = SSEEvent(event, "\n".join(data)) if data else None
            data.clear()
            event, size = "message", 0
            return result
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            size += len(value)
            if size > limit:
                raise MayaError("The provider sent an oversized stream event.", "protocol")
            data.append(value)
        elif field == "event":
            event = value
        return None

    try:
        for chunk in chunks:
            buffer += decoder.decode(chunk)
            while buffer:
                positions = [pos for pos in (buffer.find("\n"), buffer.find("\r")) if pos >= 0]
                if not positions:
                    break
                pos = min(positions)
                if buffer[pos] == "\r" and pos == len(buffer) - 1:
                    break  # A split CRLF must not create a spurious blank line.
                step = 2 if buffer[pos : pos + 2] == "\r\n" else 1
                line, buffer = buffer[:pos], buffer[pos + step :]
                if result := consume(line):
                    yield result
            if len(buffer) > limit:
                raise MayaError("The provider sent an oversized stream line.", "protocol")
        buffer += decoder.decode(b"", final=True)
        for line in buffer.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            if result := consume(line):
                yield result
        if result := consume(""):
            yield result
    except UnicodeError as exc:
        raise MayaError("The provider sent invalid UTF-8 stream data.", "protocol") from exc


def parse_ndjson(chunks: Iterable[bytes], limit: int = 1048576) -> Iterator[str]:
    """Frame local-model JSON lines incrementally, enforcing a bound before an unclosed line can grow."""
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    buffer = ""
    try:
        for chunk in chunks:
            buffer += decoder.decode(chunk)
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if len(line) > limit:
                    raise MayaError("The local model sent an oversized stream line.", "protocol")
                if line.strip():
                    yield line.strip()
            if len(buffer) > limit:
                raise MayaError("The local model sent an oversized stream line.", "protocol")
        buffer += decoder.decode(b"", final=True)
        if len(buffer) > limit:
            raise MayaError("The local model sent an oversized stream line.", "protocol")
        if buffer.strip():
            yield buffer.strip()
    except UnicodeError as exc:
        raise MayaError("The local model sent invalid UTF-8 stream data.", "protocol") from exc
