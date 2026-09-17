WITH checks AS (
  SELECT "All DQ codes have blocking assertions" AS check_name, CAST(COUNT(*) AS STRING) AS observed, "12" AS expected, COUNT(*) = 12 AS passed
  FROM `kloof-marketing-pipeline.kloof_ops.INFORMATION_SCHEMA.TABLES`
  WHERE STARTS_WITH(table_name, "assert_dq")

  UNION ALL
  SELECT "Gold order count reconciles", CONCAT(CAST((SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) AS STRING), "/", CAST((SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_gold.fct_orders`) AS STRING)), "equal", (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) = (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_gold.fct_orders`)

  UNION ALL
  SELECT "Gold revenue reconciles", CONCAT(CAST((SELECT SUM(IF(status = "completed", revenue, 0)) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) AS STRING), "/", CAST((SELECT SUM(completed_revenue) FROM `kloof-marketing-pipeline.kloof_gold.fct_orders`) AS STRING)), "equal", ABS((SELECT SUM(IF(status = "completed", revenue, 0)) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) - (SELECT SUM(completed_revenue) FROM `kloof-marketing-pipeline.kloof_gold.fct_orders`)) <= 0.01

  UNION ALL
  SELECT "Gold spend reconciles", CONCAT(CAST(((SELECT SUM(cost_zar) FROM `kloof-marketing-pipeline.kloof_silver.stg_google_ads_performance`) + (SELECT SUM(spend_zar) FROM `kloof-marketing-pipeline.kloof_silver.stg_meta_ads`)) AS STRING), "/", CAST((SELECT SUM(spend_zar) FROM `kloof-marketing-pipeline.kloof_gold.fct_ad_spend_daily`) AS STRING)), "equal", ABS(((SELECT SUM(cost_zar) FROM `kloof-marketing-pipeline.kloof_silver.stg_google_ads_performance`) + (SELECT SUM(spend_zar) FROM `kloof-marketing-pipeline.kloof_silver.stg_meta_ads`)) - (SELECT SUM(spend_zar) FROM `kloof-marketing-pipeline.kloof_gold.fct_ad_spend_daily`)) <= 0.01
)
SELECT check_name, observed, expected, IF(passed, "PASS", "FAIL") AS status FROM checks ORDER BY check_name;
