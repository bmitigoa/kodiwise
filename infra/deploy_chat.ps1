# Deploys kodiwise-chat (Cloud Run, rent-prediction-ar, africa-south1).
#   .\infra\deploy_chat.ps1 -Models "<primary id>,<fallback id>" -DailyCap <requests/day PER MODEL> -Rpm <requests/min PER MODEL>
# Each model has its own free quota, so caps are per model. Runs as the dedicated service account
# kodiwise-chat@rent-prediction-ar (secretAccessor on the key, datastore.user on kodiwise-9adab) and nothing else.
# The Gemini key is NOT a parameter: it is read by the service from Secret Manager (kodiwise-gemini-key),
# which holds a key from the unbilled project kodiwise-ai-free. Never use a key from a billed project.
param(
    [Parameter(Mandatory)] [string]$Models,
    [Parameter(Mandatory)] [int]$DailyCap,
    [Parameter(Mandatory)] [int]$Rpm,
    [int]$UserDaily = 10
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $env:TEMP ("kodiwise-chat-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $stage, "$stage\chat", "$stage\agent", "$stage\data\reference" | Out-Null
try {
    Get-ChildItem "$repo\chat" -File | Where-Object { $_.Extension -in ".py", ".txt" -and $_.Name -ne "model_eval.py" } | Copy-Item -Destination "$stage\chat"
    Copy-Item "$repo\agent\__init__.py" "$stage\agent\"
    Copy-Item "$repo\agent\core" "$stage\agent\core" -Recurse -Exclude "__pycache__"
    Copy-Item "$repo\data\reference\neighbourhood_centroids.csv" "$stage\data\reference\"
    Copy-Item "$repo\infra\chat\Dockerfile" "$stage\Dockerfile"
    gcloud run deploy kodiwise-chat --source=$stage --project=rent-prediction-ar --region=africa-south1 `
        --platform=managed --allow-unauthenticated --memory=512Mi --min-instances=0 --max-instances=1 `
        --service-account="kodiwise-chat@rent-prediction-ar.iam.gserviceaccount.com" `
        --set-secrets="GEMINI_API_KEY=kodiwise-gemini-key:latest" `
        --set-env-vars="^@^CHAT_MODELS=$Models@CHAT_GLOBAL_DAILY_CAP=$DailyCap@CHAT_RPM_CAP=$Rpm@CHAT_MAX_INSTANCES=1@CHAT_USER_DAILY=$UserDaily@CHAT_COUNTERS_PROJECT=rent-prediction-ar@CHAT_COUNTERS_DATABASE=kodiwise-counters" `
        --quiet
} finally {
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}
