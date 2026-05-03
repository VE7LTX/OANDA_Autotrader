import argparse
import json
import os


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/stream_latency.jsonl")
    parser.add_argument("--output", default="data/stream_latency_v2.jsonl")
    parser.add_argument("--assume-mode", default="live")
    parser.add_argument("--instrument", default="USD_CAD")
    parser.add_argument("--only-missing", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    count = 0
    with open(args.input, "r", encoding="utf-8") as inp, open(
        args.output, "w", encoding="utf-8"
    ) as out:
        for line in inp:
            raw = line.strip()
            if not raw:
                continue
            payload = json.loads(raw)
            has_mode = "mode" in payload and payload.get("mode") is not None
            has_instrument = "instrument" in payload and payload.get("instrument") is not None
            if args.only_missing and has_mode and has_instrument:
                out.write(json.dumps(payload) + "\n")
                count += 1
                continue
            if not has_mode:
                payload["mode"] = args.assume_mode
            if not has_instrument:
                payload["instrument"] = args.instrument
            out.write(json.dumps(payload) + "\n")
            count += 1
    print(json.dumps({"output": args.output, "records": count}, indent=2))


if __name__ == "__main__":
    main()
