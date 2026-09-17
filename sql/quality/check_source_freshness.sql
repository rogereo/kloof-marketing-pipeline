WITH freshness AS (
  SELECT "google_ads_performance_raw" AS source_name, MAX(dt) AS latest_dt FROM `kloof-marketing-pipeline.kloof_bronze.google_ads_performance_raw`
  UNION ALL SELECT "google_ads_clicks", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.google_ads_clicks`
  UNION ALL SELECT "meta_ads_insights_raw", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.meta_ads_insights_raw`
  UNION ALL SELECT "ga4_events", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.ga4_events`
  UNION ALL SELECT "crm_customers", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.crm_customers`
  UNION ALL SELECT "crm_orders", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.crm_orders`
  UNION ALL SELECT "crm_order_items", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.crm_order_items`
  UNION ALL SELECT "creative_copy_raw", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.creative_copy_raw`
  UNION ALL SELECT "weather_daily", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.weather_daily`
  UNION ALL SELECT "fx_rates", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.fx_rates`
)
SELECT
  source_name,
  latest_dt,
  DATE_SUB(CURRENT_DATE("Africa/Johannesburg"), INTERVAL 1 DAY) AS expected_dt,
  IF(latest_dt >= DATE_SUB(CURRENT_DATE("Africa/Johannesburg"), INTERVAL 1 DAY), "FRESH", "STALE") AS status
FROM freshness
ORDER BY source_name;
