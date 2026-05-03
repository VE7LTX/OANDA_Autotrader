from __future__ import annotations

import responses

from oanda_autotrader.http import OandaHttpClient


@responses.activate
def test_http_client_request_injects_auth_header() -> None:
    client = OandaHttpClient(base_url="https://example.com", token="secret")
    responses.add(
        responses.GET,
        "https://example.com/v3/accounts",
        json={"accounts": []},
        status=200,
    )
    payload = client.request("GET", "/v3/accounts")
    assert payload == {"accounts": []}
    assert responses.calls[0].request.headers["Authorization"] == "Bearer secret"
