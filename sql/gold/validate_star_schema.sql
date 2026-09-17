WITH metrics AS (
  SELECT
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_gold.dim_date`) AS date_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT calendar_date) FROM `kloof-marketing-pipeline.kloof_gold.dim_date`) AS duplicate_dates,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_gold.dim_customer`) AS customer_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT customer_key) FROM `kloof-marketing-pipeline.kloof_gold.dim_customer`) AS duplicate_customers,
    (SELECT COUNTIF(is_internal_customer) FROM `kloof-marketing-pipeline.kloof_gold.dim_customer`) AS internal_customers,
    (SELECT COUNT(*) - COUNT(DISTINCT CONCAT(platform, "|", campaign_id)) FROM `kloof-marketing-pipeline.kloof_gold.dim_campaign`) AS duplicate_campaigns,
    (SELECT COUNTIF(ARRAY_LENGTH(campaign_name_history) > 1) FROM `kloof-marketing-pipeline.kloof_gold.dim_campaign`) AS renamed_campaigns,
    (SELECT COUNT(*) - COUNT(DISTINCT CONCAT(platform, "|", ad_id)) FROM `kloof-marketing-pipeline.kloof_gold.dim_ad`) AS duplicate_ads,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_gold.fct_sessions`) AS gold_sessions,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.int_sessions`) AS silver_sessions,
    (SELECT COUNT(*) - COUNT(DISTINCT session_key) FROM `kloof-marketing-pipeline.kloof_gold.fct_sessions`) AS duplicate_sessions,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_gold.fct_orders`) AS gold_orders,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) AS silver_orders,
    (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM `kloof-marketing-pipeline.kloof_gold.fct_orders`) AS duplicate_orders,
    (SELECT COUNTIF(is_test_order) FROM `kloof-marketing-pipeline.kloof_gold.fct_orders`) AS test_orders,
    (SELECT SUM(completed_revenue) FROM `kloof-marketing-pipeline.kloof_gold.fct_orders`) AS gold_completed_revenue,
    (SELECT SUM(IF(status = "completed", revenue, 0)) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) AS silver_completed_revenue,
    (SELECT COUNT(*) - COUNT(DISTINCT CONCAT(CAST(spend_date AS STRING), "|", platform, "|", ad_id)) FROM `kloof-marketing-pipeline.kloof_gold.fct_ad_spend_daily`) AS duplicate_ad_spend,
    (SELECT COUNTIF(spend_zar < 0 OR spend_zar IS NULL) FROM `kloof-marketing-pipeline.kloof_gold.fct_ad_spend_daily`) AS invalid_ad_spend,
    ((SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_gold.dim_customer`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_gold.dim_campaign`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_gold.dim_ad`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_gold.fct_ad_spend_daily`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_gold.fct_sessions`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_gold.fct_orders`)) AS missing_lineage
)

SELECT check_name, observed, expected, IF(passed, "PASS", "FAIL") AS status
FROM metrics,
UNNEST([
  STRUCT("Date dimension populated" AS check_name, CAST(date_rows AS STRING) AS observed, "> 0" AS expected, date_rows > 0 AS passed),
  STRUCT("Date keys unique", CAST(duplicate_dates AS STRING), "0", duplicate_dates = 0),
  STRUCT("Customer dimension populated", CAST(customer_rows AS STRING), "> 0", customer_rows > 0),
  STRUCT("Customer keys unique", CAST(duplicate_customers AS STRING), "0", duplicate_customers = 0),
  STRUCT("Internal customers excluded", CAST(internal_customers AS STRING), "0", internal_customers = 0),
  STRUCT("Campaign keys unique", CAST(duplicate_campaigns AS STRING), "0", duplicate_campaigns = 0),
  STRUCT("Campaign rename history retained", CAST(renamed_campaigns AS STRING), "> 0", renamed_campaigns > 0),
  STRUCT("Ad keys unique", CAST(duplicate_ads AS STRING), "0", duplicate_ads = 0),
  STRUCT("Session totals reconcile", CONCAT(CAST(gold_sessions AS STRING), "/", CAST(silver_sessions AS STRING)), "equal", gold_sessions = silver_sessions),
  STRUCT("Session keys unique", CAST(duplicate_sessions AS STRING), "0", duplicate_sessions = 0),
  STRUCT("Order totals reconcile", CONCAT(CAST(gold_orders AS STRING), "/", CAST(silver_orders AS STRING)), "equal", gold_orders = silver_orders),
  STRUCT("Order keys unique", CAST(duplicate_orders AS STRING), "0", duplicate_orders = 0),
  STRUCT("QA orders excluded", CAST(test_orders AS STRING), "0", test_orders = 0),
  STRUCT("Completed revenue reconciles", CONCAT(CAST(gold_completed_revenue AS STRING), "/", CAST(silver_completed_revenue AS STRING)), "equal", gold_completed_revenue = silver_completed_revenue),
  STRUCT("Ad spend grain unique", CAST(duplicate_ad_spend AS STRING), "0", duplicate_ad_spend = 0),
  STRUCT("Ad spend valid", CAST(invalid_ad_spend AS STRING), "0", invalid_ad_spend = 0),
  STRUCT("Source lineage retained", CAST(missing_lineage AS STRING), "0 missing", missing_lineage = 0)
])
ORDER BY check_name;
