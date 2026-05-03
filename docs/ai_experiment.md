# AI Experiment

Current phase:
- Practice account only.
- Dry-run first, then explicit `--submit` for practice execution.
- Real-account trading is intentionally out of scope for the first implementation.
- The deterministic bot is the primary trading path for now.
- External AI is deferred to an oversight role until the deterministic bot is stable.

Editable example files:
- `.env.example`
- `accounts.yaml.example`
- `decision.example.json`

If any of those example files are removed, regenerate them with:

```bash
python scripts/bootstrap_example_files.py
```

AI runner modes:
- `heuristic`: built-in baseline for end-to-end validation.
- `json-file`: lets an external AI write a decision file that the runner validates and executes.

Dry-run example:

```bash
python scripts/run_ai_experiment.py --instrument USD_CAD --dry-run
```

External decision-file example:

```bash
python scripts/run_ai_experiment.py --decision-source json-file --decision-file decision.example.json --dry-run
```
