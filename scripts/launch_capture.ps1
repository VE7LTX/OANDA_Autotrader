Param(
    [string]$WorkingDir = $null
)

$root = if ($WorkingDir) { $WorkingDir } else { Split-Path -Parent $PSScriptRoot }
$env:PYTHONPATH = "src"

Write-Host "Starting USD_CAD candle capture..."
Write-Host "Press Ctrl+C to stop."
Write-Host "Working dir: $root"

Push-Location $root
try {
    python scripts\capture_usd_cad_stream.py
} finally {
    Pop-Location
}
