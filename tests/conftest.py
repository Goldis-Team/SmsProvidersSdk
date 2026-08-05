import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs

import pytest

from sms_providers_sdk.providers.kavenegar import helpers as kavenegar_helpers
from sms_providers_sdk.providers.melipayamak import helpers as melipayamak_helpers
from sms_providers_sdk.providers.smsir import helpers as smsir_helpers

KAVENEGAR_TEMPLATE = "/v1/{api_key}/{scope}/{method}.json"

SMSIR_PREFIX = "/v1"
"""SMS.ir's base path. Its credential travels in a header, so the path carries nothing secret."""

MELIPAYAMAK_PREFIX = "/api"
"""Melipayamak's base path. Its key is the last segment of every path, as with Kavenegar."""


@dataclass
class Exchange:
    """One request the server actually received."""

    path: str
    headers: dict[str, str]
    body: bytes

    @property
    def form(self) -> dict[str, str]:
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

        def do_POST(self) -> None:
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
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.daemon = True
    thread.start()

    monkeypatch.setattr(kavenegar_helpers, "BASE_URL", f"{controller.base_url}{KAVENEGAR_TEMPLATE}")
    monkeypatch.setattr(smsir_helpers, "BASE_URL", f"{controller.base_url}{SMSIR_PREFIX}")
    monkeypatch.setattr(
        melipayamak_helpers, "BASE_URL", f"{controller.base_url}{MELIPAYAMAK_PREFIX}"
    )

    try:
        yield controller
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
