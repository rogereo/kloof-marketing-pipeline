WITH freshness AS (
  SELECT "google_ads_performance_raw" AS source_name, "DAILY" AS cadence, MAX(dt) AS latest_dt FROM `kloof-marketing-pipeline.kloof_bronze.google_ads_performance_raw`
  UNION ALL SELECT "google_ads_clicks", "DAILY", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.google_ads_clicks`
  UNION ALL SELECT "meta_ads_insights_raw", "DAILY", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.meta_ads_insights_raw`
  UNION ALL SELECT "ga4_events", "DAILY", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.ga4_events`
  UNION ALL SELECT "crm_customers", "DAILY_SECURED", MAX(dt) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_customers`
  UNION ALL SELECT "crm_orders", "DAILY", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.crm_orders`
  UNION ALL SELECT "crm_order_items", "DAILY", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.crm_order_items`
  UNION ALL SELECT "creative_copy_raw", "EVENT_DRIVEN", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.creative_copy_raw`
  UNION ALL SELECT "weather_daily", "DAILY", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.weather_daily`
  UNION ALL SELECT "fx_rates", "DAILY", MAX(dt) FROM `kloof-marketing-pipeline.kloof_bronze.fx_rates`
)
SELECT
  source_name,
  cadence,
  latest_dt,
  IF(cadence = "EVENT_DRIVEN", NULL, DATE_SUB(CURRENT_DATE("Africa/Johannesburg"), INTERVAL 1 DAY)) AS expected_dt,
  CASE
    WHEN cadence = "EVENT_DRIVEN" AND latest_dt IS NOT NULL THEN "AVAILABLE"
    WHEN latest_dt >= DATE_SUB(CURRENT_DATE("Africa/Johannesburg"), INTERVAL 1 DAY) THEN "FRESH"
    ELSE "STALE"
  END AS status
FROM freshness
ORDER BY source_name;
