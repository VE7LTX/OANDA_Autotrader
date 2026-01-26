"""
Live dashboard using pygame.
"""

from __future__ import annotations

import asyncio
import json
import os
import atexit
import threading
import time
import traceback
from datetime import datetime, timezone
import subprocess
from pathlib import Path

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


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
    if "." in raw:
        head, frac = raw.split(".", 1)
        frac = frac[:6].ljust(6, "0")
        raw = f"{head}.{frac}"
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _fmt_float(value: float | None, precision: int = 5) -> str:
    if value is None:
        return "--"
    return f"{value:.{precision}f}"


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
        self.instrument_candles: list[dict] = []
        self.instrument_times: list[str] = []
        self.instrument_last_close: float | None = None
        self.instrument_last_volume: int | None = None
        self.instrument_last_ts: str | None = None
        self.autoencoder_status: dict | None = None
        self.predictions: dict | None = None
        self.recon: dict | None = None
        self.recon_history: list[float] = []
        self.recon_std_error: float | None = None
        self.recon_k: float = 1.5
        self.pred_scores: dict | None = None
        self.stream_metrics = StreamMetrics(window_seconds=10)
        self.candle_interval = 5
        self.max_candles = 120
        self._bucket_start: float | None = None
        self._bucket: dict | None = None

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

    def update_instrument(
        self, candles: list[dict], times: list[str], last_volume: int | None
    ) -> None:
        with self.lock:
            self.instrument_candles = candles
            self.instrument_times = times
            if candles:
                self.instrument_last_close = candles[-1]["c"]
            if times:
                self.instrument_last_ts = times[-1]
            self.instrument_last_volume = last_volume

    def update_autoencoder_status(self, status: dict | None) -> None:
        with self.lock:
            self.autoencoder_status = status

    def update_predictions(self, preds: dict | None) -> None:
        with self.lock:
            self.predictions = preds

    def update_recon(self, recon: dict | None) -> None:
        with self.lock:
            self.recon = recon
            if recon and "recon" in recon:
                self.recon_history.append(float(recon["recon"]))
                self.recon_history = self.recon_history[-self.max_candles :]
                if "std_error" in recon:
                    self.recon_std_error = float(recon["std_error"])
                if "k" in recon:
                    self.recon_k = float(recon["k"])

    def update_scores(self, scores: dict | None) -> None:
        with self.lock:
            self.pred_scores = scores

    def update_tick(self, price: float, ts: float) -> None:
        with self.lock:
            if self._bucket_start is None:
                self._bucket_start = ts - (ts % self.candle_interval)
                self._bucket = {"o": price, "h": price, "l": price, "c": price, "v": 1, "ts": self._bucket_start}
                return
            if ts >= self._bucket_start + self.candle_interval:
                if self._bucket:
                    self.instrument_candles.append(self._bucket)
                    self.instrument_candles = self.instrument_candles[-self.max_candles :]
                    self.instrument_last_close = self._bucket["c"]
                    self.instrument_last_ts = datetime.fromtimestamp(self._bucket_start, tz=timezone.utc).isoformat()
                    self.instrument_last_volume = self._bucket["v"]
                self._bucket_start = ts - (ts % self.candle_interval)
                self._bucket = {"o": price, "h": price, "l": price, "c": price, "v": 1, "ts": self._bucket_start}
                return
            if self._bucket:
                self._bucket["c"] = price
                self._bucket["h"] = max(self._bucket["h"], price)
                self._bucket["l"] = min(self._bucket["l"], price)
                self._bucket["v"] += 1


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


def load_latest_prediction(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().strip().splitlines()
            for line in reversed(lines):
                if not line:
                    continue
                candidate = json.loads(line)
                if "horizon_secs" not in candidate or "horizon" not in candidate:
                    continue
                return candidate
    except Exception:
        return None
    return None


def _log_dashboard_event(message: str) -> None:
    path = os.getenv("OANDA_DASHBOARD_LOG_PATH", "data/dashboard.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def _log_dashboard_json(event: str, payload: dict) -> None:
    path = os.getenv("OANDA_DASHBOARD_LOG_PATH", "data/dashboard.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = json.dumps({"ts": stamp, "event": event, **payload}, ensure_ascii=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def build_prediction_command(
    *,
    script_path: str,
    features_path: str,
    retrain_interval: int,
    epochs: int,
    horizon: int,
    interval_secs: int,
    archive: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        script_path,
        "--features",
        features_path,
        "--retrain-interval",
        str(retrain_interval),
        "--epochs",
        str(epochs),
        "--horizon",
        str(horizon),
        "--interval-secs",
        str(interval_secs),
    ]
    if archive:
        cmd.append("--archive-predictions")
    return cmd


def build_score_command(*, script_path: str, every_seconds: int) -> list[str]:
    return [
        sys.executable,
        script_path,
        "--watch",
        "--every",
        str(every_seconds),
    ]


def start_dashboard_processes() -> list[subprocess.Popen]:
    processes: list[subprocess.Popen] = []
    if not _env_bool("OANDA_DASHBOARD_AUTOSTART", True):
        return processes

    repo_root = Path(__file__).resolve().parents[1]
    pred_script = str(repo_root / "scripts" / "train_autoencoder_loop.py")
    score_script = str(repo_root / "scripts" / "score_predictions.py")
    pred_features = _env("OANDA_DASHBOARD_PRED_FEATURES", "data/usd_cad_features.jsonl")
    pred_interval = _env_int("OANDA_DASHBOARD_PRED_INTERVAL_SECS", 5)
    pred_horizon = _env_int("OANDA_DASHBOARD_PRED_HORIZON", 12)
    pred_epochs = _env_int("OANDA_DASHBOARD_PRED_EPOCHS", 1)
    pred_retrain = _env_int("OANDA_DASHBOARD_PRED_RETRAIN_INTERVAL", 60)
    pred_archive = _env_bool("OANDA_DASHBOARD_PRED_ARCHIVE", False)
    score_every = _env_int("OANDA_DASHBOARD_SCORE_EVERY", 10)

    pred_log = _env("OANDA_DASHBOARD_PRED_LOG", "data/prediction_runner.log")
    score_log = _env("OANDA_DASHBOARD_SCORE_LOG", "data/score_runner.log")

    pred_cmd = build_prediction_command(
        script_path=pred_script,
        features_path=pred_features,
        retrain_interval=pred_retrain,
        epochs=pred_epochs,
        horizon=pred_horizon,
        interval_secs=pred_interval,
        archive=pred_archive,
    )
    score_cmd = build_score_command(script_path=score_script, every_seconds=score_every)

    os.makedirs(os.path.dirname(pred_log), exist_ok=True)
    os.makedirs(os.path.dirname(score_log), exist_ok=True)
    pred_handle = open(pred_log, "a", encoding="utf-8")
    score_handle = open(score_log, "a", encoding="utf-8")

    _log_dashboard_json("dashboard_autostart", {"pred_cmd": pred_cmd, "score_cmd": score_cmd})
    processes.append(
        subprocess.Popen(pred_cmd, stdout=pred_handle, stderr=pred_handle, cwd=str(repo_root))
    )
    processes.append(
        subprocess.Popen(score_cmd, stdout=score_handle, stderr=score_handle, cwd=str(repo_root))
    )
    return processes


def stop_dashboard_processes(processes: list[subprocess.Popen]) -> None:
    for proc in processes:
        try:
            proc.terminate()
        except Exception:
            continue


def predictions_loop(state: SharedState, interval: int, path: str) -> None:
    while True:
        preds = load_latest_prediction(path)
        state.update_predictions(preds)
        time.sleep(interval)


def recon_loop(state: SharedState, interval: int, path: str) -> None:
    while True:
        recon = None
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as handle:
                    lines = handle.read().strip().splitlines()
                    if lines:
                        recon = json.loads(lines[-1])
        except Exception:
            recon = None
        state.update_recon(recon)
        time.sleep(interval)


def scores_loop(state: SharedState, interval: int, path: str) -> None:
    while True:
        scores = None
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as handle:
                    lines = handle.read().strip().splitlines()
                    if lines:
                        scores = json.loads(lines[-1])
        except Exception:
            scores = None
        state.update_scores(scores)
        time.sleep(interval)

async def stream_loop(state: SharedState, group: str, account: str, instrument: str) -> None:
    groups = load_account_groups("accounts.yaml")
    group_obj, entry = select_account(groups, group, account)
    config = resolve_account_credentials(group_obj, entry)
    async with build_stream_client(config, on_event=state.stream_metrics.on_event) as stream:
        async for msg in stream.stream_pricing(entry.account_id, [instrument]):
            payload = msg.raw if hasattr(msg, "raw") else msg
            if payload.get("type") != "PRICE":
                continue
            bids = payload.get("bids") or []
            asks = payload.get("asks") or []
            if not bids or not asks:
                continue
            bid = float(bids[0].get("price"))
            ask = float(asks[0].get("price"))
            mid = (bid + ask) / 2.0
            ts = time.time()
            state.update_tick(mid, ts)


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


def draw_candles(screen, candles, rect, *, min_val: float, max_val: float):
    if len(candles) < 2:
        return
    span = max(max_val - min_val, max_val * 0.002, 1e-6)
    candle_width = max(2, int(rect.width / max(len(candles), 1)) - 2)
    for i, c in enumerate(candles):
        x = rect.left + int(i * rect.width / max(len(candles), 1))
        y_high = rect.bottom - int(((c["h"] - min_val) / span) * rect.height)
        y_low = rect.bottom - int(((c["l"] - min_val) / span) * rect.height)
        y_open = rect.bottom - int(((c["o"] - min_val) / span) * rect.height)
        y_close = rect.bottom - int(((c["c"] - min_val) / span) * rect.height)
        color = (80, 200, 120) if c["c"] >= c["o"] else (220, 80, 80)
        pygame.draw.line(screen, color, (x + candle_width // 2, y_high), (x + candle_width // 2, y_low), 1)
        body_top = min(y_open, y_close)
        body_h = abs(y_close - y_open)
        min_body_px = 4
        if body_h < min_body_px:
            mid = int((y_open + y_close) / 2)
            body_top = mid - (min_body_px // 2)
            body_h = min_body_px
        pygame.draw.rect(screen, color, pygame.Rect(x, body_top, candle_width, body_h))


def draw_dashed_line(screen, points, color, dash_length=6):
    if len(points) < 2:
        return
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        dx = x2 - x1
        dy = y2 - y1
        dist = max((dx * dx + dy * dy) ** 0.5, 1.0)
        steps = int(dist // dash_length)
        for s in range(0, steps, 2):
            t1 = s / steps
            t2 = min((s + 1) / steps, 1.0)
            sx = x1 + dx * t1
            sy = y1 + dy * t1
            ex = x1 + dx * t2
            ey = y1 + dy * t2
            pygame.draw.line(screen, color, (sx, sy), (ex, ey), 1)


def draw_grid(screen, rect, rows=5, cols=5, color=(40, 46, 60)):
    for i in range(1, rows):
        y = rect.top + int(i * rect.height / rows)
        pygame.draw.line(screen, color, (rect.left, y), (rect.right, y), 1)
    for i in range(1, cols):
        x = rect.left + int(i * rect.width / cols)
        pygame.draw.line(screen, color, (x, rect.top), (x, rect.bottom), 1)


def draw_axis_labels(
    screen,
    rect,
    values,
    font,
    *,
    span_seconds: int,
    unit: str | None = None,
    precision: int = 1,
    align_right: bool = False,
    show_time: bool = True,
    color=(180, 180, 180),
):
    if not values:
        return
    max_val = max(values)
    min_val = min(values)
    span = max(max_val - min_val, 1.0)
    suffix = f" {unit}" if unit else ""
    fmt = f"{{:.{precision}f}}"
    top_label = font.render(f"{fmt.format(max_val)}{suffix}", True, color)
    mid_label = font.render(f"{fmt.format(min_val + span / 2)}{suffix}", True, color)
    bot_label = font.render(f"{fmt.format(min_val)}{suffix}", True, color)
    inset = 6
    if align_right:
        screen.blit(top_label, (rect.right - top_label.get_width() - inset, rect.top + inset))
        screen.blit(mid_label, (rect.right - mid_label.get_width() - inset, rect.centery - 10))
        screen.blit(bot_label, (rect.right - bot_label.get_width() - inset, rect.bottom - 25))
    else:
        screen.blit(top_label, (rect.left + inset, rect.top + inset))
        screen.blit(mid_label, (rect.left + inset, rect.centery - 10))
        screen.blit(bot_label, (rect.left + inset, rect.bottom - 25))

    if show_time:
        left_label = font.render("0s", True, color)
        right_label = font.render(f"{span_seconds}s", True, color)
        screen.blit(left_label, (rect.left + inset, rect.bottom - 20))
        screen.blit(right_label, (rect.right - right_label.get_width() - inset, rect.bottom - 20))


def main() -> None:
    interval = _env_int("OANDA_DASHBOARD_LATENCY_INTERVAL", 5)
    max_points = _env_int("OANDA_DASHBOARD_HISTORY", 120)
    instrument = _env("OANDA_DASHBOARD_INSTRUMENT", "USD_CAD")
    stream_group = _env("OANDA_DASHBOARD_GROUP", "live")
    stream_account = _env("OANDA_DASHBOARD_ACCOUNT", "Primary")
    summary_interval = _env_int("OANDA_DASHBOARD_SUMMARY_INTERVAL", 10)
    instrument_interval = _env_int("OANDA_DASHBOARD_CANDLE_INTERVAL", 5)
    instrument_points = _env_int("OANDA_DASHBOARD_CANDLE_POINTS", 120)
    autoencoder_status_path = _env("OANDA_DASHBOARD_AE_STATUS_PATH", "data/ae_status.jsonl")
    autoencoder_status_interval = _env_int("OANDA_DASHBOARD_AE_STATUS_INTERVAL", 5)
    preds_path = _env("OANDA_DASHBOARD_PRED_PATH", "data/predictions_latest.jsonl")
    preds_interval = _env_int("OANDA_DASHBOARD_PRED_INTERVAL", 5)
    recon_path = _env("OANDA_DASHBOARD_RECON_PATH", "data/recon.jsonl")
    recon_interval = _env_int("OANDA_DASHBOARD_RECON_INTERVAL", 5)
    scores_path = _env("OANDA_DASHBOARD_SCORE_PATH", "data/prediction_scores.jsonl")
    scores_interval = _env_int("OANDA_DASHBOARD_SCORE_INTERVAL", 5)

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
    state.candle_interval = instrument_interval
    state.max_candles = instrument_points
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
    threading.Thread(
        target=recon_loop,
        args=(state, recon_interval, recon_path),
        daemon=True,
    ).start()
    threading.Thread(
        target=scores_loop,
        args=(state, scores_interval, scores_path),
        daemon=True,
    ).start()

    loop = asyncio.new_event_loop()
    threading.Thread(
        target=loop.run_until_complete,
        args=(stream_loop(state, stream_group, stream_account, instrument),),
        daemon=True,
    ).start()

    pygame.init()
    screen = pygame.display.set_mode((1100, 680))
    pygame.display.set_caption("OANDA Dashboard")
    _log_dashboard_event("dashboard_display_ready")
    font = pygame.font.SysFont("Consolas", 20)

    clock = pygame.time.Clock()
    running = True
    event_log_until = time.time() + 10
    ignore_quit = _env_bool("OANDA_DASHBOARD_IGNORE_QUIT", False)
    last_tick_log = time.time()
    processes = start_dashboard_processes()
    while running:
        for event in pygame.event.get():
            if time.time() < event_log_until:
                try:
                    name = pygame.event.event_name(event.type)
                except Exception:
                    name = str(event.type)
                _log_dashboard_json(
                    "pygame_event",
                    {"type": event.type, "name": name, "dict": getattr(event, "dict", None)},
                )
            if event.type == pygame.QUIT:
                _log_dashboard_json(
                    "pygame_quit_received",
                    {"type": event.type, "name": "QUIT", "dict": getattr(event, "dict", None)},
                )
                if not ignore_quit:
                    running = False

        screen.fill((10, 12, 16))
        with state.lock:
            practice = state.practice_latency_ms
            live = state.live_latency_ms
            practice_hist = list(state.practice_history)
            live_hist = list(state.live_history)
            metrics = state.stream_metrics.snapshot()
            candles = list(state.instrument_candles)
            last_close = state.instrument_last_close
            last_vol = state.instrument_last_volume
            last_candle_ts = state.instrument_last_ts
            ae_status = state.autoencoder_status
            preds = state.predictions
            recon = state.recon
            scores = state.pred_scores

        padding = 20
        line_h = 26
        header = font.render("OANDA Live Dashboard", True, (230, 230, 230))
        screen.blit(header, (padding, padding))

        line1 = font.render(
            f"{instrument} | {instrument_interval}s candles   AE mode: reconstruction   Anomaly sigma: 2.0",
            True,
            (200, 200, 200),
        )
        screen.blit(line1, (padding, padding + line_h))

        line2 = font.render(
            f"Latency live: {live:.2f} ms | practice: {practice:.2f} ms"
            if practice is not None and live is not None
            else "Latency live: -- | practice: --",
            True,
            (200, 200, 200),
        )
        screen.blit(line2, (padding, padding + line_h * 2))

        uptime_seconds = int(time.time() - start_ts)
        uptime_label = f"{uptime_seconds // 3600:02d}:{(uptime_seconds % 3600) // 60:02d}:{uptime_seconds % 60:02d}"
        last_err = (
            datetime.fromtimestamp(metrics.last_error_ts, tz=timezone.utc).strftime("%H:%M:%S")
            if metrics.last_error_ts
            else "--"
        )
        pl_text = f"{state.live_pl:.2f}" if state.live_pl is not None else "--"
        bal_text = f"{state.live_balance:.2f}" if state.live_balance is not None else "--"
        coverage = "--"
        mae = "--"
        if scores:
            if scores.get("coverage") is not None:
                coverage = f"{scores['coverage'] * 100:.1f}%"
            if scores.get("mae") is not None:
                mae = f"{scores['mae']:.6f}"
        line3 = font.render(
            f"stream msgs/sec: {metrics.messages_per_sec:.2f}  total: {metrics.messages_total}  uptime: {uptime_label}  coverage: {coverage}  mae: {mae}",
            True,
            (200, 200, 200),
        )
        screen.blit(line3, (padding, padding + line_h * 3))

        line4 = font.render(
            f"P&L: {pl_text}  balance: {bal_text}  errors: {metrics.errors}  last_error: {last_err}",
            True,
            (200, 200, 200),
        )
        screen.blit(line4, (padding, padding + line_h * 4))

        pred_status = "PRED: --"
        pred_ts_label = "--"
        pred_base = None
        pred_step1 = None
        pred_stepN = None
        pred_low = None
        pred_high = None
        pred_recent = False
        pred_record = preds if preds and "horizon" in preds else None
        pred_dt = _parse_timestamp(pred_record.get("ts")) if pred_record else None
        last_candle_dt = _parse_timestamp(last_candle_ts) if last_candle_ts else None
        if pred_dt:
            pred_ts_label = pred_dt.strftime("%H:%M:%S")
            pred_age = time.time() - pred_dt.timestamp()
            if last_candle_dt:
                drift = abs((last_candle_dt - pred_dt).total_seconds())
                pred_recent = drift <= max(instrument_interval * 2, 10)
            else:
                pred_recent = pred_age <= 120
        if pred_record and pred_recent:
            horizon = pred_record.get("horizon") or []
            if horizon:
                pred_base = pred_record.get("base_close")
                pred_step1 = horizon[0].get("mean")
                pred_stepN = horizon[-1].get("mean")
                pred_low = min(item.get("low") for item in horizon if item.get("low") is not None)
                pred_high = max(item.get("high") for item in horizon if item.get("high") is not None)

        line5 = font.render(
            f"pred_ts: {pred_ts_label}  base: {_fmt_float(pred_base)}  p1: {_fmt_float(pred_step1)}  p12: {_fmt_float(pred_stepN)}  {pred_status}",
            True,
            (200, 200, 200),
        )
        screen.blit(line5, (padding, padding + line_h * 5))

        charts_top = padding + line_h * 7 + 10
        chart_h = 180
        price_rect = pygame.Rect(padding, charts_top, 1060 - padding * 2, chart_h * 2)
        pygame.draw.rect(screen, (30, 36, 48), price_rect)
        draw_grid(screen, price_rect)
        price_vals = []
        for c in candles:
            price_vals.extend([c["l"], c["h"]])
        pred_points = []
        if price_vals:
            price_min = min(price_vals)
            price_max = max(price_vals)
            pad = max((price_max - price_min) * 0.10, price_max * 0.001)
            price_min -= pad
            price_max += pad
        else:
            price_min = 0.0
            price_max = 1.0
        if pred_record:
            if not pred_recent:
                pred_status = "PRED: stale"
            else:
                horizon = pred_record.get("horizon") or []
                lows = [item.get("low") for item in horizon if item.get("low") is not None]
                highs = [item.get("high") for item in horizon if item.get("high") is not None]
                mean_vals = [item.get("mean") for item in horizon if item.get("mean") is not None]
                if lows and highs and mean_vals:
                    pred_low = min(lows)
                    pred_high = max(highs)
                    pred_in_view = pred_low <= price_max and pred_high >= price_min
                    pred_status = "PRED: ok" if pred_in_view else "PRED: offscale"
                    pred_points = mean_vals if pred_in_view else []

        line6 = font.render(
            f"pred_low/high: {_fmt_float(pred_low)} / {_fmt_float(pred_high)}  price_min/max: {_fmt_float(price_min)} / {_fmt_float(price_max)}",
            True,
            (200, 200, 200),
        )
        screen.blit(line6, (padding, padding + line_h * 6))
        draw_candles(screen, candles, price_rect, min_val=price_min, max_val=price_max)
        draw_axis_labels(
            screen,
            price_rect,
            price_vals,
            font,
            span_seconds=int(instrument_points * instrument_interval),
            unit=None,
            precision=5,
        )

        if pred_points and pred_record:
            # Draw prediction band as an expanding cloud.
            lows = [item["low"] for item in pred_record["horizon"]]
            highs = [item["high"] for item in pred_record["horizon"]]
            mean_vals = [item["mean"] for item in pred_record["horizon"]]
            step_px = max(8, int(price_rect.width / max(len(pred_points) + 2, 1)))
            start_x = price_rect.right - (len(pred_points) * step_px) - 10
            # Map to screen coords using full scale.
            span = max(price_max - price_min, price_max * 0.002, 1e-6)
            points_low = []
            points_high = []
            points_mean = []
            for i, (low, high, mean) in enumerate(zip(lows, highs, mean_vals)):
                x = start_x + i * step_px
                y_low = price_rect.bottom - int(((low - price_min) / span) * price_rect.height)
                y_high = price_rect.bottom - int(((high - price_min) / span) * price_rect.height)
                y_mean = price_rect.bottom - int(((mean - price_min) / span) * price_rect.height)
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

        # AE reconstruction band + line on right axis (separate scale)
        ae_vals = list(state.recon_history)
        if recon and ae_vals:
            ae_min = min(ae_vals)
            ae_max = max(ae_vals)
            ae_std = state.recon_std_error or 0.0
            k = state.recon_k
            ae_min -= k * ae_std
            ae_max += k * ae_std
            ae_pad = max((ae_max - ae_min) * 0.10, abs(ae_max) * 0.01, 1e-6)
            ae_min -= ae_pad
            ae_max += ae_pad
            ae_span = max(ae_max - ae_min, 1e-6)

            # AE axis labels on right
            draw_axis_labels(
                screen,
                price_rect,
                [ae_min, ae_max],
                font,
                span_seconds=int(instrument_points * instrument_interval),
                unit="recon",
                precision=5,
                align_right=True,
                show_time=False,
            )

            # AE recon line (dashed)
            points = []
            for i, val in enumerate(ae_vals[-instrument_points:]):
                x = price_rect.left + int(i * price_rect.width / max(len(ae_vals) - 1, 1))
                y = price_rect.bottom - int(((val - ae_min) / ae_span) * price_rect.height)
                points.append((x, y))
            draw_dashed_line(screen, points, (120, 180, 255))

            # AE error band around latest recon
            if recon and "recon" in recon:
                recon_val = float(recon["recon"])
                band = k * ae_std
                y_low = price_rect.bottom - int(((recon_val - band - ae_min) / ae_span) * price_rect.height)
                y_high = price_rect.bottom - int(((recon_val + band - ae_min) / ae_span) * price_rect.height)
                band_surface = pygame.Surface((price_rect.width, price_rect.height), pygame.SRCALPHA)
                pygame.draw.rect(
                    band_surface,
                    (70, 120, 200, 60),
                    pygame.Rect(0, min(y_high, y_low), price_rect.width, abs(y_high - y_low)),
                )
                screen.blit(band_surface, (price_rect.left, price_rect.top))

        # Anomaly highlight on last candle
        if recon and candles:
            err = recon.get("error")
            mean_err = recon.get("mean_error", 0.0)
            std_err = recon.get("std_error", 0.0)
            if err is not None and std_err is not None:
                threshold = mean_err + 2 * std_err
                severe = mean_err + 3 * std_err
                if err > threshold:
                    last_index = len(candles) - 1
                    candle_width = max(2, int(price_rect.width / max(len(candles), 1)) - 2)
                    x = price_rect.left + int(last_index * price_rect.width / max(len(candles), 1))
                    y = price_rect.top
                    h = price_rect.height
                    border_color = (255, 120, 0) if err <= severe else (255, 40, 40)
                    pygame.draw.rect(screen, border_color, pygame.Rect(x, y, candle_width, h), 2)

        # Prediction hit/miss markers on recent candles
        if scores and candles:
            results = scores.get("results") or []
            for item in results:
                step = item.get("step")
                hit = item.get("hit")
                actual = item.get("actual")
                if step is None or actual is None:
                    continue
                idx = len(candles) - step
                if idx < 0 or idx >= len(candles):
                    continue
                c = candles[idx]
                y = price_rect.bottom - int(((c["c"] - price_min) / max(price_max - price_min, 1e-6)) * price_rect.height)
                x = price_rect.left + int(idx * price_rect.width / max(len(candles), 1))
                color = (80, 200, 120) if hit else (220, 80, 80)
                pygame.draw.circle(screen, color, (x + 2, y - 6), 3)

        price_label = font.render(
            f"{instrument} last: {last_close if last_close is not None else '--'}  vol: {last_vol if last_vol is not None else '--'}  ts: {last_candle_ts or '--'}",
            True,
            (200, 200, 200),
        )
        screen.blit(price_label, (padding, price_rect.bottom + 6))

        ae_text = "--"
        if ae_status:
            parts = []
            if "epoch" in ae_status:
                parts.append(f"epoch {ae_status['epoch']}")
            if "loss" in ae_status:
                parts.append(f"loss {ae_status['loss']}")
            if "val_loss" in ae_status:
                parts.append(f"val {ae_status['val_loss']}")
            if "ts" in ae_status:
                parts.append(f"ts {ae_status['ts']}")
            ae_text = " | ".join(parts) if parts else "--"
        ae_label = font.render(f"AE status: {ae_text}", True, (200, 200, 200))
        screen.blit(ae_label, (padding, price_rect.bottom + 32))

        pygame.display.flip()
        clock.tick(30)
        if time.time() - last_tick_log >= 5:
            _log_dashboard_event("dashboard_tick")
            last_tick_log = time.time()

    _log_dashboard_event("dashboard_exit")
    stop_dashboard_processes(processes)
    pygame.quit()


if __name__ == "__main__":
    try:
        _log_dashboard_event(f"dashboard_start pid={os.getpid()}")
        atexit.register(lambda: _log_dashboard_event("dashboard_atexit"))
        main()
    except BaseException:
        _log_dashboard_event("dashboard_error")
        _log_dashboard_event(traceback.format_exc())
        raise
