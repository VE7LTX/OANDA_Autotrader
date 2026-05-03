from __future__ import annotations

from oanda_autotrader.state import BotState


def test_state_round_trip(tmp_path) -> None:
    path = tmp_path / "bot_state.json"
    state = BotState(consecutive_failures=2, last_trade_ts=123.0, last_action="buy")
    state.save(str(path))
    loaded = BotState.load(str(path))
    assert loaded.consecutive_failures == 2
    assert loaded.last_trade_ts == 123.0
    assert loaded.last_action == "buy"
