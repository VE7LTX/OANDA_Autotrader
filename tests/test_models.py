from oanda_autotrader.models import parse_stream_message, PriceMessage, TransactionMessage, HeartbeatMessage


def test_parse_price_message() -> None:
    payload = {"type": "PRICE", "instrument": "EUR_USD", "time": "2026-01-01T00:00:00Z"}
    msg = parse_stream_message(payload)
    assert isinstance(msg, PriceMessage)
    assert msg.instrument == "EUR_USD"


def test_parse_transaction_message() -> None:
    payload = {"type": "TRANSACTION", "id": "123", "accountID": "abc"}
    msg = parse_stream_message(payload)
    assert isinstance(msg, TransactionMessage)
    assert msg.transaction_id == "123"


def test_parse_heartbeat_message() -> None:
    payload = {"type": "HEARTBEAT", "time": "2026-01-01T00:00:00Z"}
    msg = parse_stream_message(payload)
    assert isinstance(msg, HeartbeatMessage)
    assert msg.time == "2026-01-01T00:00:00Z"
