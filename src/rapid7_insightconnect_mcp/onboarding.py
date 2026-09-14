"""One-shot loopback form so the credential never passes through the model context.

The listener binds 127.0.0.1 on an ephemeral port, requires a single-use token, refuses
non-loopback peers, and stops after the first valid submission or the timeout.
"""

import asyncio
import html
import secrets
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
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
    submission = Submission(
        region=region,
        api_key=SecretStr(key),
        allow_writes=bool(fields.get("allow_writes")),
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
        self._server = HTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        port = self._server.server_address[1]
        return f"http://127.0.0.1:{port}/?t={self.token}"

    def result(self) -> Submission | None:
        return self._submission

    async def __aenter__(self) -> Self:
        self._thread.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # shutdown() blocks until serve_forever exits; keep it off the event loop.
        await asyncio.get_running_loop().run_in_executor(None, self._server.shutdown)
        self._server.server_close()

    async def wait(self) -> Submission | None:
        """Block until a valid submission arrives or the window closes."""
        await asyncio.get_running_loop().run_in_executor(None, self._done.wait, self.timeout)
        return self._submission

    def _authorized(self, handler: BaseHTTPRequestHandler) -> bool:
        if not self.token:
            return False
        query = parse_qs(urlparse(handler.path).query)
        supplied = (query.get("t") or [""])[0]
        return handler.client_address[0] in {"127.0.0.1", "::1"} and secrets.compare_digest(
            supplied, self.token
        )

    def _accept(self, submission: Submission) -> None:
        self._submission = submission
        self.token = ""
        self._done.set()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        form = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"
            timeout = 2

            def log_message(self, *args: Any) -> None:
                """Silence request logging; paths carry the single-use token."""

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
                if not form._authorized(self):
                    self._reply(403, "<h1>Forbidden</h1>")
                    return
                self._reply(200, render())

            def do_POST(self) -> None:
                if not form._authorized(self):
                    self._reply(403, "<h1>Forbidden</h1>")
                    return
                raw = self.headers.get("Content-Length") or ""
                try:
                    length = int(raw)
                except ValueError:
                    length = 0
                # A negative value would make read() block for the whole body instead
                # of enforcing the cap, since read(-1) means "read until EOF".
                length = max(0, min(length, MAX_BODY))
                try:
                    submission = parse_submission(self.rfile.read(length))
                except ValueError as error:
                    self._reply(400, render(str(error)))
                    return
                self._reply(200, DONE)
                form._accept(submission)

        return Handler
