from __future__ import annotations

from scripts.batch_backtest_windows import output_name, resolve_window_starts


def test_resolve_window_starts_merges_inline_and_file(tmp_path) -> None:
    path = tmp_path / "windows.txt"
    path.write_text("2026-04-26T21:05:00Z\n2026-05-03T21:05:00Z\n", encoding="utf-8")
    values = resolve_window_starts("2026-04-19T21:05:00Z", str(path))
    assert values == [
        "2026-04-19T21:05:00Z",
        "2026-04-26T21:05:00Z",
        "2026-05-03T21:05:00Z",
    ]


def test_output_name_is_filesystem_safe() -> None:
    assert output_name("USD_CAD", "M5", "2026-04-26T21:05:00Z") == "backtest_usd_cad_m5_20260426_210500.json"
