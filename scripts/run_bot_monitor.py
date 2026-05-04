from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_AUDIT_PATH = DATA_DIR / "bot_audit.jsonl"
DEFAULT_STATE_PATH = DATA_DIR / "bot_state.json"
DEFAULT_SCAN_PATH = DATA_DIR / "forex_opportunity_scan.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor the latest bot cycle, state, and watchlist.")
    parser.add_argument("--audit-path", default=str(DEFAULT_AUDIT_PATH))
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--scan-path", default=str(DEFAULT_SCAN_PATH))
    return parser.parse_args()


def read_last_jsonl(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except Exception:
        return None


def read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


class MonitorApp(tk.Tk):
    def __init__(self, *, audit_path: Path, state_path: Path, scan_path: Path) -> None:
        super().__init__()
        self.audit_path = audit_path
        self.state_path = state_path
        self.scan_path = scan_path
        self.title("OANDA Bot Monitor")
        self._configure_geometry()
        self.configure(bg="#0f172a")
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("Card.TFrame", background="#111827")
        self.style.configure("Header.TLabel", background="#0f172a", foreground="#e5e7eb", font=("Segoe UI", 18, "bold"))
        self.style.configure("Sub.TLabel", background="#111827", foreground="#cbd5e1", font=("Segoe UI", 10))
        self.style.configure("Value.TLabel", background="#111827", foreground="#f8fafc", font=("Consolas", 10))

        self.status_var = tk.StringVar(value="Waiting for bot audit data")
        self.summary_var = tk.StringVar(value="No audit record yet")
        self.health_var = tk.StringVar(value="No health result yet")
        self.action_var = tk.StringVar(value="No action yet")
        self.position_var = tk.StringVar(value="No snapshot yet")
        self.state_var = tk.StringVar(value="No runtime state yet")
        self.refresh_var = tk.StringVar(value="Auto-refresh every 2 seconds")

        self._build_ui()
        self.refresh()

    def _configure_geometry(self) -> None:
        try:
            screen_w = max(1024, self.winfo_screenwidth())
            screen_h = max(768, self.winfo_screenheight())
            width = min(1100, int(screen_w * 0.82))
            height = min(820, int(screen_h * 0.86))
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 2)
            self.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:
            self.geometry("1100x820")
        self.minsize(920, 680)

    def _build_ui(self) -> None:
        outer = tk.Frame(self, bg="#0f172a")
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg="#0f172a", highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="#0f172a")
        scroll_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def sync_scrollregion(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_width(event: tk.Event) -> None:
            canvas.itemconfigure(scroll_window, width=event.width)

        scroll_frame.bind("<Configure>", sync_scrollregion)
        canvas.bind("<Configure>", sync_width)
        canvas.pack(side="left", fill="both", expand=True, padx=12, pady=12)
        scrollbar.pack(side="right", fill="y", pady=12)

        header = ttk.Label(scroll_frame, text="Practice Bot Monitor", style="Header.TLabel")
        header.pack(anchor="w")

        controls = tk.Frame(scroll_frame, bg="#0f172a")
        controls.pack(fill="x", pady=(8, 12))
        tk.Label(
            controls,
            textvariable=self.status_var,
            bg="#0f172a",
            fg="#93c5fd",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")
        tk.Label(
            controls,
            textvariable=self.refresh_var,
            bg="#0f172a",
            fg="#94a3b8",
            font=("Segoe UI", 9),
        ).pack(side="left", padx=(10, 0))
        tk.Button(
            controls,
            text="Refresh",
            command=self.refresh,
            bg="#1d4ed8",
            fg="white",
            activebackground="#2563eb",
            relief="flat",
            padx=12,
            pady=6,
        ).pack(side="right")

        self._status_pills(scroll_frame)
        self._card(scroll_frame, "Cycle Summary", self.summary_var)
        self._card(scroll_frame, "Health Gate", self.health_var)
        self._card(scroll_frame, "Latest Action", self.action_var)
        self._card(scroll_frame, "Position State", self.position_var)
        self._card(scroll_frame, "Runtime State", self.state_var)
        self.watchlist_frame = ttk.Frame(scroll_frame, style="Card.TFrame", padding=14)
        self.watchlist_frame.pack(fill="x", pady=6)
        ttk.Label(self.watchlist_frame, text="Watchlist", style="Sub.TLabel").pack(anchor="w")
        self.watchlist_container = tk.Frame(self.watchlist_frame, bg="#111827")
        self.watchlist_container.pack(fill="x", pady=(6, 0))

    def _status_pills(self, parent: tk.Widget) -> None:
        pill_row = tk.Frame(parent, bg="#0f172a")
        pill_row.pack(fill="x", pady=(0, 6))
        self.status_pill = self._pill(pill_row, "Status", "#1d4ed8")
        self.position_pill = self._pill(pill_row, "Position", "#0f766e")
        self.signal_pill = self._pill(pill_row, "Signal", "#7c3aed")
        self.pnl_pill = self._pill(pill_row, "PnL", "#334155")

    def _pill(self, parent: tk.Widget, label: str, color: str) -> tk.Label:
        pill = tk.Label(
            parent,
            text=f"{label}: n/a",
            bg=color,
            fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=6,
        )
        pill.pack(side="left", padx=(0, 8))
        return pill

    def _card(self, parent: tk.Widget, title: str, variable: tk.StringVar) -> None:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=14)
        frame.pack(fill="x", pady=6)
        ttk.Label(frame, text=title, style="Sub.TLabel").pack(anchor="w")
        tk.Label(
            frame,
            textvariable=variable,
            justify="left",
            anchor="w",
            bg="#111827",
            fg="#f8fafc",
            font=("Consolas", 10),
            wraplength=980,
        ).pack(fill="x", pady=(6, 0))

    def refresh(self) -> None:
        audit = read_last_jsonl(self.audit_path)
        state = read_json(self.state_path)
        scan = read_json(self.scan_path)

        if audit is None:
            self.status_var.set("No bot audit record yet")
            self.after(2000, self.refresh)
            return

        blocked = audit.get("blocked") or []
        status = classify_status(audit, blocked)
        self.status_var.set(
            f"Latest cycle status: {status} | Audit: {self.audit_path.name} | State: {self.state_path.name}"
        )

        self.summary_var.set(format_cycle_summary(audit, blocked))
        self.health_var.set(format_health_summary(audit.get("health") or {}))
        self.action_var.set(format_action_summary(audit.get("action") or {}, audit.get("result") or {}))
        self.position_var.set(format_snapshot_summary(audit.get("snapshot") or {}))
        self.state_var.set(format_state_summary(state or {}))
        self._update_pills(audit, blocked, state or {})
        self._render_watchlist(scan or {})
        self.after(2000, self.refresh)

    def _render_watchlist(self, scan: dict) -> None:
        for child in self.watchlist_container.winfo_children():
            child.destroy()

        rows = (scan.get("top_opportunities") or [])[:5]
        if not rows:
            tk.Label(
                self.watchlist_container,
                text="No watchlist data yet",
                bg="#111827",
                fg="#f8fafc",
                font=("Consolas", 10),
                anchor="w",
                justify="left",
            ).pack(fill="x")
            return

        for row in rows:
            text = (
                f"{row.get('instrument')}  {str(row.get('action', 'n/a')).upper()}  "
                f"score {float(row.get('score', 0.0)):.3f}  "
                f"reason {row.get('reason', 'n/a')}"
            )
            tk.Label(
                self.watchlist_container,
                text=text,
                bg="#111827",
                fg="#f8fafc",
                font=("Consolas", 10),
                anchor="w",
                justify="left",
            ).pack(fill="x", pady=2)


def format_cycle_summary(audit: dict, blocked: list[str]) -> str:
    return "\n".join(
        [
            f"Instrument: {audit.get('instrument', 'n/a')}  Granularity: {audit.get('granularity', 'n/a')}",
            f"Env: {audit.get('environment', 'n/a')}  Dry-run: {audit.get('dry_run', 'n/a')}",
            f"Status: {'blocked' if blocked else 'ready'}  Blocked: {', '.join(blocked) if blocked else 'none'}",
            f"Error: {audit.get('error') or 'none'}",
        ]
    )


def format_health_summary(health: dict) -> str:
    details = health.get("details") or {}
    reasons = health.get("reasons") or []
    return "\n".join(
        [
            f"OK: {health.get('ok', 'n/a')}  Reasons: {', '.join(reasons) if reasons else 'none'}",
            f"Stale secs: {details.get('stale_seconds', 'n/a')}  Session hour UTC: {details.get('session_hour_utc', 'n/a')}",
            f"ATR: {details.get('atr', 'n/a')}  Regime: {details.get('regime_score', 'n/a')}",
            f"Day PnL: {details.get('daily_pnl', 'n/a')}  Week PnL: {details.get('weekly_pnl', 'n/a')}",
        ]
    )


def format_action_summary(action: dict, result: dict) -> str:
    metadata = action.get("metadata") or {}
    order = result.get("order") or {}
    order_units = order.get("units") if order else None
    return "\n".join(
        [
            f"Action: {action.get('action', 'n/a')}  Reason: {action.get('reason', 'n/a')}",
            f"Instrument: {action.get('instrument', 'n/a')}  Units: {action.get('units', 'n/a')}  Order units: {order_units or 'n/a'}",
            f"Confidence: {action.get('confidence', 'n/a')}  Long score: {metadata.get('long_score', 'n/a')}  Short score: {metadata.get('short_score', 'n/a')}",
            f"Fast MA: {metadata.get('fast_ma', 'n/a')}  Slow MA: {metadata.get('slow_ma', 'n/a')}  RSI: {metadata.get('rsi', 'n/a')}",
        ]
    )


def format_snapshot_summary(snapshot: dict) -> str:
    positions = snapshot.get("positions_by_instrument") or {}
    active_positions = ", ".join(f"{name}:{units}" for name, units in positions.items() if units) or "flat"
    return "\n".join(
        [
            f"NAV: {snapshot.get('nav', 'n/a')}  Balance: {snapshot.get('balance', 'n/a')}",
            f"Open trades: {snapshot.get('open_trade_count', 'n/a')}  Positions: {active_positions}",
        ]
    )


def format_state_summary(state: dict) -> str:
    position = state.get("current_position") or {}
    if not position:
        return "\n".join(
            [
                f"Failures: {state.get('consecutive_failures', 'n/a')}  Last action: {state.get('last_action', 'n/a')}",
                "Current position: none",
            ]
        )
    return "\n".join(
        [
            f"Failures: {state.get('consecutive_failures', 'n/a')}  Last action: {state.get('last_action', 'n/a')}",
            f"Current position: {position.get('side', 'n/a')} {position.get('units', 'n/a')} {position.get('instrument', 'n/a')}",
            f"Entry: {position.get('entry_price', 'n/a')}  Peak: {position.get('peak_price', 'n/a')}  Trough: {position.get('trough_price', 'n/a')}",
        ]
    )


def _position_label(state: dict) -> str:
    position = state.get("current_position") or {}
    if not position:
        return "FLAT"
    side = str(position.get("side", "n/a")).upper()
    units = position.get("units", "n/a")
    instrument = position.get("instrument", "n/a")
    return f"{side} {units} {instrument}"


def _signal_label(audit: dict) -> str:
    action = audit.get("action") or {}
    metadata = action.get("metadata") or {}
    return (
        f"long {metadata.get('long_score', 'n/a')} | "
        f"short {metadata.get('short_score', 'n/a')} | "
        f"regime {metadata.get('regime_score', 'n/a')}"
    )


def _pnl_label(state: dict) -> str:
    day = state.get("realized_pnl_day", 0.0)
    week = state.get("realized_pnl_week", 0.0)
    return f"day {day:.2f} | week {week:.2f}"


def _set_pill(pill: tk.Label, prefix: str, text: str, color: str) -> None:
    pill.configure(text=f"{prefix}: {text}", bg=color)


def classify_status(audit: dict, blocked: list[str]) -> str:
    if audit.get("error"):
        return "ERROR"
    if not blocked:
        return "READY"
    if any(reason.startswith("cooldown") for reason in blocked):
        return "COOLDOWN"
    if any("loss_limit" in reason or "regime_filter" in reason for reason in blocked):
        return "RISK BLOCKED"
    return "BLOCKED"


def _status_color(status: str) -> str:
    if status == "READY":
        return "#166534"
    if status == "COOLDOWN":
        return "#92400e"
    if status == "RISK BLOCKED":
        return "#7c2d12"
    if status == "ERROR":
        return "#991b1b"
    return "#334155"


def _update_pills(self: MonitorApp, audit: dict, blocked: list[str], state: dict) -> None:
    status = classify_status(audit, blocked)
    _set_pill(self.status_pill, "Status", status, _status_color(status))
    _set_pill(self.position_pill, "Position", _position_label(state), "#0f766e")
    _set_pill(self.signal_pill, "Signal", _signal_label(audit), "#7c3aed")
    _set_pill(self.pnl_pill, "PnL", _pnl_label(state), "#334155")


MonitorApp._update_pills = _update_pills


def format_block(payload: dict) -> str:
    return json.dumps(payload, indent=2)


def main() -> None:
    args = parse_args()
    app = MonitorApp(
        audit_path=Path(args.audit_path),
        state_path=Path(args.state_path),
        scan_path=Path(args.scan_path),
    )
    app.mainloop()


if __name__ == "__main__":
    sys.exit(main())
