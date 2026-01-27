from oanda_autotrader.trade_latency_gate import TradeLatencyGate, TradeLatencyGateConfig, suggest_thresholds


def test_gate_blocks_until_min_samples() -> None:
    gate = TradeLatencyGate(TradeLatencyGateConfig(mode="live", instrument="USD_CAD"))
    gate.update(10.0, backlog=False, outlier=False, skew_ms=None)
    assert gate.state.blocked is True


def test_gate_unblocks_after_good_streak() -> None:
    cfg = TradeLatencyGateConfig(mode="live", instrument="USD_CAD")
    cfg.min_samples = 1
    gate = TradeLatencyGate(cfg)
    for _ in range(cfg.consecutive_good_to_unblock):
        gate.update(10.0, backlog=False, outlier=False, skew_ms=None)
    assert gate.state.blocked is False


def test_gate_blocks_on_backlog() -> None:
    cfg = TradeLatencyGateConfig(mode="live", instrument="USD_CAD")
    cfg.min_samples = 1
    gate = TradeLatencyGate(cfg)
    for _ in range(cfg.consecutive_backlog_to_block):
        gate.update(cfg.backlog_block_ms + 1, backlog=True, outlier=False, skew_ms=None)
    assert gate.state.blocked is True


def test_suggest_thresholds_clamps() -> None:
    warn, block = suggest_thresholds(
        [10, 20, 30, 40, 50],
        warn_min=800,
        warn_max=2500,
        block_min=250,
        block_max=750,
    )
    assert warn == 800
    assert block == 250
