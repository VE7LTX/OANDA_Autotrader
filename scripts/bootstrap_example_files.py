from __future__ import annotations

from pathlib import Path


FILES = {
    ".env.example": """OANDA_ENV=demo
FXPRACTICE_API_URL=https://api-fxpractice.oanda.com
FXPRACTICE_STREAM_URL=https://stream-fxpractice.oanda.com
FXPRACTICE_APIKEY=your-practice-api-key
FXPRACTICE_ACCOUNT_ID=your-practice-account-id
FXTRADE_API_URL=https://api-fxtrade.oanda.com
FXTRADE_STREAM_URL=https://stream-fxtrade.oanda.com
FXTRADE_APIKEY=your-live-api-key
FXTRADE_ACCOUNT_ID=your-live-account-id
DEFAULT_DATETIME_FORMAT=RFC3339
""",
    "accounts.yaml.example": """# accounts.yaml
accounts:
  demo:
    environment: FXPRACTICE
    currency: CAD
    accounts:
      - name: Primary
        type: primary
        account_id: "101-002-0000000-000"

  live:
    environment: FXTRADE
    currency: CAD
    accounts:
      - name: Primary
        type: primary
        account_id: "001-002-0000000-001"
""",
    "decision.example.json": """{
  "action": "buy",
  "instrument": "USD_CAD",
  "units": 100,
  "confidence": 0.62,
  "reason": "example_action_for_json_file_provider",
  "stop_loss_price": "1.35000",
  "take_profit_price": "1.36000",
  "metadata": {
    "source": "example"
  }
}
""",
}


def main() -> None:
    for name, content in FILES.items():
        path = Path(name)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
