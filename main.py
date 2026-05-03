# main.py — CLI front-end for the OANDA trading-analyst toolkit
# Author  : Ziggy (OpenAI o3)
# Updated : 2025-06-19

from __future__ import annotations

# ── force a GUI backend BEFORE any other matplotlib import ─────────────────
import matplotlib
matplotlib.use("TkAgg")                # TkAgg works out-of-box on Windows

import argparse
import logging
import sys
from typing import List

# ── SDK layers ─────────────────────────────────────────────────────────────
from accounts.handlers   import account_handler
from instruments.handlers import instrument_handler
from candles.handlers    import candle_handler
from streams.pricing     import PricingStreamWorker
from utils.agg           import CandleAggregator
from utils.exceptions    import OandaError

# ── optional Rich tables ───────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table   import Table
    RICH, console = True, Console()
except ImportError:
    RICH, console = False, None

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s – %(levelname)s – %(message)s")
logger = logging.getLogger(__name__)

# ═════════════════ helper printers ════════════════════════════════════════
def _print_instruments(lst: List):
    if RICH:
        t = Table(title="Tradeable Instruments")
        for col in ("Name","Display","Type","PipLoc","Prec"):
            t.add_column(col, justify="right" if col in ("PipLoc","Prec") else None)
        for i in lst:
            t.add_row(i.name,i.displayName,i.type,
                      str(i.pipLocation),str(i.displayPrecision))
        console.print(t)
    else:
        print("Name        Display       Type  PipLoc Prec")
        for i in lst:
            print(f"{i.name:<11}{i.displayName:<13}{i.type:<6}"
                  f"{i.pipLocation:>7}{i.displayPrecision:>6}")

def _print_summary(s):
    cols=("id","alias","currency","balance","unrealizedPL",
          "nav","marginUsed","marginAvailable")
    if RICH:
        t=Table(title="Account Summary",box=None)
        for c in cols:t.add_row(c,str(getattr(s,c)));console.print(t)
    else:
        for c in cols:print(f"{c:16}: {getattr(s,c)}")

# ═════════════════ sub-commands ════════════════════════════════════════════
def cmd_list(_):     _print_instruments(instrument_handler.list_instruments())
def cmd_show(a):     _print_instruments([instrument_handler.get(a.symbol)])
def cmd_summary(_):  _print_summary(account_handler.get_account_summary())

def cmd_chart(a):
    try: import pandas as pd, matplotlib.pyplot as plt
    except ImportError: sys.exit("pip install pandas matplotlib")
    rows=candle_handler.fetch(a.symbol,granularity=a.granularity,count=a.count)
    df  =pd.DataFrame({"Time":pd.to_datetime([r["time"] for r in rows]),
                       "Close":[float(r["mid"]["c"]) for r in rows]})
    plt.figure(figsize=(10,4));plt.plot(df["Time"],df["Close"])
    plt.title(f"{a.symbol} – {a.granularity} closes");plt.tight_layout()
    plt.show(block=True)

# ── GLOBAL animation handle to prevent GC ─────────────────────────────────
_ani = None

def cmd_stream(a):
    """
    Live streaming candlestick plot.

    • background thread pulls PRICE ticks → queue
    • CandleAggregator bins them into *a.window*-second bars
    • mplfinance redraws the last *a.bars* candles every 0.5 s
    """
    try:
        import pandas as pd, mplfinance as mpf
        import matplotlib.pyplot as plt, matplotlib.animation as animation
        import queue, datetime as dt
    except ImportError:
        sys.exit("pip install pandas matplotlib mplfinance")

    q: "queue.Queue" = queue.Queue(maxsize=5000)
    PricingStreamWorker([a.symbol], q).start()

    agg=CandleAggregator(window_secs=a.window)
    df =pd.DataFrame(columns=["Open","High","Low","Close"],
                     index=pd.DatetimeIndex([],name="Time"))

    fig, ax=plt.subplots(figsize=(10,5))
    plt.title(f"{a.symbol} — live {a.window}s candles")

    def redraw(frame_df):
        ax.clear()
        mpf.plot(frame_df,type="candle",ax=ax,style="charles",
                 datetime_format="%H:%M:%S",xrotation=15,show_nontrading=True)

    def updater(_):
        nonlocal df
        while not q.empty(): agg.add_tick(q.get_nowait())
        for bar in agg.flush_ready():
            ts=pd.Timestamp(dt.datetime.fromtimestamp(bar["start"]))
            df.loc[ts]=[bar["open"],bar["high"],bar["low"],bar["close"]]
            logger.debug("completed bar @ %s  O=%.5f C=%.5f",
                         ts.strftime('%H:%M:%S'),bar["open"],bar["close"])
        df=df.tail(a.bars)
        if not df.empty:    redraw(df)
        return []

    global _ani
    _ani=animation.FuncAnimation(fig,updater,interval=500,blit=False,
                                 cache_frame_data=False)
    plt.show(block=True)

# ═════════════════ argparse wiring ════════════════════════════════════════
def cli()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="OANDA Trading-Analyst CLI")
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("instruments").set_defaults(func=cmd_list)
    sp=sub.add_parser("show");sp.add_argument("symbol");sp.set_defaults(func=cmd_show)
    sub.add_parser("summary").set_defaults(func=cmd_summary)
    cp=sub.add_parser("chart");cp.add_argument("symbol")
    cp.add_argument("-g","--granularity",default="M5")
    cp.add_argument("-n","--count",type=int,default=200);cp.set_defaults(func=cmd_chart)
    lp=sub.add_parser("stream");lp.add_argument("symbol")
    lp.add_argument("-w","--window",type=int,default=5,help="candle width (s)")
    lp.add_argument("-b","--bars",type=int,default=120,help="bars on screen")
    lp.set_defaults(func=cmd_stream)
    return p

def main(argv:List[str]|None=None):
    args=cli().parse_args(argv);args.func(args)

if __name__=="__main__":
    try:main()
    except KeyboardInterrupt:print("\nInterrupted — goodbye.")