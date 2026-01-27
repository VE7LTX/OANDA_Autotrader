Param(
    [string]$Mode = "live",
    [string]$Account = "Primary",
    [string]$Instrument = "USD_CAD",
    [int]$Seconds = 600,
    [string]$Output = "data\stream_latency.jsonl",
    [switch]$UsePythonw = $false,
    [string]$WorkingDir = $null
)

$exe = if ($UsePythonw) { "pythonw" } else { "python" }
$root = if ($WorkingDir) { $WorkingDir } else { Split-Path -Parent $PSScriptRoot }
$script = Join-Path $root "scripts\capture_latency.py"
$safeInstrument = $Instrument -replace "[\\/:]", "_"
$pidPath = Join-Path $root ("data\capture_{0}_{1}.pid" -f $Mode, $safeInstrument)

New-Item -ItemType Directory -Path (Split-Path -Parent $pidPath) -Force | Out-Null

$proc = Start-Process `
    -FilePath $exe `
    -ArgumentList @(
        $script,
        "--mode", $Mode,
        "--account", $Account,
        "--instrument", $Instrument,
        "--seconds", $Seconds,
        "--output", $Output,
        "--pid-file", $pidPath
    ) `
    -WorkingDirectory $root `
    -PassThru

$proc.Id | Out-File -Encoding ascii $pidPath
