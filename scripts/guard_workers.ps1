Param(
    [string]$WorkingDir = $null,
    [int]$PredStaleSeconds = 120,
    [int]$ScoreStaleSeconds = 300,
    [int]$CheckEverySeconds = 10,
    [int]$ScoreEverySeconds = 10,
    [string]$FeaturesPath = "data/usd_cad_features.jsonl",
    [int]$PredRetrainInterval = 60,
    [int]$PredEpochs = 1,
    [int]$PredHorizon = 12,
    [int]$PredIntervalSecs = 5
)

$root = if ($WorkingDir) { $WorkingDir } else { Split-Path -Parent $PSScriptRoot }
Set-Location $root

function Get-FileAgeSeconds([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    $item = Get-Item $Path
    return (New-TimeSpan -Start $item.LastWriteTime -End (Get-Date)).TotalSeconds
}

function Get-ProcessByPattern([string]$pattern) {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match $pattern }
}

function Start-Trainer {
    Start-Process -FilePath "python" -WindowStyle Hidden -ArgumentList @(
        "scripts/train_autoencoder_loop.py",
        "--features", $FeaturesPath,
        "--retrain-interval", "$PredRetrainInterval",
        "--epochs", "$PredEpochs",
        "--horizon", "$PredHorizon",
        "--interval-secs", "$PredIntervalSecs"
    ) -WorkingDirectory $root | Out-Null
}

function Start-Scorer {
    Start-Process -FilePath "python" -WindowStyle Hidden -ArgumentList @(
        "scripts/score_predictions.py",
        "--watch",
        "--every", "$ScoreEverySeconds"
    ) -WorkingDirectory $root | Out-Null
}

while ($true) {
    $predAge = Get-FileAgeSeconds "data/predictions_latest.jsonl"
    $scoreAge = Get-FileAgeSeconds "data/prediction_scores.jsonl"

    $trainerProcs = @(Get-ProcessByPattern "train_autoencoder_loop.py")
    $scorerProcs = @(Get-ProcessByPattern "score_predictions.py")

    if ($predAge -eq $null -or $predAge -gt $PredStaleSeconds) {
        if ($trainerProcs.Count -gt 0) {
            $trainerProcs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        }
        Start-Trainer
    } elseif ($trainerProcs.Count -eq 0) {
        Start-Trainer
    }

    if ($scoreAge -eq $null -or $scoreAge -gt $ScoreStaleSeconds) {
        if ($scorerProcs.Count -gt 0) {
            $scorerProcs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        }
        Start-Scorer
    } elseif ($scorerProcs.Count -eq 0) {
        Start-Scorer
    }

    Start-Sleep -Seconds $CheckEverySeconds
}
