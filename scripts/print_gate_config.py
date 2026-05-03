import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from oanda_autotrader.trade_latency_gate import load_thresholds


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="live")
    parser.add_argument("--instrument", default="USD_CAD")
    parser.add_argument("--thresholds-dir", default="data")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg, meta = load_thresholds(args.mode, args.instrument, base_dir=args.thresholds_dir)
    payload = {"config": cfg.__dict__, "meta": meta}
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
