"""Loopback HTTP tests check real socket resource behavior separately from mocked API serializers."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Event, Thread
import time
import pytest

from PyQt5.QtTest import QTest

from maya.core.providers import CompatibleProvider, Transport
from maya.core.types import Cancellation, MayaError, Message, Model, Request
from maya.ui.workers import Generation, Job


# --- The test server deliberately goes quiet mid-stream to reproduce blocked socket reads. ---
@pytest.mark.parametrize("end", ["stop", "timeout"])
def test_stop_or_deadline_during_quiet_http_stream(qapp, end):
    """Cancellation must keep the UI responsive and complete even when no new provider chunks arrive."""
    received = Event()
    release = Event()

    class Handler(BaseHTTPRequestHandler):
        """Loopback-only SSE fixture that has no keys, user content, or external effects."""

        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):
            """Suppress test HTTP access logging to keep test output small."""
            return

        def do_POST(self):
            """Send one token and remain quiet until the test releases the server."""
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            data = {"choices": [{"delta": {"content": "partial"}}]}
            self.wfile.write(("data: " + json.dumps(data) + "\n\n").encode())
            self.wfile.flush()
            received.set()
            release.wait(4)
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server_thread = Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    provider = CompatibleProvider("compatible", base)
    request = Request(Model("test", "Test", "compatible"), "Rules", (Message("user", "Explain"),))
    worker = Generation(provider, request, 0, 30 if end == "stop" else 0.5)
    results, deltas = [], []
    worker.ended.connect(lambda *values: results.append(values))
    worker.delta.connect(deltas.append)
    worker.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not deltas:
        qapp.processEvents()
        QTest.qWait(10)
    assert received.is_set() and deltas == ["partial"]
    started = time.monotonic()
    if end == "stop":
        worker.token.cancel()
    while time.monotonic() - started < 2 and worker.isRunning():
        qapp.processEvents()
        QTest.qWait(10)
    elapsed = time.monotonic() - started
    release.set()
    worker.wait(5000)
    qapp.processEvents()
    server.shutdown()
    server.server_close()
    assert not worker.isRunning() and results[0][0] == ("stopped" if end == "stop" else "error")
    if end == "timeout":
        assert results[0][2]["kind"] == "timeout"
    assert elapsed < 2, "Stop must unblock a quiet socket read promptly"
    worker.deleteLater()


@pytest.mark.parametrize("end", ["stop", "timeout"])
def test_quiet_catalog_socket_respects_stop_and_overall_deadline(qapp, end):
    """The classifier's discovery request must also close a stalled socket before its short deadline."""
    received, release = Event(), Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):
            return

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b'{"models":')
            self.wfile.flush()
            received.set()
            release.wait(4)
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    Thread(target=server.serve_forever, daemon=True).start()
    http = Transport(f"http://127.0.0.1:{server.server_address[1]}", {})
    kinds = []

    def task(token):
        try:
            http.get("/models", token)
        except MayaError as exc:
            kinds.append(exc.kind)

    worker = Job(task, Cancellation(30 if end == "stop" else 0.5))
    worker.start()
    deadline = time.monotonic() + 3
    while not received.is_set() and time.monotonic() < deadline:
        qapp.processEvents()
        QTest.qWait(10)
    assert received.is_set()
    started = time.monotonic()
    if end == "stop":
        worker.token.cancel()
    while worker.isRunning() and time.monotonic() - started < 2:
        qapp.processEvents()
        QTest.qWait(10)
    elapsed = time.monotonic() - started
    release.set()
    worker.wait(5000)
    server.shutdown()
    server.server_close()
    qapp.processEvents()
    assert kinds == ["cancelled" if end == "stop" else "timeout"] and elapsed < 2
    worker.deleteLater()
