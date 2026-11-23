# Deploys kodiwise-chat (Cloud Run, rent-prediction-ar, africa-south1).
#   .\infra\deploy_chat.ps1 -Model <gemini model id> -DailyCap <global Gemini requests/day> -Rpm <total requests/min>
# The Gemini key is NOT a parameter: it is read by the service from Secret Manager (kodiwise-gemini-key),
# which holds a key from the unbilled project kodiwise-ai-free. Never use a key from a billed project.
param(
    [Parameter(Mandatory)] [string]$Model,
    [Parameter(Mandatory)] [int]$DailyCap,
    [Parameter(Mandatory)] [int]$Rpm,
    [int]$UserDaily = 15
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
        --platform=managed --allow-unauthenticated --memory=512Mi --min-instances=0 --max-instances=2 `
        --set-secrets="GEMINI_API_KEY=kodiwise-gemini-key:latest" `
        --set-env-vars="GEMINI_MODEL=$Model,CHAT_GLOBAL_DAILY_CAP=$DailyCap,CHAT_RPM_CAP=$Rpm,CHAT_MAX_INSTANCES=2,CHAT_USER_DAILY=$UserDaily" `
        --quiet
} finally {
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}
