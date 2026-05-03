from scripts.dashboard_pygame import build_prediction_command, build_score_command


def test_build_prediction_command() -> None:
    cmd = build_prediction_command(
        script_path="scripts/train_autoencoder_loop.py",
        features_path="data/features.jsonl",
        retrain_interval=60,
        epochs=1,
        horizon=12,
        interval_secs=5,
        archive=True,
    )
    assert cmd[:2] == [cmd[0], "scripts/train_autoencoder_loop.py"]
    assert "--features" in cmd
    assert "--archive-predictions" in cmd


def test_build_score_command() -> None:
    cmd = build_score_command(script_path="scripts/score_predictions.py", every_seconds=10)
    assert cmd[1:] == ["scripts/score_predictions.py", "--watch", "--every", "10"]
