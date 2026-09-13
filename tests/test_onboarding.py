import asyncio
import ipaddress
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


async def test_submitted_values_are_escaped_in_responses():
    async with OneShotForm() as form:
        async with httpx.AsyncClient() as http:
            response = await http.post(
                form.url, data={"region": "<script>alert(1)</script>", "api_key": KEY}
            )
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
