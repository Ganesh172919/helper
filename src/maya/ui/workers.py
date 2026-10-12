"""Qt workers marshal immutable network/capture results to the UI with explicit lifecycle control."""

from collections.abc import Callable
import random
import time

from PyQt5.QtCore import QThread, pyqtSignal

from maya.core.types import Cancellation, MayaError


# --- Short jobs and generation jobs have consistent safe error contracts. ---
class Job(QThread):
    """Run catalog/capture operations without blocking the event loop."""

    result = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, task: Callable, token: Cancellation | None = None):
        """Retain a callable and cancellation token until QThread.finished releases the job."""
        super().__init__()
        self.task = task
        self.token = token or Cancellation()

    def run(self) -> None:
        """Emit results/errors through Qt signals; unexpected exception details never reach logs or UI."""
        try:
            self.result.emit(self.task(self.token))
        except MayaError as exc:
            self.error.emit(str(exc))
        except Exception:
            self.error.emit("This operation failed unexpectedly. Check Settings and try again.")


class Generation(QThread):
    """Incremental streaming with bounded retry before any visible output; partial output is never replayed."""

    delta = pyqtSignal(str)
    ended = pyqtSignal(str, str, object)

    def __init__(self, provider, request, retries: int, seconds: int):
        """Snapshot the request/provider and initialize an independent stop token."""
        super().__init__()
        self.provider, self.request, self.retries = provider, request, retries
        self.token = Cancellation(seconds)

    def run(self) -> None:
        """Stream chunks, retry transient pre-output errors, and report latency/finish state once."""
        started, first, chunks = time.monotonic(), None, 0
        usage = {}
        finish = "complete"
        for attempt in range(self.retries + 1):
            try:
                self.token.check()
                for event in self.provider.stream(self.request, self.token):
                    self.token.check()
                    if event.kind == "text" and event.text:
                        first = first or time.monotonic()
                        chunks += 1
                        self.delta.emit(event.text)
                    elif event.kind == "finish":
                        finish = event.text
                    elif event.kind == "usage":
                        usage = event.data
                if not chunks:
                    if finish == "safety":
                        raise MayaError(
                            "The provider withheld this response under its safety rules.", "safety"
                        )
                    raise MayaError(
                        "The provider returned no visible text. Try another model or increase the output limit.",
                        "empty",
                    )
                note = {
                    "length": "Output limit reached. Use Continue for more.",
                    "safety": "The provider ended this response under its safety rules.",
                }.get(finish, "")
                self.ended.emit(
                    finish,
                    note,
                    {
                        "first": first - started if first else None,
                        "total": time.monotonic() - started,
                        "usage": usage,
                    },
                )
                return
            except MayaError as exc:
                if not chunks and attempt < self.retries and exc.kind in {"server", "network", "rate_limit"}:
                    try:
                        self.token.wait(max(exc.retry_after, 0.8 * 2**attempt + random.uniform(0, 0.4)))
                        continue
                    except MayaError as stopped:
                        exc = stopped
                self.ended.emit(
                    "stopped" if exc.kind == "cancelled" else "error",
                    str(exc),
                    {
                        "first": first - started if first else None,
                        "total": time.monotonic() - started,
                        "kind": exc.kind,
                        "usage": usage,
                    },
                )
                return
            except Exception:
                self.ended.emit(
                    "error",
                    "An unexpected provider response interrupted generation. Try refreshing models.",
                    {"total": time.monotonic() - started, "kind": "protocol"},
                )
                return
