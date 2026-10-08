"""A fake Messages API: serves canned responses in order and records what the
harness sent, so the loop can be exercised without an API key or token spend."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import anthropic
import pytest


class FakeAPI:
    def __init__(self, responses: list[dict[str, Any]]):
        self.responses = responses
        self.requests: list[dict[str, Any]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers["Content-Length"]))
                fake.requests.append(json.loads(body))
                if len(fake.requests) > len(fake.responses):
                    self.send_response(500)
                    self.end_headers()
                    return
                payload = json.dumps(fake.responses[len(fake.requests) - 1]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: Any) -> None:
                pass  # keep test output quiet

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def client(self) -> anthropic.Anthropic:
        host, port = self.server.server_address[:2]
        return anthropic.Anthropic(api_key="test-key", base_url=f"http://{host}:{port}", max_retries=0)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def message(stop_reason: str, *content: dict[str, Any]) -> dict[str, Any]:
    """A canned assistant response."""
    return {"id": "msg_x", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": list(content), "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 11, "output_tokens": 7}}


def text(s: str) -> dict[str, Any]:
    return {"type": "text", "text": s}


@pytest.fixture
def fake_api():
    """Starts a FakeAPI with the given responses; the test fails if the harness
    makes more requests than there are responses."""
    started: list[FakeAPI] = []

    def start(*responses: dict[str, Any]) -> FakeAPI:
        api = FakeAPI(list(responses))
        started.append(api)
        return api

    yield start
    for api in started:
        api.close()
        assert len(api.requests) <= len(api.responses), "harness made more requests than canned responses"
