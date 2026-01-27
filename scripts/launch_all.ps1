Param(
    [switch]$UsePythonw = $false,
    [string]$WorkingDir = $null
)

$root = if ($WorkingDir) { $WorkingDir } else { Split-Path -Parent $PSScriptRoot }

Write-Host "Launching capture + dashboard (detached)..."
Write-Host "Working dir: $root"

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

Write-Host "Launch complete."
