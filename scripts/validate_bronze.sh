#!/usr/bin/env bash
set -euo pipefail

# Run in Cloud Shell after create_external_tables.sql and before applying
# secure_crm_customers.sql. If security is already active, run as the
# dataform-runner service account so crm_customers rows are visible.

KLOOF_VALIDATION_DT="${KLOOF_VALIDATION_DT:-2026-03-20}"
KLOOF_LANDING="${KLOOF_LANDING:-${KLOOF_UPLOAD_DIR:?Set KLOOF_UPLOAD_DIR}/landing}"

KLOOF_GAP_ROWS=$(awk 'END {print NR+0}' \
  "$KLOOF_LANDING/google_ads/dt=$KLOOF_VALIDATION_DT/ad_performance.csv")
KLOOF_GAC_ROWS=$(awk 'FNR > 1 {n++} END {print n+0}' \
  "$KLOOF_LANDING/google_ads/dt=$KLOOF_VALIDATION_DT/click_view.csv")
KLOOF_META_ROWS=$(awk 'END {print NR+0}' \
  "$KLOOF_LANDING/meta_ads/dt=$KLOOF_VALIDATION_DT/insights.jsonl")
KLOOF_GA4_ROWS=$(gzip -cd \
  "$KLOOF_LANDING/ga4/dt=$KLOOF_VALIDATION_DT/events.ndjson.gz" | \
  awk 'END {print NR+0}')
KLOOF_CUSTOMERS_ROWS=$(awk 'FNR > 1 {n++} END {print n+0}' \
  "$KLOOF_LANDING/crm/dt=$KLOOF_VALIDATION_DT/customers.csv")
KLOOF_ORDERS_ROWS=$(awk 'FNR > 1 {n++} END {print n+0}' \
  "$KLOOF_LANDING/crm/dt=$KLOOF_VALIDATION_DT/orders.csv")
KLOOF_ITEMS_ROWS=$(awk 'FNR > 1 {n++} END {print n+0}' \
  "$KLOOF_LANDING/crm/dt=$KLOOF_VALIDATION_DT/order_items.csv")
KLOOF_CREATIVE_ROWS=$(find \
  "$KLOOF_LANDING/creatives/dt=$KLOOF_VALIDATION_DT" \
  -type f -name 'copy.txt' -exec awk '{n++} END {print n+0}' {} +)
KLOOF_WEATHER_ROWS=$(find \
  "$KLOOF_LANDING/weather/dt=$KLOOF_VALIDATION_DT" \
  -type f -name '*.json' -exec awk '{n++} END {print n+0}' {} +)
KLOOF_FX_ROWS=$(awk 'FNR > 1 {n++} END {print n+0}' \
  "$KLOOF_LANDING/fx_rates/dt=$KLOOF_VALIDATION_DT/usd_zar.csv")

KLOOF_CREATIVE_FILES=$(find \
  "$KLOOF_LANDING/creatives/dt=$KLOOF_VALIDATION_DT" \
  -type f -name 'copy.txt' | awk 'END {print NR+0}')
KLOOF_WEATHER_FILES=$(find \
  "$KLOOF_LANDING/weather/dt=$KLOOF_VALIDATION_DT" \
  -type f -name '*.json' | awk 'END {print NR+0}')

bq query \
  --location=US \
  --use_legacy_sql=false \
  --format=pretty \
  --parameter=validation_dt:DATE:"$KLOOF_VALIDATION_DT" \
  --parameter=gap_rows:INT64:"$KLOOF_GAP_ROWS" \
  --parameter=gac_rows:INT64:"$KLOOF_GAC_ROWS" \
  --parameter=meta_rows:INT64:"$KLOOF_META_ROWS" \
  --parameter=ga4_rows:INT64:"$KLOOF_GA4_ROWS" \
  --parameter=customers_rows:INT64:"$KLOOF_CUSTOMERS_ROWS" \
  --parameter=orders_rows:INT64:"$KLOOF_ORDERS_ROWS" \
  --parameter=items_rows:INT64:"$KLOOF_ITEMS_ROWS" \
  --parameter=creative_rows:INT64:"$KLOOF_CREATIVE_ROWS" \
  --parameter=weather_rows:INT64:"$KLOOF_WEATHER_ROWS" \
  --parameter=fx_rows:INT64:"$KLOOF_FX_ROWS" \
  --parameter=creative_files:INT64:"$KLOOF_CREATIVE_FILES" \
  --parameter=weather_files:INT64:"$KLOOF_WEATHER_FILES" \
  <<'SQL'
WITH expected AS (
  SELECT 'google_ads_performance_raw' AS table_name, @gap_rows AS local_rows, 1 AS local_files
  UNION ALL SELECT 'google_ads_clicks', @gac_rows, 1
  UNION ALL SELECT 'meta_ads_insights_raw', @meta_rows, 1
  UNION ALL SELECT 'ga4_events', @ga4_rows, 1
  UNION ALL SELECT 'crm_customers', @customers_rows, 1
  UNION ALL SELECT 'crm_orders', @orders_rows, 1
  UNION ALL SELECT 'crm_order_items', @items_rows, 1
  UNION ALL SELECT 'creative_copy_raw', @creative_rows, @creative_files
  UNION ALL SELECT 'weather_daily', @weather_rows, @weather_files
  UNION ALL SELECT 'fx_rates', @fx_rows, 1
),
actual AS (
  SELECT 'google_ads_performance_raw' AS table_name, COUNT(*) AS bq_rows,
         COUNT(DISTINCT _FILE_NAME) AS bq_files
  FROM `kloof-marketing-pipeline.kloof_bronze.google_ads_performance_raw`
  WHERE dt = @validation_dt
  UNION ALL
  SELECT 'google_ads_clicks', COUNT(*), COUNT(DISTINCT _FILE_NAME)
  FROM `kloof-marketing-pipeline.kloof_bronze.google_ads_clicks`
  WHERE dt = @validation_dt
  UNION ALL
  SELECT 'meta_ads_insights_raw', COUNT(*), COUNT(DISTINCT _FILE_NAME)
  FROM `kloof-marketing-pipeline.kloof_bronze.meta_ads_insights_raw`
  WHERE dt = @validation_dt
  UNION ALL
  SELECT 'ga4_events', COUNT(*), COUNT(DISTINCT _FILE_NAME)
  FROM `kloof-marketing-pipeline.kloof_bronze.ga4_events`
  WHERE dt = @validation_dt
  UNION ALL
  SELECT 'crm_customers', COUNT(*), COUNT(DISTINCT _FILE_NAME)
  FROM `kloof-marketing-pipeline.kloof_bronze.crm_customers`
  WHERE dt = @validation_dt
  UNION ALL
  SELECT 'crm_orders', COUNT(*), COUNT(DISTINCT _FILE_NAME)
  FROM `kloof-marketing-pipeline.kloof_bronze.crm_orders`
  WHERE dt = @validation_dt
  UNION ALL
  SELECT 'crm_order_items', COUNT(*), COUNT(DISTINCT _FILE_NAME)
  FROM `kloof-marketing-pipeline.kloof_bronze.crm_order_items`
  WHERE dt = @validation_dt
  UNION ALL
  SELECT 'creative_copy_raw', COUNT(*), COUNT(DISTINCT _FILE_NAME)
  FROM `kloof-marketing-pipeline.kloof_bronze.creative_copy_raw`
  WHERE dt = @validation_dt
  UNION ALL
  SELECT 'weather_daily', COUNT(*), COUNT(DISTINCT _FILE_NAME)
  FROM `kloof-marketing-pipeline.kloof_bronze.weather_daily`
  WHERE dt = @validation_dt
  UNION ALL
  SELECT 'fx_rates', COUNT(*), COUNT(DISTINCT _FILE_NAME)
  FROM `kloof-marketing-pipeline.kloof_bronze.fx_rates`
  WHERE dt = @validation_dt
)
SELECT
  table_name,
  local_rows,
  bq_rows,
  local_files,
  bq_files,
  IF(local_rows = bq_rows AND local_files = bq_files, 'PASS', 'FAIL') AS status
FROM expected
JOIN actual USING (table_name)
ORDER BY table_name;
SQL
