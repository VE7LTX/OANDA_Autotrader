Param(
    [switch]$UsePythonw = $false,
    [switch]$Clean = $false,
    [string]$WorkingDir = $null
)

$root = if ($WorkingDir) { $WorkingDir } else { Split-Path -Parent $PSScriptRoot }

Write-Host "Launching capture + dashboard (detached)..."
Write-Host "Working dir: $root"

if ($Clean) {
    Write-Host "Stopping existing trainer/scorer/capture/guard/dashboard processes..."
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match "train_autoencoder_loop.py|score_predictions.py|capture_usd_cad_stream.py|dashboard_pygame.py" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -match "guard_workers.ps1|launch_capture.ps1|launch_dashboard.ps1" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

# Launch capture (console so Ctrl+C is possible if run directly)
Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $root "scripts\launch_capture.ps1"),
    "-WorkingDir", $root
) | Out-Null

# Launch dashboard (detached)
$dashArgs = @()
if ($UsePythonw) { $dashArgs += "-UsePythonw" }
$dashArgsList = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $root "scripts\launch_dashboard.ps1")
)
$dashArgsList += $dashArgs
Start-Process -FilePath "powershell" -ArgumentList $dashArgsList | Out-Null

# Launch worker guard (keeps trainer/scorer alive)
Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $root "scripts\guard_workers.ps1"),
    "-WorkingDir", $root
) | Out-Null

Write-Host "Launch complete."
