import asyncio
import ipaddress
import socket
import time
from urllib.parse import urlparse

import httpx
import pytest

from insightconnect_mcp.setup_form import MAX_BODY, OneShotForm

KEY = "form-secret-key"


async def test_url_is_loopback_only_with_random_port_and_token():
    async with OneShotForm() as form:
        parsed = urlparse(form.url)
        assert ipaddress.ip_address(parsed.hostname).is_loopback
        assert parsed.port > 0
        assert len(form.token) >= 32


async def test_two_forms_use_different_tokens_and_ports():
    async with OneShotForm() as first, OneShotForm() as second:
        assert first.token != second.token
        assert urlparse(first.url).port != urlparse(second.url).port


async def test_form_page_renders_regions_without_revealing_secrets():
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            page = await http.get(form.url)
    assert page.status_code == 200
    assert 'type="password"' in page.text
    assert 'value="eu"' in page.text
    assert 'autocomplete="off"' in page.text


async def test_responses_forbid_framing_and_foreign_resources():
    async with OneShotForm() as form:
        base = form.url.split("?")[0]
        async with httpx.AsyncClient() as http:
            responses = [
                await http.get(form.url),
                await http.get(base),
                await http.post(form.url, data={"region": "mars", "api_key": KEY}),
            ]
    for response in responses:
        policy = response.headers["Content-Security-Policy"]
        assert "default-src 'none'" in policy
        assert "frame-ancestors 'none'" in policy
        assert "form-action 'self'" in policy
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("token", ["", "wrong-token"])
async def test_wrong_token_is_refused_on_both_methods(token):
    async with OneShotForm() as form:
        base = form.url.split("?")[0]
        async with httpx.AsyncClient() as http:
            assert (await http.get(base, params={"t": token})).status_code == 403
            posted = await http.post(
                base, params={"t": token}, data={"region": "us", "api_key": KEY}
            )
            assert posted.status_code == 403
        assert form.result() is None


async def test_submission_is_captured_and_server_stops():
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            response = await http.post(
                form.url, data={"region": "eu", "api_key": KEY, "allow_writes": "on"}
            )
        assert response.status_code == 200
        assert KEY not in response.text
        submitted = await asyncio.wait_for(form.wait(), timeout=5)

    assert submitted.region == "eu"
    assert submitted.allow_writes is True
    assert submitted.api_key.get_secret_value() == KEY
    with pytest.raises(httpx.HTTPError):
        async with httpx.AsyncClient() as http:
            await http.get(form.url, timeout=2)


async def test_unchecked_write_box_stays_disabled():
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            await http.post(form.url, data={"region": "us", "api_key": KEY})
        assert (await asyncio.wait_for(form.wait(), timeout=5)).allow_writes is False


@pytest.mark.parametrize(
    "payload",
    [
        {"region": "us", "api_key": "   "},
        {"region": "mars", "api_key": KEY},
        {"api_key": KEY},
        {"region": "us"},
        {"region": "us", "api_key": "has a space"},
    ],
)
async def test_invalid_submission_reprompts_without_completing(payload):
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            response = await http.post(form.url, data=payload)
            assert response.status_code == 400
            assert 'type="password"' in response.text
            assert KEY not in response.text
            assert (await http.get(form.url)).status_code == 200
        assert form.result() is None


async def test_timeout_yields_no_submission():
    async with OneShotForm(timeout=0.2) as form:
        async with httpx.AsyncClient() as http:
            assert (await http.get(form.url)).status_code == 200
        assert await form.wait() is None
        assert form.result() is None
    assert form.token == ""
    assert not form._thread.is_alive()
    assert not form._timer.is_alive()
    assert not form._server._threads


def test_expiry_interrupts_existing_connections():
    from unittest.mock import Mock

    form = OneShotForm()
    connection = Mock()
    form._connections.add(connection)
    try:
        form._expire()
        connection.shutdown.assert_called_once_with(socket.SHUT_RDWR)
        assert form.token == ""
        assert form._done.is_set()
    finally:
        form._server.server_close()


@pytest.mark.parametrize("name", ["Host", "Origin"])
def test_duplicate_origin_headers_are_rejected(name):
    from email.message import Message
    from types import SimpleNamespace

    form = OneShotForm()
    try:
        headers = Message()
        value = urlparse(form.url).netloc
        if name == "Origin":
            value = f"http://{value}"
        headers[name] = value
        headers[name] = value
        assert not form._same_origin(SimpleNamespace(headers=headers))
    finally:
        form._server.server_close()


async def test_token_stops_working_after_first_submission():
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            first = await http.post(form.url, data={"region": "eu", "api_key": KEY})
            assert first.status_code == 200
            second = await http.post(
                form.url, data={"region": "us", "api_key": KEY, "allow_writes": "on"}
            )
            assert second.status_code == 403
            assert (await http.get(form.url)).status_code == 403
        submitted = await asyncio.wait_for(form.wait(), timeout=5)
    assert submitted.region == "eu"
    assert submitted.allow_writes is False


async def test_submitted_values_are_escaped_in_responses():
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            response = await http.post(
                form.url, data={"region": "<script>alert(1)</script>", "api_key": KEY}
            )
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


async def test_negative_content_length_does_not_bypass_body_cap():
    """min(length, MAX_BODY) alone would let a negative Content-Length through, since
    read(-1) means "read until EOF" instead of "read nothing"."""
    async with OneShotForm() as form:
        parsed = urlparse(form.url)
        path = f"{parsed.path}?{parsed.query}"
        with socket.create_connection(("127.0.0.1", parsed.port), timeout=5) as sock:
            sock.sendall(f"POST {path} HTTP/1.0\r\nContent-Length: -1\r\n\r\n".encode())
            response = sock.recv(4096)
    assert response.startswith(b"HTTP/1.0 400")
    assert form.result() is None


async def test_shutdown_completes_while_partial_request_is_open():
    async with OneShotForm(timeout=0.2) as form:
        port = urlparse(form.url).port
        stall = socket.create_connection(("127.0.0.1", port))
        try:
            stall.send(b"GET / HTTP/1.1\r\n")  # incomplete headers
            assert await asyncio.wait_for(form.wait(), timeout=5) is None
        finally:
            stall.close()
    # Leaving the context would hang if shutdown blocked on the stalled handler.


async def test_non_ascii_token_is_rejected_and_leaves_the_form_usable():
    """compare_digest() raises TypeError on non-ASCII text, which would kill the request."""
    async with OneShotForm() as form:
        base = form.url.split("?")[0]
        async with httpx.AsyncClient() as http:
            assert (await http.get(f"{base}?t=%C3%A9")).status_code == 403
            assert (await http.get(form.url)).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.invalid"},
        {"Origin": "null"},
        {"Host": "evil.invalid"},  # DNS rebinding reaches the loopback listener
    ],
)
async def test_foreign_origin_or_host_is_rejected_even_with_the_token(headers):
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            response = await http.post(
                form.url, data={"region": "eu", "api_key": KEY}, headers=headers
            )
    assert response.status_code == 403
    assert form.result() is None


async def test_crafted_allow_writes_value_does_not_enable_writes():
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            response = await http.post(
                form.url, data={"region": "eu", "api_key": KEY, "allow_writes": "false"}
            )
        assert response.status_code == 200
        submitted = await asyncio.wait_for(form.wait(), timeout=5)
    assert submitted.allow_writes is False


async def test_oversized_body_is_rejected_instead_of_truncated():
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            response = await http.post(
                form.url, data={"region": "eu", "api_key": KEY, "pad": "x" * MAX_BODY}
            )
    assert response.status_code == 413
    assert form.result() is None


async def test_duplicate_content_length_is_rejected():
    body = b"region=eu&api_key=" + KEY.encode()
    async with OneShotForm() as form:
        parsed = urlparse(form.url)
        head = (
            f"POST {parsed.path}?{parsed.query} HTTP/1.0\r\n"
            f"Content-Length: {len(body)}\r\nContent-Length: 0\r\n\r\n"
        )
        with socket.create_connection(("127.0.0.1", parsed.port), timeout=5) as sock:
            sock.sendall(head.encode() + body)
            response = sock.recv(4096)
    assert response.startswith(b"HTTP/1.0 400")
    assert form.result() is None


async def test_unsupported_methods_keep_the_security_headers():
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            response = await http.request("OPTIONS", form.url)
    assert response.status_code in {405, 501}
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


async def test_a_stalled_connection_does_not_delay_a_real_submission():
    async with OneShotForm(timeout=5) as form:
        port = urlparse(form.url).port
        stall = socket.create_connection(("127.0.0.1", port))
        try:
            stall.send(b"GET / HTTP/1.1\r\nX-Slow: 1\r\n")  # headers never finish
            start = time.monotonic()
            async with httpx.AsyncClient() as http:
                assert (await http.get(form.url, timeout=5)).status_code == 200
            assert time.monotonic() - start < 1
        finally:
            stall.close()


@pytest.mark.parametrize("origin", ["https://{host}", "http://{host}/", "http://{host}/path"])
async def test_origin_must_match_exactly(origin):
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            response = await http.get(
                form.url, headers={"Origin": origin.format(host=urlparse(form.url).netloc)}
            )
            assert response.status_code == 403


def test_accept_is_atomic_and_rejects_expired_token():
    from insightconnect_mcp.setup_form import parse_submission

    form = OneShotForm()
    try:
        submission = parse_submission(b"region=eu&api_key=fake-key")
        assert form._accept(submission) is True
        assert form._accept(submission) is False
    finally:
        form._server.server_close()
    form = OneShotForm(timeout=0)
    try:
        assert form._accept(submission) is False
        assert form.token == ""
    finally:
        form._server.server_close()


@pytest.mark.parametrize(
    "headers,body",
    [
        ([("Content-Length", "24"), ("Content-Length", "24")], b"region=eu&api_key=fake-key"),
        (
            [("Transfer-Encoding", "chunked"), ("Content-Length", "24")],
            b"region=eu&api_key=fake-key",
        ),
        ([("Content-Type", "text/plain"), ("Content-Length", "24")], b"region=eu&api_key=fake-key"),
        ([("Content-Length", "30")], b"region=eu&api_key=fake-key"),
    ],
)
def test_malformed_submission_framing(headers, body):
    from email.message import Message
    from io import BytesIO
    from types import SimpleNamespace

    from insightconnect_mcp.setup_form import Rejected, read_submission

    message = Message()
    if not any(name == "Content-Type" for name, _ in headers):
        message["Content-Type"] = "application/x-www-form-urlencoded"
    for name, value in headers:
        message[name] = value
    handler = SimpleNamespace(headers=message, rfile=BytesIO(body))
    with pytest.raises(Rejected):
        read_submission(handler)


async def test_the_window_covers_the_whole_setup_not_just_the_wait():
    async with OneShotForm(timeout=0.3) as form:
        await asyncio.sleep(0.35)  # stands in for a slow client prompt
        start = time.monotonic()
        assert await form.wait() is None
        assert time.monotonic() - start < 0.2
