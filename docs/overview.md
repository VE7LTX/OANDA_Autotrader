# Overview

## Purpose
This repo is a small OANDA market-data + ML prediction pipeline with a live pygame dashboard.
It is organized as three layers that communicate via JSONL files.

## Layers

### Library layer (src/oanda_autotrader/)
Reusable Python code that talks to OANDA endpoints and returns structured data.
This layer is importable and unit-testable without pygame.

### Script/ops layer (scripts/)
Executable programs that:
- pull/stream candles and write JSONL
- generate features
- train/infer an autoencoder prediction band
- score predictions once future candles exist
- render the live dashboard

### Data layer (data/)
JSONL files are the system contracts:
- candles
- features
- predictions (latest + optional archives)
- prediction scores
- recon status + AE status
- logs

## Core pipeline
1) Candle stream -> JSONL files in data/
2) Feature generation -> data/usd_cad_features.jsonl
3) Prediction writer -> data/predictions_latest.jsonl (overwrite)
4) Scorer -> data/prediction_scores.jsonl (append)
5) Dashboard -> renders candles + recon + prediction band + scores

## Process model
There are three long-running loops:
- Candle stream capture (writes candle JSONL)
- Prediction loop (writes predictions_latest.jsonl)
- Scoring loop (writes prediction_scores.jsonl)

The dashboard can autostart the prediction + scoring loops. Candle capture
still runs separately unless you add an autostart hook for it.

## Design contract
All stages speak JSONL. Latest predictions are written as a single-line
"latest" file to avoid stale schema poisoning; archives are optional.
