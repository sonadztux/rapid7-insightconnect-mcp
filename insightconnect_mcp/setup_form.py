"""One-shot loopback form so the credential never passes through the model context.

The listener binds 127.0.0.1 on an ephemeral port, requires a single-use token, refuses
non-loopback peers, and stops after the first valid submission or the timeout.
"""

import asyncio
import html
import secrets
import socket
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import Any, Self
from urllib.parse import parse_qs, urlparse

from pydantic import SecretStr, ValidationError

from .config import Region, Settings

TIMEOUT = 300.0
MAX_BODY = 8192
# The page loads nothing external and must not be framed by another origin
# (clickjacking the password field) or leak its tokenized URL as a referrer.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'"
    ),
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Rapid7 InsightConnect MCP setup</title>
<style>body{{font-family:system-ui;max-width:34rem;margin:3rem auto;padding:0 1rem}}
label{{display:block;margin:1rem 0 .25rem;font-weight:600}}
input,select{{width:100%;padding:.5rem;font-size:1rem}}
.row{{display:flex;gap:.5rem;align-items:center;margin-top:1rem}}
.row input{{width:auto}} .err{{color:#b00020;font-weight:600}}
button{{margin-top:1.5rem;padding:.6rem 1.2rem;font-size:1rem}}
small{{color:#555;display:block;margin-top:1.5rem}}</style></head>
<body><h1>Rapid7 InsightConnect MCP</h1>
<p class="err">{error}</p>
<form method="post" autocomplete="off">
<label for="region">Region</label>
<select id="region" name="region">{regions}</select>
<label for="api_key">API key</label>
<input id="api_key" name="api_key" type="password" autocomplete="off" required>
<div class="row"><input id="allow_writes" name="allow_writes" type="checkbox">
<label for="allow_writes" style="margin:0">Allow workflow execution and cancellation</label></div>
<button type="submit">Save</button></form>
<small>This page is served only to this machine and closes after you save.
The key is stored with owner-only permissions and is never sent to the model.</small>
</body></html>"""

DONE = """<!doctype html><html><head><meta charset="utf-8"><title>Saved</title>
<style>body{font-family:system-ui;max-width:34rem;margin:3rem auto;padding:0 1rem}</style>
</head><body><h1>Credential received</h1>
<p>You can close this tab and return to your assistant.</p></body></html>"""


@dataclass(frozen=True)
class Submission:
    region: str
    api_key: SecretStr
    allow_writes: bool

    def settings(self) -> Settings:
        return Settings(
            api_key=self.api_key,
            region=self.region,  # type: ignore[arg-type]
            allow_writes=self.allow_writes,
        )


class Rejected(Exception):
    """Carries the status to send back for a submission that was not read."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def read_submission(handler: BaseHTTPRequestHandler) -> Submission:
    if handler.headers.get_all("Transfer-Encoding") or handler.headers.get_all("Content-Type") != [
        "application/x-www-form-urlencoded"
    ]:
        raise Rejected(400, "Malformed submission")
    lengths = handler.headers.get_all("Content-Length") or []
    try:
        # A negative or conflicting length would make read() run to EOF instead of
        # enforcing the cap, since read(-1) means "read until EOF".
        length = int(lengths.pop()) if len(lengths) == 1 else -1
    except ValueError:
        length = -1
    if length < 0:
        raise Rejected(400, "Malformed submission")
    if length > MAX_BODY:
        raise Rejected(413, "Submission is too large")
    body = handler.rfile.read(length)
    if len(body) != length:
        raise Rejected(400, "Incomplete submission")
    try:
        return parse_submission(body)
    except ValueError as error:
        raise Rejected(400, str(error)) from None


def render(error: str = "") -> str:
    options = "".join(
        f'<option value="{region}">{region}</option>'
        for region in Region.__args__  # type: ignore[attr-defined]
    )
    return PAGE.format(error=html.escape(error), regions=options)


def parse_submission(body: bytes) -> Submission:
    fields = parse_qs(body.decode("utf-8", errors="replace"))
    region = (fields.get("region") or [""])[0].strip()
    key = (fields.get("api_key") or [""])[0].strip()
    if region not in Region.__args__:  # type: ignore[attr-defined]
        raise ValueError(f"Unsupported region: {region}")
    if not key:
        raise ValueError("API key is required")
    # A checkbox is absent when unticked; a crafted "allow_writes=false" must stay false.
    writes = (fields.get("allow_writes") or [""])[0].strip().lower()
    submission = Submission(
        region=region,
        api_key=SecretStr(key),
        allow_writes=writes in {"on", "true", "yes", "1"},
    )
    try:
        # Settings applies the stricter format check (printable ASCII, no whitespace);
        # run it now so a bad key re-shows the form instead of spending the one-shot
        # token on a submission that setup() can only fail on afterward.
        submission.settings()
    except ValidationError:
        raise ValueError("API key must be nonempty printable ASCII without whitespace") from None
    return submission


class OneShotForm:
    def __init__(self, timeout: float = TIMEOUT) -> None:
        self.token = secrets.token_urlsafe(32)
        self.timeout = timeout
        self._submission: Submission | None = None
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._deadline = time.monotonic() + timeout
        self._connections: set[socket.socket] = set()
        form = self

        class Server(ThreadingHTTPServer):
            daemon_threads = False

            def get_request(self) -> tuple[socket.socket, Any]:
                connection, address = super().get_request()
                with form._lock:
                    if not form.remaining():
                        connection.close()
                        raise OSError("Setup closed")
                    form._connections.add(connection)
                return connection, address

            def shutdown_request(self, request: Any) -> None:
                with form._lock:
                    form._connections.discard(request)
                super().shutdown_request(request)

        self._server = Server(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._timer = threading.Timer(timeout, self._expire)

    @property
    def url(self) -> str:
        port = self._server.server_address[1]
        return f"http://127.0.0.1:{port}/?t={self.token}"

    def result(self) -> Submission | None:
        return self._submission

    async def __aenter__(self) -> Self:
        self._deadline = time.monotonic() + self.timeout
        self._thread.start()
        self._timer.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._timer.cancel()
        self._expire()
        await asyncio.to_thread(self._server.shutdown)
        await asyncio.to_thread(self._server.server_close)
        self._thread.join()
        self._timer.join()

    def _expire(self) -> None:
        with self._lock:
            self.token = ""
            for connection in self._connections:
                with suppress(OSError):
                    connection.shutdown(socket.SHUT_RDWR)
        self._done.set()

    def remaining(self) -> float:
        """Time left in the window, which covers opening the page as well as submitting."""
        return max(0.0, self._deadline - time.monotonic())

    async def wait(self) -> Submission | None:
        """Block until a valid submission arrives or the window closes."""
        await asyncio.get_running_loop().run_in_executor(None, self._done.wait, self.remaining())
        return self._submission

    def _same_origin(self, handler: BaseHTTPRequestHandler) -> bool:
        """A browser sent here by DNS rebinding carries a foreign Host or Origin.

        Non-browser clients that omit both headers still need the token.
        """
        expected = f"127.0.0.1:{self._server.server_address[1]}"
        hosts = handler.headers.get_all("Host")
        origins = handler.headers.get_all("Origin")
        return hosts in (None, [expected]) and origins in (None, [f"http://{expected}"])

    def _authorized(self, handler: BaseHTTPRequestHandler) -> bool:
        token = self.token
        if not token or not self.remaining() or not self._same_origin(handler):
            return False
        query = parse_qs(urlparse(handler.path).query)
        supplied = (query.get("t") or [""])[0]
        # Compare bytes: compare_digest() raises TypeError on non-ASCII text.
        return handler.client_address[0] in {"127.0.0.1", "::1"} and secrets.compare_digest(
            supplied.encode(), token.encode()
        )

    def _accept(self, submission: Submission) -> bool:
        with self._lock:
            if not self.token or not self.remaining():
                self.token = ""
                return False
            self.token = ""
            self._submission = submission
        return True

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        form = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"
            timeout = 2

            def log_message(self, *args: Any) -> None:
                """Silence request logging; paths carry the single-use token."""

            def send_error(
                self, code: int, message: str | None = None, explain: str | None = None
            ) -> None:
                """Keep the security headers on parser-generated replies (501, 414, ...)."""
                self._reply(code, f"<h1>{code}</h1>")

            def _reply(self, status: int, body: str) -> None:
                payload = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                for name, value in SECURITY_HEADERS.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                authorized = form._authorized(self)
                self._reply(
                    200 if authorized else 403, render() if authorized else "<h1>Forbidden</h1>"
                )

            def do_POST(self) -> None:
                if not form._authorized(self):
                    self._reply(403, "<h1>Forbidden</h1>")
                    return
                try:
                    submission = read_submission(self)
                except Rejected as rejection:
                    self._reply(rejection.status, render(str(rejection)))
                    return
                accepted = form._accept(submission)
                try:
                    self._reply(
                        200 if accepted else 403, DONE if accepted else "<h1>Forbidden</h1>"
                    )
                finally:
                    if accepted:
                        form._done.set()

        return Handler
