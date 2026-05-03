from __future__ import annotations

from oanda_autotrader.endpoints.orders import OrdersAPI


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


def test_orders_endpoint_wraps_payload() -> None:
    client = DummyClient()
    api = OrdersAPI(client)
    payload = {
        "type": "MARKET",
        "instrument": "USD_CAD",
        "units": "100",
    }
    api.create_order("abc", payload)
    assert client.calls[0]["method"] == "POST"
    assert client.calls[0]["path"] == "/v3/accounts/abc/orders"
    assert client.calls[0]["json_body"] == {"order": payload}
