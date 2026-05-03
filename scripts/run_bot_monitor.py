from __future__ import annotations

import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
AUDIT_PATH = DATA_DIR / "bot_audit.jsonl"
STATE_PATH = DATA_DIR / "bot_state.json"


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
    def __init__(self) -> None:
        super().__init__()
        self.title("OANDA Bot Monitor")
        self.geometry("980x760")
        self.configure(bg="#0f172a")
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("Card.TFrame", background="#111827")
        self.style.configure("Header.TLabel", background="#0f172a", foreground="#e5e7eb", font=("Segoe UI", 18, "bold"))
        self.style.configure("Sub.TLabel", background="#111827", foreground="#cbd5e1", font=("Segoe UI", 10))
        self.style.configure("Value.TLabel", background="#111827", foreground="#f8fafc", font=("Consolas", 11))

        self.status_var = tk.StringVar(value="Waiting for bot audit data")
        self.summary_var = tk.StringVar(value="No audit record yet")
        self.health_var = tk.StringVar(value="No health result yet")
        self.action_var = tk.StringVar(value="No action yet")
        self.position_var = tk.StringVar(value="No snapshot yet")
        self.state_var = tk.StringVar(value="No runtime state yet")

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        outer = tk.Frame(self, bg="#0f172a", padx=16, pady=16)
        outer.pack(fill="both", expand=True)

        header = ttk.Label(outer, text="Practice Bot Monitor", style="Header.TLabel")
        header.pack(anchor="w")

        controls = tk.Frame(outer, bg="#0f172a")
        controls.pack(fill="x", pady=(8, 12))
        tk.Label(
            controls,
            textvariable=self.status_var,
            bg="#0f172a",
            fg="#93c5fd",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")
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

        self._card(outer, "Cycle Summary", self.summary_var)
        self._card(outer, "Health Gate", self.health_var)
        self._card(outer, "Latest Action", self.action_var)
        self._card(outer, "Account Snapshot", self.position_var)
        self._card(outer, "Runtime State", self.state_var)

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
            font=("Consolas", 11),
            wraplength=920,
        ).pack(fill="x", pady=(6, 0))

    def refresh(self) -> None:
        audit = read_last_jsonl(AUDIT_PATH)
        state = read_json(STATE_PATH)

        if audit is None:
            self.status_var.set("No bot audit record yet")
            self.after(2000, self.refresh)
            return

        blocked = audit.get("blocked") or []
        status = "BLOCKED" if blocked else "READY"
        if audit.get("error"):
            status = "ERROR"
        self.status_var.set(
            f"Latest cycle status: {status} | Audit file: {AUDIT_PATH.name}"
        )

        self.summary_var.set(
            format_block(
                {
                    "instrument": audit.get("instrument"),
                    "granularity": audit.get("granularity"),
                    "environment": audit.get("environment"),
                    "dry_run": audit.get("dry_run"),
                    "blocked": blocked,
                    "error": audit.get("error"),
                }
            )
        )
        self.health_var.set(format_block(audit.get("health") or {"health": "missing"}))
        self.action_var.set(format_block(audit.get("action") or {"action": "missing"}))
        self.position_var.set(format_block(audit.get("snapshot") or {"snapshot": "missing"}))
        self.state_var.set(format_block(state or {"state": "missing"}))
        self.after(2000, self.refresh)


def format_block(payload: dict) -> str:
    return json.dumps(payload, indent=2)


def main() -> None:
    app = MonitorApp()
    app.mainloop()


if __name__ == "__main__":
    sys.exit(main())
