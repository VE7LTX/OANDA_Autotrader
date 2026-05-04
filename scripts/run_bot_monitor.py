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
DEFAULT_FOREX_AUDIT_PATH = DATA_DIR / "forex_autonomous_audit.jsonl"
DEFAULT_FOREX_STATE_PATH = DATA_DIR / "forex_autonomous_state.json"
DEFAULT_SCAN_PATH = DATA_DIR / "forex_opportunity_scan.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor the latest bot cycle, state, and watchlist.")
    parser.add_argument("--audit-path", default=str(DEFAULT_FOREX_AUDIT_PATH if DEFAULT_FOREX_AUDIT_PATH.exists() else DEFAULT_AUDIT_PATH))
    parser.add_argument("--state-path", default=str(DEFAULT_FOREX_STATE_PATH if DEFAULT_FOREX_STATE_PATH.exists() else DEFAULT_STATE_PATH))
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
        self.style.configure("Value.TLabel", background="#111827", foreground="#f8fafc", font=("Consolas", 9))

        self.status_var = tk.StringVar(value="Waiting for bot audit data")
        self.summary_var = tk.StringVar(value="No audit record yet")
        self.health_var = tk.StringVar(value="No health result yet")
        self.action_var = tk.StringVar(value="No action yet")
        self.position_var = tk.StringVar(value="No snapshot yet")
        self.state_var = tk.StringVar(value="No runtime state yet")
        self.decision_var = tk.StringVar(value="No decision summary yet")
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

        cards_frame = tk.Frame(scroll_frame, bg="#0f172a")
        cards_frame.pack(fill="x", pady=6)
        for col in range(3):
            cards_frame.grid_columnconfigure(col, weight=1, uniform="cards")
        self._card_grid(cards_frame, 0, 0, "Cycle Summary", self.summary_var)
        self._card_grid(cards_frame, 0, 1, "Health Gate", self.health_var)
        self._card_grid(cards_frame, 0, 2, "Latest Action", self.action_var)
        self._card_grid(cards_frame, 1, 0, "Position State", self.position_var)
        self._card_grid(cards_frame, 1, 1, "Runtime State", self.state_var)
        self._card_grid(cards_frame, 1, 2, "Decision Gate", self.decision_var)

        watchlists_grid = tk.Frame(scroll_frame, bg="#0f172a")
        watchlists_grid.pack(fill="x", pady=6)
        for col in range(3):
            watchlists_grid.grid_columnconfigure(col, weight=1, uniform="watchlists")
        self.watchlist_frame = self._watchlist_panel(watchlists_grid, 0, 0, "Watchlist")
        self.long_watchlist_frame = self._watchlist_panel(watchlists_grid, 0, 1, "Long Watchlist")
        self.short_watchlist_frame = self._watchlist_panel(watchlists_grid, 0, 2, "Short Watchlist")

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

    def _card_grid(self, parent: tk.Widget, row: int, col: int, title: str, variable: tk.StringVar) -> None:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=14)
        frame.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        ttk.Label(frame, text=title, style="Sub.TLabel").pack(anchor="w")
        tk.Label(
            frame,
            textvariable=variable,
            justify="left",
            anchor="w",
            bg="#111827",
            fg="#f8fafc",
            font=("Consolas", 10),
            wraplength=340,
        ).pack(fill="x", pady=(6, 0))

    def _watchlist_panel(self, parent: tk.Widget, row: int, col: int, title: str) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=14)
        frame.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
        label = ttk.Label(frame, text=title, style="Sub.TLabel")
        label.pack(anchor="w")
        container = tk.Frame(frame, bg="#111827")
        container.pack(fill="x", pady=(6, 0))
        if title == "Watchlist":
            self.watchlist_title = label
            self.watchlist_container = container
        elif title == "Long Watchlist":
            self.long_watchlist_title = label
            self.long_watchlist_container = container
        else:
            self.short_watchlist_title = label
            self.short_watchlist_container = container
        return frame

    def refresh(self) -> None:
        audit = read_last_jsonl(self.audit_path)
        state = read_json(self.state_path)
        scan = read_json(self.scan_path)

        if audit is None:
            self.status_var.set("No bot audit record yet")
            self.after(2000, self.refresh)
            return

        blocked = audit.get("blocked") or []
        decision = audit.get("decision_summary") or (state or {}).get("decision_summary") or {}
        status = classify_status(audit, blocked, decision)
        self.status_var.set(
            f"Latest cycle status: {status} | Audit: {self.audit_path.name} | State: {self.state_path.name}"
        )

        self.summary_var.set(format_cycle_summary(audit, blocked))
        self.health_var.set(format_health_summary(audit.get("health") or {}))
        self.action_var.set(format_action_summary(audit.get("action") or {}, audit.get("result") or {}))
        self.position_var.set(format_snapshot_summary(audit.get("snapshot") or {}))
        self.state_var.set(format_state_summary(state or {}))
        self.decision_var.set(format_decision_summary(decision))
        self._update_pills(audit, blocked, state or {}, decision)
        self._render_watchlist(scan or {})
        self._render_side_watchlists(scan or {})
        self.after(2000, self.refresh)

    def _render_watchlist(self, scan: dict) -> None:
        for child in self.watchlist_container.winfo_children():
            child.destroy()

        exits = scan.get("exit_opportunities") or []
        entries = scan.get("entry_opportunities") or []
        self.watchlist_title.configure(text=f"Watchlist  exits {len(exits)}  entries {len(entries)}")

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
            kind = str(row.get("kind", "entry")).upper()
            color = "#166534" if kind == "EXIT" else "#1d4ed8"
            text = (
                f"{kind} {row.get('instrument')} {str(row.get('action', 'n/a')).upper()}  "
                f"score {_fmt(row.get('score'))}\n"
                f"{row.get('reason', 'n/a')}"
            )
            tk.Label(
                self.watchlist_container,
                text=text,
                bg=color,
                fg="#f8fafc",
                font=("Consolas", 9),
                anchor="w",
                justify="left",
                wraplength=310,
            ).pack(fill="x", pady=2)

    def _render_side_watchlists(self, scan: dict) -> None:
        self._render_side_watchlist(
            self.long_watchlist_container,
            self.long_watchlist_title,
            scan.get("long_opportunities") or [],
            "LONG",
            "#166534",
        )
        self._render_side_watchlist(
            self.short_watchlist_container,
            self.short_watchlist_title,
            scan.get("short_opportunities") or [],
            "SHORT",
            "#1d4ed8",
        )

    def _render_side_watchlist(
        self,
        container: tk.Widget,
        title: ttk.Label,
        rows: list[dict],
        label: str,
        color: str,
    ) -> None:
        for child in container.winfo_children():
            child.destroy()
        title.configure(text=f"{label} Watchlist ({len(rows)})")
        if not rows:
            tk.Label(
                container,
                text="No candidates",
                bg="#111827",
                fg="#f8fafc",
                font=("Consolas", 10),
                anchor="w",
                justify="left",
            ).pack(fill="x")
            return
        for row in rows[:5]:
            text = (
                f"{row.get('instrument')} {str(row.get('action', 'n/a')).upper()}  "
                f"score {_fmt(row.get('score'))}\n"
                f"{row.get('reason', 'n/a')}"
            )
            tk.Label(
                container,
                text=text,
                bg=color,
                fg="#f8fafc",
                font=("Consolas", 9),
                anchor="w",
                justify="left",
                wraplength=310,
            ).pack(fill="x", pady=2)


def format_cycle_summary(audit: dict, blocked: list[str]) -> str:
    return "\n".join(
        [
            f"Instrument: {audit.get('instrument', 'n/a')}",
            f"Granularity: {audit.get('granularity', 'n/a')}",
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
            f"Stale secs: {_fmt(details.get('stale_seconds'))}",
            f"Session hour UTC: {details.get('session_hour_utc', 'n/a')}",
            f"ATR: {_fmt(details.get('atr'))}  Regime: {_fmt(details.get('regime_score'))}",
            f"Day PnL: {_fmt(details.get('daily_pnl'))}  Week PnL: {_fmt(details.get('weekly_pnl'))}",
        ]
    )


def format_action_summary(action: dict, result: dict) -> str:
    metadata = action.get("metadata") or {}
    order = result.get("order") or {}
    order_units = order.get("units") if order else None
    return "\n".join(
        [
            f"Action: {action.get('action', 'n/a')}  Reason: {action.get('reason', 'n/a')}",
            f"Instrument: {action.get('instrument', 'n/a')}  Units: {action.get('units', 'n/a')}",
            f"Order units: {order_units or 'n/a'}  Confidence: {_fmt(action.get('confidence'))}",
            f"Long: {_fmt(metadata.get('long_score'))}  Short: {_fmt(metadata.get('short_score'))}",
            f"Fast MA: {_fmt(metadata.get('fast_ma'))}",
            f"Slow MA: {_fmt(metadata.get('slow_ma'))}  RSI: {_fmt(metadata.get('rsi'))}",
        ]
    )


def format_snapshot_summary(snapshot: dict) -> str:
    positions = snapshot.get("positions_by_instrument") or {}
    active_positions = ", ".join(f"{name}:{units}" for name, units in positions.items() if units) or "flat"
    return "\n".join(
        [
            f"NAV: {_fmt(snapshot.get('nav'))}",
            f"Balance: {_fmt(snapshot.get('balance'))}",
            f"Open trades: {_fmt(snapshot.get('open_trade_count'), digits=0)}",
            f"Positions: {active_positions}",
            f"Unrealized: {_fmt(snapshot.get('unrealized_pnl'))}",
            f"Realized: {_fmt(snapshot.get('realized_pnl_day'))}",
        ]
    )


def format_state_summary(state: dict) -> str:
    position = state.get("current_position") or {}
    active_positions = state.get("active_positions") or []
    active_text = ", ".join(
        f"{item.get('instrument', 'n/a')}:{item.get('side', 'n/a')}:{item.get('units', 'n/a')}"
        for item in active_positions
    ) or "none"
    if not position:
        return "\n".join(
            [
                f"Failures: {state.get('consecutive_failures', 'n/a')}  Last action: {state.get('last_action', 'n/a')}",
                "Current position: none",
                f"Active positions: {active_text}",
                f"Realized PnL: {_fmt(state.get('realized_pnl_day'))}",
                f"Unrealized PnL: {_fmt(state.get('unrealized_pnl'))}",
            ]
        )
    return "\n".join(
        [
            f"Failures: {state.get('consecutive_failures', 'n/a')}  Last action: {state.get('last_action', 'n/a')}",
            f"Current position: {position.get('side', 'n/a')} {position.get('units', 'n/a')} {position.get('instrument', 'n/a')}",
            f"Entry: {position.get('entry_price', 'n/a')}  Peak: {position.get('peak_price', 'n/a')}  Trough: {position.get('trough_price', 'n/a')}",
            f"Active positions: {active_text}",
            f"Realized PnL: {_fmt(state.get('realized_pnl_day'))}",
            f"Unrealized PnL: {_fmt(state.get('unrealized_pnl'))}",
        ]
    )


def format_decision_summary(decision: dict) -> str:
    if not decision:
        return "No decision summary yet"
    return "\n".join(
        [
            f"Decision: {decision.get('decision', 'n/a')}  Reason: {decision.get('reason', 'n/a')}",
            f"Instrument: {decision.get('instrument', 'n/a')}  Action: {decision.get('action', 'n/a')}",
            f"Filter: {decision.get('filter_reason', 'n/a')}",
            f"Score: {_fmt(decision.get('score'))}  Need: {_fmt(decision.get('min_submit_score'))}",
            f"Gap: {_fmt(decision.get('score_gap'))}",
            f"Long: {_fmt(decision.get('long_score'))}  Short: {_fmt(decision.get('short_score'))}",
            f"Regime: {_fmt(decision.get('regime_score'))}  RSI: {_fmt(decision.get('rsi'))}",
            f"Submitted: {decision.get('submitted_count', 0)}  Instruments: {', '.join(decision.get('instruments') or []) or 'none'}",
        ]
    )


def _fmt(value, *, digits: int = 3) -> str:
    if value in (None, ""):
        return "n/a"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if digits == 0:
        return str(int(round(number)))
    return f"{number:.{digits}f}"


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
    unrealized = state.get("unrealized_pnl", 0.0)
    return f"day {day:.2f} | week {week:.2f} | uPnL {unrealized:.2f}"


def _set_pill(pill: tk.Label, prefix: str, text: str, color: str) -> None:
    pill.configure(text=f"{prefix}: {text}", bg=color)


def classify_status(audit: dict, blocked: list[str], decision: dict | None = None) -> str:
    if audit.get("error"):
        return "ERROR"
    if not blocked:
        if (decision or {}).get("decision") == "watching":
            return "WATCHING"
        return "READY"
    if any(reason.startswith("cooldown") for reason in blocked):
        return "COOLDOWN"
    if any("loss_limit" in reason or "regime_filter" in reason for reason in blocked):
        return "RISK BLOCKED"
    return "BLOCKED"


def _status_color(status: str) -> str:
    if status == "READY":
        return "#166534"
    if status == "WATCHING":
        return "#1d4ed8"
    if status == "COOLDOWN":
        return "#92400e"
    if status == "RISK BLOCKED":
        return "#7c2d12"
    if status == "ERROR":
        return "#991b1b"
    return "#334155"


def _update_pills(self: MonitorApp, audit: dict, blocked: list[str], state: dict, decision: dict | None = None) -> None:
    status = classify_status(audit, blocked, decision)
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
