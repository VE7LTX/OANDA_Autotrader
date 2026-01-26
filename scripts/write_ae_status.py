"""
Write dummy autoencoder status updates to JSONL for dashboard testing.
"""

from __future__ import annotations

import json
import os
import time


def main() -> None:
    out_dir = "data"
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "ae_status.jsonl")

    epoch = 0
    loss = 0.05
    while True:
        epoch += 1
        loss *= 0.98
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "epoch": epoch,
            "loss": round(loss, 6),
        }
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
        time.sleep(2)


if __name__ == "__main__":
    main()
