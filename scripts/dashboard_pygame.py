"""
Live dashboard using pygame.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from datetime import datetime, timezone

import pygame
import sys

sys.path.insert(0, "src")

from oanda_autotrader.app import build_stream_client, load_account_client
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

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


if __name__ == "__main__":
    main()
