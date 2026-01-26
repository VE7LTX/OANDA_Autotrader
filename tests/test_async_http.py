import pytest

from oanda_autotrader.async_http import OandaAsyncHttpClient


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def raise_for_status(self):
        return None

    async def json(self):
        return self._payload


class DummySession:
    def __init__(self):
        self.last_headers = None
        self.last_url = None
        self.last_method = None

    def request(self, *, method, url, params=None, json=None, headers=None):
        self.last_headers = headers
        self.last_url = url
        self.last_method = method
        return DummyResponse({"ok": True})

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_async_http_client_sets_headers():
    client = OandaAsyncHttpClient(base_url="https://example.com", token="secret")
    dummy = DummySession()
    client._session = dummy
    payload = await client.request("GET", "/v3/accounts")
    assert payload["ok"] is True
    assert dummy.last_headers["Authorization"] == "Bearer secret"
