#!/usr/bin/env bash
# Thursday and Friday morning: write yesterday's data, then push the new folders to GCS.
# Usage: BUCKET=your-bucket-name ./scripts/daily.sh
set -euo pipefail
: "${BUCKET:?Set BUCKET, e.g. BUCKET=kloof-landing ./scripts/daily.sh}"
python -m sim daily
gcloud storage rsync output/landing "gs://${BUCKET}/landing" --recursive
python -m pytest -q
