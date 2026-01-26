Param(
    [switch]$IgnoreQuit = $false,
    [switch]$AutoStart = $true,
    [string]$WorkingDir = "C:\agent\oanda_autotrader"
)

$env:OANDA_DASHBOARD_AUTOSTART = $AutoStart.ToString().ToLower()
$env:OANDA_DASHBOARD_IGNORE_QUIT = $IgnoreQuit.ToString().ToLower()

Start-Process `
    -FilePath "python" `
    -ArgumentList "scripts/dashboard_pygame.py" `
    -WorkingDirectory $WorkingDir
