from __future__ import annotations

from scripts.optimize_strategy_settings import aggregate_summaries, score_summary


def test_aggregate_summaries_combines_rows() -> None:
    summary = aggregate_summaries(
        [
            {
                "trade_count": 10,
                "wins": 4,
                "losses": 6,
                "gross_pnl": 1.0,
                "net_pnl": 0.5,
                "max_drawdown": -0.2,
            },
            {
                "trade_count": 5,
                "wins": 3,
                "losses": 2,
                "gross_pnl": 0.7,
                "net_pnl": 0.3,
                "max_drawdown": -0.1,
            },
        ]
    )
    assert summary["trade_count"] == 15
    assert summary["wins"] == 7
    assert summary["losses"] == 8
    assert summary["net_pnl"] == 0.8
    assert summary["win_rate"] == 7 / 15
    assert summary["max_drawdown"] == -0.2


def test_score_summary_prefers_positive_pnl_and_lower_drawdown() -> None:
    stronger = score_summary(
        {"trade_count": 12, "net_pnl": 0.5, "win_rate": 0.5, "expectancy": 0.04, "max_drawdown": -0.1},
        target_win_rate=0.6,
        min_trades=8,
    )
    weaker = score_summary(
        {"trade_count": 12, "net_pnl": -0.1, "win_rate": 0.6, "expectancy": -0.01, "max_drawdown": -0.4},
        target_win_rate=0.6,
        min_trades=8,
    )
    assert stronger > weaker
