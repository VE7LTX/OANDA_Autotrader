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

Start-Process `
    -FilePath $exe `
    -ArgumentList "scripts/dashboard_pygame.py" `
    -WorkingDirectory $root
