Param(
    [switch]$IgnoreQuit = $false,
    [switch]$AutoStart = $true,
    [switch]$UsePythonw = $false,
    [string]$WorkingDir = $null
)

$env:OANDA_DASHBOARD_AUTOSTART = $AutoStart.ToString().ToLower()
$env:OANDA_DASHBOARD_IGNORE_QUIT = $IgnoreQuit.ToString().ToLower()

$exe = if ($UsePythonw) { "pythonw" } else { "python" }
$root = if ($WorkingDir) { $WorkingDir } else { Split-Path -Parent $PSScriptRoot }
$dash = Join-Path $root "scripts\dashboard_pygame.py"

$proc = Start-Process `
    -FilePath $exe `
    -ArgumentList @($dash) `
    -WorkingDirectory $root `
    -PassThru

$pidPath = Join-Path $root "data\dashboard.pid"
New-Item -ItemType Directory -Path (Split-Path -Parent $pidPath) -Force | Out-Null
$proc.Id | Out-File -Encoding ascii $pidPath
