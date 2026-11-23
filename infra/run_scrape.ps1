# Weekly KodiWise scrape, run from Windows Task Scheduler (Monday 09:00, catch-up after a missed start).
# Launched hidden (see kodiwise_scrape_task.xml): there is no console window to close.
# Uses your gcloud Application Default Credentials (no key files, no stored password).
#
# Log: %LOCALAPPDATA%\KodiWise\logs\scrape_YYYYMMDD.log  (outside the repo)
#   The first line is written before anything else can fail, and the last line
#   ("end ... exit N") is written from a finally block, so every run has both.
#   If the log folder cannot be created, %TEMP%\kodiwise_scrape_fallback.log is used.
# Exit codes: 0 ok | 1 job crashed or lost the network part-way | 2 this script failed before or
#   after the job (e.g. venv missing) | 3 Jiji returned 403/429 or robots disallowed (week skipped, no retry).
# The python job also writes runs/<time>.json to the bucket on failure, if the network is up.
#
# The PC is kept awake while this runs (SetThreadExecutionState, released in the finally block;
# Windows also drops it automatically when this process exits).

$ErrorActionPreference = "Continue"
$code = 2
$script:log = Join-Path $env:TEMP "kodiwise_scrape_fallback.log"

function Stamp { Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz" }
function Write-Log([string]$msg) {
    try { Add-Content -Path $script:log -Value $msg -Encoding UTF8 } catch { }
}

$powerType = $null
try {
    $logDir = Join-Path $env:LOCALAPPDATA "KodiWise\logs"
    try { New-Item -ItemType Directory -Force -Path $logDir | Out-Null } catch { $logDir = $env:TEMP }
    $script:log = Join-Path $logDir ("scrape_{0:yyyyMMdd}.log" -f (Get-Date))

    if (-not $env:MAX_LISTINGS) { $env:MAX_LISTINGS = "300" }
    Write-Log ("=== {0} start (MAX_LISTINGS={1}, pid={2}) ===" -f (Stamp), $env:MAX_LISTINGS, $PID)

    # Keep the system awake while the scrape runs: ES_CONTINUOUS | ES_SYSTEM_REQUIRED.
    try {
        Add-Type -Namespace KodiWise -Name Power -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
        $powerType = [KodiWise.Power]
        [void]$powerType::SetThreadExecutionState([uint32]2147483649)
        Write-Log "sleep prevention on"
    } catch {
        Write-Log ("WARNING: could not prevent sleep: " + $_.Exception.Message)
    }

    $repo = Split-Path -Parent $PSScriptRoot
    Set-Location $repo
    & (Join-Path $repo ".venv\Scripts\Activate.ps1")
    $env:BUCKET = "rent-prediction-ar-kodiwise-scrape"
    $env:GOOGLE_CLOUD_PROJECT = "rent-prediction-ar"

    python -m data_pipeline.job 2>&1 | ForEach-Object { Write-Log ("$_") }
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 2 }
}
catch {
    Write-Log ("ERROR: " + $_.Exception.Message)
    $code = 2
}
finally {
    if ($null -ne $powerType) {
        try { [void]$powerType::SetThreadExecutionState([uint32]2147483648) } catch { }   # ES_CONTINUOUS: release
        Write-Log "sleep prevention released"
    }
    Write-Log ("=== {0} end exit {1} ===" -f (Stamp), $code)
}
exit $code
