from __future__ import annotations

from oanda_autotrader.endpoints.accounts import AccountsAPI
from oanda_autotrader.endpoints.instruments import InstrumentsAPI


class DummyClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, *, params=None, json_body=None, accept_datetime_format=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "json_body": json_body,
                "accept_datetime_format": accept_datetime_format,
            }
        )
        return {"ok": True}


def test_accounts_endpoints_build_paths() -> None:
    client = DummyClient()
    api = AccountsAPI(client)
    api.list_accounts()
    api.get_account("123")
    api.get_account_summary("456")
    api.get_instruments("789", instruments=["EUR_USD", "USD_CAD"])
    assert client.calls[0]["path"] == "/v3/accounts"
    assert client.calls[1]["path"] == "/v3/accounts/123"
    assert client.calls[2]["path"] == "/v3/accounts/456/summary"
    assert client.calls[3]["path"] == "/v3/accounts/789/instruments"
    assert client.calls[3]["params"] == {"instruments": "EUR_USD,USD_CAD"}


def test_instruments_endpoint_builds_params() -> None:
    client = DummyClient()
    api = InstrumentsAPI(client)
    api.get_candles(
        "EUR_USD",
        price="M",
        granularity="S5",
        count=10,
        smooth=True,
        include_first=False,
        daily_alignment=17,
        alignment_timezone="America/New_York",
        weekly_alignment="Friday",
    )
    call = client.calls[0]
    assert call["path"] == "/v3/instruments/EUR_USD/candles"
    assert call["params"]["price"] == "M"
    assert call["params"]["granularity"] == "S5"
    assert call["params"]["count"] == 10
    assert call["params"]["smooth"] == "true"
    assert call["params"]["includeFirst"] == "false"
    assert call["params"]["dailyAlignment"] == 17
    assert call["params"]["alignmentTimezone"] == "America/New_York"
    assert call["params"]["weeklyAlignment"] == "Friday"
