"""
Live dashboard using pygame.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import datetime, timezone

import pygame
import sys

sys.path.insert(0, "src")

from oanda_autotrader.app import build_stream_client, load_account_client, load_instruments_client
from oanda_autotrader.config import load_account_groups, resolve_account_credentials, select_account
from oanda_autotrader.monitor import measure_account_latency
from oanda_autotrader.stream_metrics import StreamMetrics


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


class SharedState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.practice_latency_ms: float | None = None
        self.live_latency_ms: float | None = None
        self.practice_history: list[float] = []
        self.live_history: list[float] = []
        self.live_pl: float | None = None
        self.live_balance: float | None = None
        self.last_summary_ts: float | None = None
        self.instrument_closes: list[float] = []
        self.instrument_times: list[str] = []
        self.instrument_last_close: float | None = None
        self.instrument_last_volume: int | None = None
        self.instrument_last_ts: str | None = None
        self.autoencoder_status: dict | None = None
        self.predictions: dict | None = None
        self.stream_metrics = StreamMetrics(window_seconds=10)

    def update_latency(self, kind: str, value: float, max_points: int) -> None:
        with self.lock:
            if kind == "practice":
                self.practice_latency_ms = value
                self.practice_history.append(value)
                self.practice_history = self.practice_history[-max_points:]
            else:
                self.live_latency_ms = value
                self.live_history.append(value)
                self.live_history = self.live_history[-max_points:]

    def update_summary(self, pl: float | None, balance: float | None) -> None:
        with self.lock:
            self.live_pl = pl
            self.live_balance = balance
            self.last_summary_ts = time.time()

    def update_instrument(self, closes: list[float], times: list[str], last_volume: int | None) -> None:
        with self.lock:
            self.instrument_closes = closes
            self.instrument_times = times
            if closes:
                self.instrument_last_close = closes[-1]
            if times:
                self.instrument_last_ts = times[-1]
            self.instrument_last_volume = last_volume

    def update_autoencoder_status(self, status: dict | None) -> None:
        with self.lock:
            self.autoencoder_status = status

    def update_predictions(self, preds: dict | None) -> None:
        with self.lock:
            self.predictions = preds


def latency_loop(state: SharedState, interval: int, max_points: int) -> None:
    while True:
        try:
            _, ms = measure_account_latency("accounts.yaml", "demo", "Primary")
            state.update_latency("practice", ms, max_points)
            _, ms = measure_account_latency("accounts.yaml", "live", "Primary")
            state.update_latency("live", ms, max_points)
        except Exception:
            pass
        time.sleep(interval)


def summary_loop(state: SharedState, interval: int, group: str, account: str) -> None:
    while True:
        try:
            client = load_account_client("accounts.yaml", group, account)
            groups = load_account_groups("accounts.yaml")
            group_obj, entry = select_account(groups, group, account)
            payload = client.get_account_summary(entry.account_id)
            account = payload.get("account", {})
            pl = float(account.get("pl")) if account.get("pl") is not None else None
            balance = (
                float(account.get("balance")) if account.get("balance") is not None else None
            )
            state.update_summary(pl, balance)
        except Exception:
            pass
        time.sleep(interval)


def instrument_loop(
    state: SharedState,
    interval: int,
    group: str,
    account: str,
    instrument: str,
    history_points: int,
) -> None:
    while True:
        try:
            client = load_instruments_client("accounts.yaml", group, account)
            payload = client.get_candles(
                instrument,
                price="M",
                granularity="S5",
                count=history_points,
            )
            candles = payload.get("candles", [])
            closes = []
            times = []
            last_volume = None
            for candle in candles:
                mid = candle.get("mid") or {}
                close = mid.get("c")
                if close is None:
                    continue
                closes.append(float(close))
                times.append(candle.get("time", ""))
                last_volume = candle.get("volume") or candle.get("v")
            state.update_instrument(closes, times, int(last_volume) if last_volume else None)
        except Exception:
            pass
        time.sleep(interval)


def autoencoder_status_loop(state: SharedState, interval: int, path: str) -> None:
    while True:
        status = None
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as handle:
                    lines = handle.read().strip().splitlines()
                    if lines:
                        status = json.loads(lines[-1])
        except Exception:
            status = None
        state.update_autoencoder_status(status)
        time.sleep(interval)


def predictions_loop(state: SharedState, interval: int, path: str) -> None:
    while True:
        preds = None
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as handle:
                    lines = handle.read().strip().splitlines()
                    if lines:
                        preds = json.loads(lines[-1])
        except Exception:
            preds = None
        state.update_predictions(preds)
        time.sleep(interval)

async def stream_loop(state: SharedState, group: str, account: str, instrument: str) -> None:
    groups = load_account_groups("accounts.yaml")
    group_obj, entry = select_account(groups, group, account)
    config = resolve_account_credentials(group_obj, entry)
    async with build_stream_client(config, on_event=state.stream_metrics.on_event) as stream:
        async for _ in stream.stream_pricing(entry.account_id, [instrument]):
            pass


def draw_graph(screen, values, color, rect):
    if len(values) < 2:
        return
    max_val = max(values) if max(values) > 0 else 1.0
    min_val = min(values)
    span = max(max_val - min_val, 1.0)
    points = []
    for i, value in enumerate(values):
        x = rect.left + int(i * rect.width / max(len(values) - 1, 1))
        y = rect.bottom - int(((value - min_val) / span) * rect.height)
        points.append((x, y))
    pygame.draw.lines(screen, color, False, points, 2)


def draw_grid(screen, rect, rows=5, cols=5, color=(40, 46, 60)):
    for i in range(1, rows):
        y = rect.top + int(i * rect.height / rows)
        pygame.draw.line(screen, color, (rect.left, y), (rect.right, y), 1)
    for i in range(1, cols):
        x = rect.left + int(i * rect.width / cols)
        pygame.draw.line(screen, color, (x, rect.top), (x, rect.bottom), 1)


def draw_axis_labels(
    screen, rect, values, font, *, span_seconds: int, color=(180, 180, 180)
):
    if not values:
        return
    max_val = max(values)
    min_val = min(values)
    span = max(max_val - min_val, 1.0)
    top_label = font.render(f"{max_val:.1f} ms", True, color)
    mid_label = font.render(f"{(min_val + span / 2):.1f} ms", True, color)
    bot_label = font.render(f"{min_val:.1f} ms", True, color)
    screen.blit(top_label, (rect.left + 5, rect.top + 5))
    screen.blit(mid_label, (rect.left + 5, rect.centery - 10))
    screen.blit(bot_label, (rect.left + 5, rect.bottom - 25))

    left_label = font.render("0s", True, color)
    right_label = font.render(f"{span_seconds}s", True, color)
    screen.blit(left_label, (rect.left + 5, rect.bottom + 5))
    screen.blit(right_label, (rect.right - right_label.get_width() - 5, rect.bottom + 5))


def main() -> None:
    interval = _env_int("OANDA_DASHBOARD_LATENCY_INTERVAL", 5)
    max_points = _env_int("OANDA_DASHBOARD_HISTORY", 120)
    instrument = _env("OANDA_DASHBOARD_INSTRUMENT", "USD_CAD")
    stream_group = _env("OANDA_DASHBOARD_GROUP", "live")
    stream_account = _env("OANDA_DASHBOARD_ACCOUNT", "Primary")
    summary_interval = _env_int("OANDA_DASHBOARD_SUMMARY_INTERVAL", 10)
    instrument_interval = _env_int("OANDA_DASHBOARD_CANDLE_INTERVAL", 10)
    instrument_points = _env_int("OANDA_DASHBOARD_CANDLE_POINTS", 120)
    autoencoder_status_path = _env("OANDA_DASHBOARD_AE_STATUS_PATH", "data/ae_status.jsonl")
    autoencoder_status_interval = _env_int("OANDA_DASHBOARD_AE_STATUS_INTERVAL", 5)
    preds_path = _env("OANDA_DASHBOARD_PRED_PATH", "data/predictions.jsonl")
    preds_interval = _env_int("OANDA_DASHBOARD_PRED_INTERVAL", 5)

    state = SharedState()
    start_ts = time.time()
    t = threading.Thread(
        target=latency_loop, args=(state, interval, max_points), daemon=True
    )
    t.start()
    threading.Thread(
        target=summary_loop,
        args=(state, summary_interval, stream_group, stream_account),
        daemon=True,
    ).start()
    threading.Thread(
        target=instrument_loop,
        args=(
            state,
            instrument_interval,
            stream_group,
            stream_account,
            instrument,
            instrument_points,
        ),
        daemon=True,
    ).start()
    threading.Thread(
        target=autoencoder_status_loop,
        args=(state, autoencoder_status_interval, autoencoder_status_path),
        daemon=True,
    ).start()
    threading.Thread(
        target=predictions_loop,
        args=(state, preds_interval, preds_path),
        daemon=True,
    ).start()

    loop = asyncio.new_event_loop()
    threading.Thread(
        target=loop.run_until_complete,
        args=(stream_loop(state, stream_group, stream_account, instrument),),
        daemon=True,
    ).start()

    pygame.init()
    screen = pygame.display.set_mode((1000, 600))
    pygame.display.set_caption("OANDA Dashboard")
    font = pygame.font.SysFont("Consolas", 20)

    clock = pygame.time.Clock()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill((10, 12, 16))
        with state.lock:
            practice = state.practice_latency_ms
            live = state.live_latency_ms
            practice_hist = list(state.practice_history)
            live_hist = list(state.live_history)
            metrics = state.stream_metrics.snapshot()
            closes = list(state.instrument_closes)
            last_close = state.instrument_last_close
            last_vol = state.instrument_last_volume
            last_candle_ts = state.instrument_last_ts
            ae_status = state.autoencoder_status
            preds = state.predictions

        header = font.render("OANDA Live Dashboard", True, (230, 230, 230))
        screen.blit(header, (20, 20))

        line1 = font.render(
            f"Latency (ms)  Practice: {practice:.2f}  Live: {live:.2f}"
            if practice is not None and live is not None
            else "Latency (ms)  Practice: --  Live: --",
            True,
            (200, 200, 200),
        )
        screen.blit(line1, (20, 60))

        line2 = font.render(
            f"Stream {instrument}  msgs/sec: {metrics.messages_per_sec:.2f}  total: {metrics.messages_total}",
            True,
            (200, 200, 200),
        )
        screen.blit(line2, (20, 100))

        uptime_seconds = int(time.time() - start_ts)
        uptime_label = f"{uptime_seconds // 3600:02d}:{(uptime_seconds % 3600) // 60:02d}:{uptime_seconds % 60:02d}"
        last_err = (
            datetime.fromtimestamp(metrics.last_error_ts, tz=timezone.utc).strftime("%H:%M:%S")
            if metrics.last_error_ts
            else "--"
        )
        pl_text = f"{state.live_pl:.2f}" if state.live_pl is not None else "--"
        bal_text = f"{state.live_balance:.2f}" if state.live_balance is not None else "--"
        line3 = font.render(
            f"reconnects: {metrics.reconnect_waits}  errors: {metrics.errors}  last_error: {last_err}  uptime: {uptime_label}",
            True,
            (200, 200, 200),
        )
        screen.blit(line3, (20, 140))

        line4 = font.render(
            f"P&L: {pl_text}  balance: {bal_text}",
            True,
            (200, 200, 200),
        )
        screen.blit(line4, (20, 175))

        graph_rect = pygame.Rect(20, 210, 960, 150)
        pygame.draw.rect(screen, (30, 36, 48), graph_rect)
        draw_grid(screen, graph_rect)
        draw_graph(screen, practice_hist, (80, 200, 120), graph_rect)
        draw_graph(screen, live_hist, (80, 140, 220), graph_rect)
        combined = practice_hist + live_hist
        span_seconds = int(max_points * interval)
        draw_axis_labels(screen, graph_rect, combined, font, span_seconds=span_seconds)

        legend1 = font.render("Practice latency", True, (80, 200, 120))
        legend2 = font.render("Live latency", True, (80, 140, 220))
        screen.blit(legend1, (20, 370))
        screen.blit(legend2, (220, 370))

        price_rect = pygame.Rect(20, 400, 960, 150)
        pygame.draw.rect(screen, (30, 36, 48), price_rect)
        draw_grid(screen, price_rect)
        draw_graph(screen, closes, (230, 190, 80), price_rect)
        all_vals = list(closes)
        pred_points = []
        if preds and "horizon" in preds:
            for item in preds["horizon"]:
                pred_points.append(item["mean"])
                all_vals.extend([item["low"], item["high"]])
        draw_axis_labels(screen, price_rect, all_vals, font, span_seconds=int(instrument_points * instrument_interval))

        if pred_points:
            # Draw prediction band as an expanding cloud.
            lows = [item["low"] for item in preds["horizon"]]
            highs = [item["high"] for item in preds["horizon"]]
            mean_vals = [item["mean"] for item in preds["horizon"]]
            step_px = max(8, int(price_rect.width / max(len(pred_points) + 2, 1)))
            start_x = price_rect.right - (len(pred_points) * step_px) - 10
            # Map to screen coords using full scale.
            min_val = min(all_vals)
            max_val = max(all_vals)
            span = max(max_val - min_val, 1.0)
            points_low = []
            points_high = []
            points_mean = []
            for i, (low, high, mean) in enumerate(zip(lows, highs, mean_vals)):
                x = start_x + i * step_px
                y_low = price_rect.bottom - int(((low - min_val) / span) * price_rect.height)
                y_high = price_rect.bottom - int(((high - min_val) / span) * price_rect.height)
                y_mean = price_rect.bottom - int(((mean - min_val) / span) * price_rect.height)
                points_low.append((x, y_low))
                points_high.append((x, y_high))
                points_mean.append((x, y_mean))
            if points_low and points_high:
                band_surface = pygame.Surface((price_rect.width, price_rect.height), pygame.SRCALPHA)
                shifted_low = [(x - price_rect.left, y - price_rect.top) for x, y in points_low]
                shifted_high = [(x - price_rect.left, y - price_rect.top) for x, y in points_high]
                pygame.draw.polygon(
                    band_surface, (80, 120, 200, 60), shifted_low + list(reversed(shifted_high))
                )
                screen.blit(band_surface, (price_rect.left, price_rect.top))
            if points_mean:
                pygame.draw.lines(screen, (120, 180, 255), False, points_mean, 2)

        price_label = font.render(
            f"{instrument} last: {last_close if last_close is not None else '--'}  vol: {last_vol if last_vol is not None else '--'}  ts: {last_candle_ts or '--'}",
            True,
            (200, 200, 200),
        )
        screen.blit(price_label, (20, 560))

        ae_text = "--"
        if ae_status:
            parts = []
            if "epoch" in ae_status:
                parts.append(f"epoch {ae_status['epoch']}")
            if "loss" in ae_status:
                parts.append(f"loss {ae_status['loss']}")
            if "ts" in ae_status:
                parts.append(f"ts {ae_status['ts']}")
            ae_text = " | ".join(parts) if parts else "--"
        ae_label = font.render(f"AE status: {ae_text}", True, (200, 200, 200))
        screen.blit(ae_label, (20, 585))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


if __name__ == "__main__":
    main()
