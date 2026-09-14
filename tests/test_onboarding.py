import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
import pytest

from rapid7_insightconnect_mcp.onboarding import OneShotForm

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
        assert await form.wait() is None
        assert form.result() is None


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
