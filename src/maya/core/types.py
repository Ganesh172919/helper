"""Plain data contracts keep networking, persistence, and desktop UI independent."""

from dataclasses import dataclass, field
from threading import Event, Lock, Thread
from collections.abc import Callable
import time


# --- Request/result contracts: providers receive only explicit context. ---
@dataclass(frozen=True)
class Model:
    """Discovered metadata; unknown vision support must be explicitly enabled by the user."""

    id: str
    name: str
    provider: str
    vision: bool | None = None
    context: int = 16384
    output: int = 4096
    free: bool = False
    parameters: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImageAttachment:
    """An in-memory prepared image; never implicitly persisted to the database."""

    data: bytes
    mime: str
    width: int
    height: int
    digest: str


@dataclass
class Message:
    """A local turn; interrupted assistant text stays visible with its state."""

    role: str
    text: str
    status: str = "complete"
    id: int | None = None
    image: ImageAttachment | None = None


@dataclass(frozen=True)
class Request:
    """Immutable generation inputs assembled before a worker starts."""

    model: Model
    system: str
    messages: tuple[Message, ...]
    temperature: float = 0.7
    max_output: int = 4096


@dataclass(frozen=True)
class StreamEvent:
    """Normalized text, usage, or finish event shared by every provider."""

    kind: str
    text: str = ""
    data: dict = field(default_factory=dict)


class MayaError(Exception):
    """An actionable public error containing no raw provider response or key."""

    def __init__(self, message: str, kind: str = "error", retry_after: float = 0):
        """Store a safe message and optional retry delay; callers never log request bodies."""
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after


# --- Cancellation: HTTP resources close away from the UI thread. ---
class Cancellation:
    """Thread-safe request stop/deadline token, with an optional active stream closer."""

    def __init__(self, seconds: float = 120):
        """Create a deadline; seconds bounds retries as well as streaming."""
        self.event = Event()
        self.deadline = time.monotonic() + seconds
        self.lock = Lock()
        self.closer: Callable | None = None

    def bind(self, closer: Callable | None) -> None:
        """Bind/unbind a transport; a late binding immediately observes earlier cancellation."""
        with self.lock:
            self.closer = closer
        if closer and self.event.is_set():
            Thread(target=self._close, args=(closer,), daemon=True).start()

    @staticmethod
    def _close(closer: Callable) -> None:
        """Close a connection best-effort; transport shutdown races are expected."""
        try:
            closer()
        except (OSError, RuntimeError):
            return

    def cancel(self) -> None:
        """Signal stop immediately and close the active response in a daemon cleanup thread."""
        self.event.set()
        with self.lock:
            closer = self.closer
        if closer:
            Thread(target=self._close, args=(closer,), daemon=True).start()

    def check(self) -> None:
        """Raise a typed stop or timeout before a request/chunk/retry is processed."""
        if time.monotonic() >= self.deadline:
            raise MayaError("The request timed out. Try a shorter question or a faster model.", "timeout")
        if self.event.is_set():
            raise MayaError("Generation stopped. Your partial answer is kept.", "cancelled")

    def wait(self, seconds: float) -> None:
        """Wait for bounded backoff while allowing instant cancellation."""
        self.event.wait(min(seconds, max(0, self.deadline - time.monotonic())))
        self.check()
