# Re-run the six demo questions on one Gemini model (about 12 free-tier requests).
#   .\infra\eval_chat_model.ps1 gemini-3.1-flash-lite
# Reads the key from Secret Manager into this process only; nothing is printed or stored.
# 6/6 means the model can be added as a fallback with one redeploy:
#   .\infra\deploy_chat.ps1 -Models "gemini-3.5-flash-lite,<model>" -DailyCap 300 -Rpm 12
param([Parameter(Mandatory)] [string]$Model, [double]$Pause = 6.5)
$ErrorActionPreference = "Stop"
$env:GEMINI_API_KEY = (gcloud secrets versions access latest --secret=kodiwise-gemini-key --project=rent-prediction-ar).Trim()
try { python -m chat.model_eval $Model --pause $Pause } finally { Remove-Item Env:GEMINI_API_KEY }
