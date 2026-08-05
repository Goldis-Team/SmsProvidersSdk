"""A real HTTP server that every provider test runs against.

There is no mocking library anywhere in this suite. An in-process mock will accept a request no
server would: an unencoded body, a field the provider dispatches on quietly missing, an ``int``
where ``aiohttp`` demands a string. This server sees exactly what the SDK put on the wire, and both
engines are held to the same bytes.

Each provider's URL template is repointed at this server. It is patched where it is *used* — in
``helpers``, which builds the URL at call time — because a module-level ``from … import BASE_URL``
binds the value at import time, so patching the ``constants`` module alone would change nothing.
"""

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs

import pytest

from sms_providers_sdk.providers.kavenegar import helpers as kavenegar_helpers
from sms_providers_sdk.providers.smsir import helpers as smsir_helpers

KAVENEGAR_TEMPLATE = "/v1/{api_key}/{scope}/{method}.json"
"""Kavenegar's URL shape, kept identical to the real one so the tests exercise the same path
building — including the API key sitting in the path, which is what the redaction tests check."""

SMSIR_PREFIX = "/v1"
"""SMS.ir's base path. Its credential travels in a header, so the path carries nothing secret."""


@dataclass
class Exchange:
    """One request the server actually received."""

    path: str
    headers: dict[str, str]
    body: bytes

    @property
    def form(self) -> dict[str, str]:
        """The form-encoded body, one value per field.

        ``parse_qs`` returns lists; every field these providers take is single-valued, so the tests
        read scalars. ``keep_blank_values`` is on so that a field sent as empty shows up as an
        empty string rather than vanishing — "was it omitted or sent blank?" is a real distinction
        when a provider treats the two differently.
        """
        parsed = parse_qs(self.body.decode(), keep_blank_values=True)
        return {key: values[0] for key, values in parsed.items()}

    @property
    def json(self) -> dict[str, Any]:
        """The JSON body, for the providers that send one."""
        return dict(json.loads(self.body.decode() or "{}"))


@dataclass
class Reply:
    """What the server should answer with."""

    payload: Any = field(default_factory=dict[str, Any])
    status: int = 200
    raw_text: str | None = None
    content_type: str = "application/json"


class Stub:
    """Controls the server: what it answers, and what it saw."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.exchanges: list[Exchange] = []
        self.replies: dict[str, Reply] = {}
        self.lock = threading.Lock()

    def reply(self, fragment: str, payload: Any, *, status: int = 200) -> None:
        """Answer any path *containing* ``fragment`` with this JSON body.

        A fragment rather than the whole path, because two of the three providers put the API key
        in the URL and every test would otherwise have to spell it out — Kavenegar in the middle
        of the path, Melipayamak as the last segment, which is why this cannot be a suffix match.
        """
        self.replies[fragment] = Reply(payload=payload, status=status)

    def reply_text(self, fragment: str, text: str, *, status: int = 200) -> None:
        """Answer ``fragment`` with a body that is not JSON at all."""
        self.replies[fragment] = Reply(raw_text=text, status=status, content_type="text/html")

    def last(self, fragment: str | None = None) -> Exchange:
        matching = [e for e in self.exchanges if fragment is None or fragment in e.path]
        assert matching, f"no request was made to {fragment!r} (saw {self.paths})"
        return matching[-1]

    @property
    def paths(self) -> list[str]:
        return [e.path for e in self.exchanges]


def _make_handler(stub: Stub) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            """Silence the server's stderr logging so pytest output stays readable."""

        def do_POST(self) -> None:  # BaseHTTPRequestHandler's required method name
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length)
            with stub.lock:
                stub.exchanges.append(
                    Exchange(
                        path=self.path,
                        headers={k.lower(): v for k, v in self.headers.items()},
                        body=body,
                    )
                )
            reply = next((r for fragment, r in stub.replies.items() if fragment in self.path), None)
            if reply is None:
                payload = b'{"error": "no stubbed reply"}'
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return

            text = reply.raw_text if reply.raw_text is not None else json.dumps(reply.payload)
            encoded = text.encode()
            self.send_response(reply.status)
            self.send_header("Content-Type", reply.content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return Handler


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> Iterator[Stub]:
    """A live HTTP server with every provider's endpoints pointed at it."""
    controller = Stub("")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(controller))
    controller.base_url = f"http://127.0.0.1:{server.server_address[1]}"

    server.daemon_threads = True
    # `shutdown()` only returns once `serve_forever` notices, which it does at the poll interval.
    # The default 0.5s is charged to every single test's teardown — half a minute across a suite
    # this size, for a server that has nothing left to do.
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.daemon = True
    thread.start()

    monkeypatch.setattr(kavenegar_helpers, "BASE_URL", f"{controller.base_url}{KAVENEGAR_TEMPLATE}")
    monkeypatch.setattr(smsir_helpers, "BASE_URL", f"{controller.base_url}{SMSIR_PREFIX}")

    try:
        yield controller
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
