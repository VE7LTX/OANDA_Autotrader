Param(
    [switch]$IgnoreQuit = $false,
    [switch]$AutoStart = $true,
    [switch]$UsePythonw = $false,
    [switch]$RedirectLogs = $false,
    [string]$StdoutPath = $null,
    [string]$StderrPath = $null,
    [string]$WorkingDir = $null
)

$env:OANDA_DASHBOARD_AUTOSTART = $AutoStart.ToString().ToLower()
$env:OANDA_DASHBOARD_IGNORE_QUIT = $IgnoreQuit.ToString().ToLower()

$exe = if ($UsePythonw) { "pythonw" } else { "python" }
$root = if ($WorkingDir) { $WorkingDir } else { Split-Path -Parent $PSScriptRoot }
$dash = Join-Path $root "scripts\dashboard_pygame.py"
$stdout = if ($StdoutPath) { $StdoutPath } else { Join-Path $root "data\dashboard_stdout.log" }
$stderr = if ($StderrPath) { $StderrPath } else { Join-Path $root "data\dashboard_stderr.log" }

if ($RedirectLogs -and -not $UsePythonw) {
    $proc = Start-Process `
        -FilePath $exe `
        -ArgumentList @($dash) `
        -WorkingDirectory $root `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -PassThru
} else {
    $proc = Start-Process `
        -FilePath $exe `
        -ArgumentList @($dash) `
        -WorkingDirectory $root `
        -PassThru
}

$pidPath = Join-Path $root "data\dashboard.pid"
New-Item -ItemType Directory -Path (Split-Path -Parent $pidPath) -Force | Out-Null
$proc.Id | Out-File -Encoding ascii $pidPath
