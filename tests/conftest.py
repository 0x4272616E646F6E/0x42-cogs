import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


@pytest.fixture
def fake_llm_server():
    """An OpenAI-compatible endpoint that records the JSON bodies it receives.

    Yields a server handle that also unpacks as `(base_url, bodies)`. Set
    `.status` to make the next completion fail the way a real server would.
    """
    bodies = []
    control = {"status": 200}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _respond(self, payload):
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            self._respond({
                "object": "list",
                "data": [
                    {"id": "qwen3:8b", "object": "model"},
                    {"id": "gpt-oss:20b", "object": "model"},
                ],
            })

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            bodies.append(json.loads(self.rfile.read(length) or b"{}"))

            status = control["status"]
            if status == 200:
                body = {
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "test-model",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "ok"},
                        }
                    ],
                }
            else:
                body = {"error": {"message": "refused", "type": "invalid_request_error"}}

            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    yield FakeServer(f"http://127.0.0.1:{server.server_port}/v1", bodies, control)

    server.shutdown()
    server.server_close()


class FakeServer:
    """Unpacks as (url, bodies) for existing tests; `.status` steers failures."""

    def __init__(self, url, bodies, control):
        self.url = url
        self.bodies = bodies
        self._control = control

    @property
    def status(self):
        return self._control["status"]

    @status.setter
    def status(self, value):
        self._control["status"] = value

    def __iter__(self):
        return iter((self.url, self.bodies))
