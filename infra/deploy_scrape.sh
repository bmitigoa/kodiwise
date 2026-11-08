#!/usr/bin/env bash
# Weekly scrape job in project rent-prediction-ar. Already applied 2026-11-08;
# kept as the record of what exists. Cloud Scheduler has no africa-south1, so
# the schedule lives in me-west1 and calls the Cloud Run API for the job.
set -euo pipefail
P=rent-prediction-ar; R=africa-south1; B=rent-prediction-ar-kodiwise-scrape
IMG=$R-docker.pkg.dev/$P/kodiwise/scrape:v1
SA=kodiwise-scraper@$P.iam.gserviceaccount.com      # job identity: bucket objectAdmin only
SCH=kodiwise-scheduler@$P.iam.gserviceaccount.com   # scheduler identity: run.invoker on the job only

gcloud storage buckets create gs://$B --project $P --location $R --uniform-bucket-level-access --public-access-prevention
gcloud iam service-accounts create kodiwise-scraper --project $P
gcloud iam service-accounts create kodiwise-scheduler --project $P
gcloud storage buckets add-iam-policy-binding gs://$B --member serviceAccount:$SA --role roles/storage.objectAdmin
gcloud artifacts repositories create kodiwise --repository-format docker --location $R --project $P
gcloud artifacts repositories set-cleanup-policies kodiwise --location $R --project $P --policy infra/ar-cleanup-policy.json --no-dry-run
gcloud builds submit . --config infra/cloudbuild.scrape.yaml --substitutions _IMAGE=$IMG --project $P --region $R --gcs-source-staging-dir gs://$B/_build/source
gcloud run jobs create kodiwise-scrape-weekly --image $IMG --region $R --project $P --service-account $SA \
  --task-timeout 3600s --max-retries 1 --tasks 1 --cpu 1 --memory 1Gi --set-env-vars MAX_LISTINGS=300,BUCKET=$B
gcloud run jobs add-iam-policy-binding kodiwise-scrape-weekly --region $R --project $P --member serviceAccount:$SCH --role roles/run.invoker
gcloud scheduler jobs create http kodiwise-scrape-weekly --location me-west1 --project $P \
  --schedule "0 3 * * 1" --time-zone Africa/Nairobi --max-retry-attempts 0 \
  --uri "https://run.googleapis.com/v2/projects/$P/locations/$R/jobs/kodiwise-scrape-weekly:run" \
  --http-method POST --oauth-service-account-email $SCH
