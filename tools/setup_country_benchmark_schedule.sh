#!/usr/bin/env bash
set -euo pipefail
# Requires an already-built image and existing Secret Manager versions.
: "${CLOUD_RUN_PROJECT:?Set CLOUD_RUN_PROJECT}"
: "${CLOUD_RUN_REGION:?Set CLOUD_RUN_REGION}"
: "${BENCHMARK_IMAGE:?Set the image built from this repository}"
: "${BENCHMARK_SERVICE_ACCOUNT:?Set an existing service account email}"
: "${BENCHMARK_CONFIG_DRIVE_ID:?Provision the private config first}"
: "${BENCHMARK_SEED_SECRET:?Set Secret Manager name for BENCHMARK_PASSWORD_SEED}"
: "${BENCHMARK_GOOGLE_SECRET:?Set Secret Manager name for Google service-account JSON}"
job_name="country-benchmarks"
scheduler_name="country-benchmarks-monthly"
env_vars="BENCHMARK_CONFIG_DRIVE_ID=$BENCHMARK_CONFIG_DRIVE_ID"
for key in META_API_VERSION GOOGLE_ADS_API_VERSION GOOGLE_ADS_LOGIN_CUSTOMER_ID; do
  if [[ -n "${!key:-}" ]]; then env_vars+=",$key=${!key}"; fi
done
gcloud run jobs deploy "$job_name" --project="$CLOUD_RUN_PROJECT" --region="$CLOUD_RUN_REGION" \
  --image="$BENCHMARK_IMAGE" --command=python --args=tools/run_country_benchmarks.py \
  --service-account="$BENCHMARK_SERVICE_ACCOUNT" --tasks=1 --parallelism=1 --max-retries=2 --task-timeout=3600s \
  --set-env-vars="$env_vars" \
  --set-secrets="BENCHMARK_PASSWORD_SEED=$BENCHMARK_SEED_SECRET:latest,GOOGLE_SERVICE_ACCOUNT_JSON=$BENCHMARK_GOOGLE_SECRET:latest${BENCHMARK_PLATFORM_SECRETS:+,$BENCHMARK_PLATFORM_SECRETS}"
# The scheduler identity must already have roles/run.invoker on this job.
operation=create
if gcloud scheduler jobs describe "$scheduler_name" --project="$CLOUD_RUN_PROJECT" --location="$CLOUD_RUN_REGION" >/dev/null 2>&1; then operation=update; fi
gcloud scheduler jobs "$operation" http "$scheduler_name" --project="$CLOUD_RUN_PROJECT" --location="$CLOUD_RUN_REGION" \
  --schedule='0 9 8 * *' --time-zone='Europe/Madrid' --http-method=POST \
  --uri="https://run.googleapis.com/v2/projects/$CLOUD_RUN_PROJECT/locations/$CLOUD_RUN_REGION/jobs/$job_name:run" \
  --oauth-service-account-email="$BENCHMARK_SERVICE_ACCOUNT" --oauth-token-scope='https://www.googleapis.com/auth/cloud-platform' \
  --headers='Content-Type=application/json' --message-body='{}'
gcloud scheduler jobs describe "$scheduler_name" --project="$CLOUD_RUN_PROJECT" --location="$CLOUD_RUN_REGION" --format='yaml(name,schedule,timeZone,state)'
