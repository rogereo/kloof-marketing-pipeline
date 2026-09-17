WITH metrics AS (
  SELECT
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.stg_google_ads_performance`) AS google_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT CONCAT(CAST(performance_date AS STRING), "|", ad_id)) FROM `kloof-marketing-pipeline.kloof_silver.stg_google_ads_performance`) AS duplicate_google_rows,
    (SELECT COUNTIF(cost_zar IS NULL OR cost_zar < 0) FROM `kloof-marketing-pipeline.kloof_silver.stg_google_ads_performance`) AS invalid_google_cost,
    (SELECT COUNTIF(performance_date < DATE "2026-09-01" AND all_conversions IS NOT NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_google_ads_performance`) AS unexpected_old_all_conversions,
    (SELECT COUNTIF(performance_date >= DATE "2026-09-01" AND all_conversions IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_google_ads_performance`) AS missing_new_all_conversions,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.stg_meta_ads`) AS meta_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT CONCAT(ad_id, "|", CAST(insight_date AS STRING))) FROM `kloof-marketing-pipeline.kloof_silver.stg_meta_ads`) AS duplicate_meta_rows,
    (SELECT COUNTIF(spend_zar IS NULL OR spend_zar < 0) FROM `kloof-marketing-pipeline.kloof_silver.stg_meta_ads`) AS invalid_meta_spend,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.quarantine_meta_ads`) AS quarantined_meta_lines,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.stg_creatives`) AS creative_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT ad_id) FROM `kloof-marketing-pipeline.kloof_silver.stg_creatives`) AS duplicate_creatives,
    (SELECT COUNTIF(ad_id IS NULL OR NOT ENDS_WITH(source_file_name, CONCAT("/ad_", ad_id, "/copy.txt"))) FROM `kloof-marketing-pipeline.kloof_silver.stg_creatives`) AS invalid_creative_lineage,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.stg_weather`) AS weather_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT CONCAT(city_standard, "|", CAST(weather_date AS STRING))) FROM `kloof-marketing-pipeline.kloof_silver.stg_weather`) AS duplicate_weather_rows,
    (SELECT COUNTIF(city_standard NOT IN ("Cape Town", "Johannesburg", "Durban") OR temperature_max_c IS NULL OR temperature_min_c IS NULL OR precipitation_mm IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_weather`) AS invalid_weather_rows,
    ((SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_google_ads_performance`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_meta_ads`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.quarantine_meta_ads`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_creatives`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_weather`)) AS missing_lineage
)

SELECT check_name, observed, expected, IF(passed, "PASS", "FAIL") AS status
FROM metrics,
UNNEST([
  STRUCT("Google performance loaded" AS check_name, CAST(google_rows AS STRING) AS observed, "> 0" AS expected, google_rows > 0 AS passed),
  STRUCT("Google performance keys unique", CAST(duplicate_google_rows AS STRING), "0", duplicate_google_rows = 0),
  STRUCT("Google cost converted", CAST(invalid_google_cost AS STRING), "0 invalid", invalid_google_cost = 0),
  STRUCT("Old Google schema handled", CAST(unexpected_old_all_conversions AS STRING), "0 shifted rows", unexpected_old_all_conversions = 0),
  STRUCT("New Google schema handled", CAST(missing_new_all_conversions AS STRING), "0 missing", missing_new_all_conversions = 0),
  STRUCT("Meta insights loaded", CAST(meta_rows AS STRING), "> 0", meta_rows > 0),
  STRUCT("Latest Meta pull unique", CAST(duplicate_meta_rows AS STRING), "0", duplicate_meta_rows = 0),
  STRUCT("Meta spend converted to ZAR", CAST(invalid_meta_spend AS STRING), "0 invalid", invalid_meta_spend = 0),
  STRUCT("Broken Meta lines quarantined", CAST(quarantined_meta_lines AS STRING), "> 0", quarantined_meta_lines > 0),
  STRUCT("Creatives loaded", CAST(creative_rows AS STRING), "> 0", creative_rows > 0),
  STRUCT("Creative ad IDs unique", CAST(duplicate_creatives AS STRING), "0", duplicate_creatives = 0),
  STRUCT("Creative IDs derived from lineage", CAST(invalid_creative_lineage AS STRING), "0 invalid", invalid_creative_lineage = 0),
  STRUCT("Weather loaded", CAST(weather_rows AS STRING), "> 0", weather_rows > 0),
  STRUCT("Weather city-date keys unique", CAST(duplicate_weather_rows AS STRING), "0", duplicate_weather_rows = 0),
  STRUCT("Weather arrays zipped", CAST(invalid_weather_rows AS STRING), "0 invalid", invalid_weather_rows = 0),
  STRUCT("Source lineage retained", CAST(missing_lineage AS STRING), "0 missing", missing_lineage = 0)
])
ORDER BY check_name;
