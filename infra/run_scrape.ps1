# Weekly KodiWise scrape, run from Windows Task Scheduler (Monday 09:00).
# Uses your gcloud Application Default Credentials (no key files).
# Log: %LOCALAPPDATA%\KodiWise\logs\scrape_YYYYMMDD.log  (outside the repo)
# Exit code 3 = Jiji returned 403/429 (or robots disallowed): week skipped, no retry.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $env:LOCALAPPDATA "KodiWise\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("scrape_{0:yyyyMMdd}.log" -f (Get-Date))

Set-Location $repo
& (Join-Path $repo ".venv\Scripts\Activate.ps1")
$env:BUCKET = "rent-prediction-ar-kodiwise-scrape"
$env:GOOGLE_CLOUD_PROJECT = "rent-prediction-ar"
if (-not $env:MAX_LISTINGS) { $env:MAX_LISTINGS = "300" }

"=== {0:u} start (MAX_LISTINGS={1}) ===" -f (Get-Date), $env:MAX_LISTINGS | Add-Content $log
python -m data_pipeline.job 2>&1 | Add-Content $log
$code = $LASTEXITCODE
"=== {0:u} exit {1} ===" -f (Get-Date), $code | Add-Content $log
exit $code
