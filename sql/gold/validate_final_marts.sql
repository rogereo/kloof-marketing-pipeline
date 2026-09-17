WITH customer_metrics AS (
  SELECT
    COUNT(*) AS customer_rows,
    COUNT(DISTINCT customer_key) AS distinct_customers,
    COUNTIF(predicted_value_90d < 0) AS invalid_predictions,
    COUNTIF(
      acquisition_ad_id IS NOT NULL
      AND acquisition_creative_tone IS NULL
    ) AS missing_creative_features,
    COUNTIF(dt IS NULL OR source_file_name IS NULL) AS missing_lineage
  FROM `kloof-marketing-pipeline.kloof_gold.mart_customer_value`
),

campaign_metrics AS (
  SELECT
    COUNT(*) AS campaign_rows,
    COUNT(DISTINCT TO_JSON_STRING(STRUCT(
      week_start_date, platform, campaign_id
    ))) AS distinct_campaign_grains,
    COUNTIF(
      spend_zar < 0
      OR claimed_revenue_zar < 0
      OR real_revenue_zar < 0
      OR predicted_value_90d < 0
      OR one_time_buyer_share NOT BETWEEN 0 AND 1
    ) AS invalid_campaign_metrics,
    COUNTIF(
      spend_zar > 0
      AND ABS(
        value_adjusted_roas
        - SAFE_DIVIDE(first_order_revenue_zar + predicted_value_90d, spend_zar)
      ) > 0.000001
    ) AS invalid_value_adjusted_roas,
    COUNTIF(dt IS NULL OR source_file_name IS NULL) AS missing_lineage
  FROM `kloof-marketing-pipeline.kloof_gold.mart_campaign_value`
),

driver_metrics AS (
  SELECT
    COUNT(*) AS driver_rows,
    COUNT(DISTINCT TO_JSON_STRING(STRUCT(
      week_start_date, platform, campaign_id, city_standard
    ))) AS distinct_driver_grains,
    COUNTIF(
      city_standard NOT IN ("Cape Town", "Johannesburg", "Durban")
      OR attributed_sessions < 0
      OR real_orders < 0
      OR real_revenue_zar < 0
      OR allocated_spend_zar < 0
      OR avg_temperature_max_c < avg_temperature_min_c
      OR total_precipitation_mm < 0
    ) AS invalid_driver_metrics,
    COUNTIF(
      allocated_spend_zar > 0
      AND (dominant_tone IS NULL OR dominant_cta IS NULL)
    ) AS missing_creative_features,
    COUNTIF(dt IS NULL OR source_file_name IS NULL) AS missing_lineage
  FROM `kloof-marketing-pipeline.kloof_gold.mart_campaign_drivers`
),

reconciliation AS (
  SELECT
    (SELECT SUM(spend_zar)
     FROM `kloof-marketing-pipeline.kloof_gold.fct_ad_spend_daily`) AS fact_spend,
    (SELECT SUM(spend_zar)
     FROM `kloof-marketing-pipeline.kloof_gold.mart_campaign_value`) AS mart_spend,
    (SELECT SUM(claimed_revenue_zar)
     FROM `kloof-marketing-pipeline.kloof_gold.fct_ad_spend_daily`) AS fact_claimed_revenue,
    (SELECT SUM(claimed_revenue_zar)
     FROM `kloof-marketing-pipeline.kloof_gold.mart_campaign_value`) AS mart_claimed_revenue,
    (SELECT SUM(completed_revenue)
     FROM `kloof-marketing-pipeline.kloof_gold.fct_orders`
     WHERE attributed_platform IN ("google", "meta") AND campaign_id IS NOT NULL) AS fact_attributed_revenue,
    (SELECT SUM(real_revenue_zar)
     FROM `kloof-marketing-pipeline.kloof_gold.mart_campaign_value`) AS mart_attributed_revenue,
    (SELECT SUM(predicted_value_90d)
     FROM `kloof-marketing-pipeline.kloof_gold.mart_customer_value`
     WHERE acquisition_platform IN ("google", "meta") AND acquisition_campaign_id IS NOT NULL) AS customer_predicted_value,
    (SELECT SUM(predicted_value_90d)
     FROM `kloof-marketing-pipeline.kloof_gold.mart_campaign_value`) AS campaign_predicted_value
),

story AS (
  SELECT
    campaign_id,
    SAFE_DIVIDE(SUM(claimed_revenue_zar), SUM(spend_zar)) AS platform_roas,
    SAFE_DIVIDE(
      SUM(first_order_revenue_zar) + SUM(predicted_value_90d),
      SUM(spend_zar)
    ) AS value_adjusted_roas
  FROM `kloof-marketing-pipeline.kloof_gold.mart_campaign_value`
  WHERE campaign_id IN ("120210040000000000", "21873002")
  GROUP BY campaign_id
),

story_pivot AS (
  SELECT
    MAX(IF(campaign_id = "120210040000000000", platform_roas, NULL)) AS meta_winter_platform_roas,
    MAX(IF(campaign_id = "21873002", platform_roas, NULL)) AS shopping_platform_roas,
    MAX(IF(campaign_id = "120210040000000000", value_adjusted_roas, NULL)) AS meta_winter_value_roas,
    MAX(IF(campaign_id = "21873002", value_adjusted_roas, NULL)) AS shopping_value_roas
  FROM story
),

checks AS (
  SELECT "Customer value mart populated" AS check_name,
    CAST(customer_rows AS STRING) AS observed, "> 0" AS expected,
    customer_rows > 0 AS passed
  FROM customer_metrics

  UNION ALL
  SELECT "Customer value matches scored customers",
    CONCAT(CAST(customer_rows AS STRING), "/", CAST((
      SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_gold.ml_customer_pltv`
    ) AS STRING)), "equal",
    customer_rows = (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_gold.ml_customer_pltv`)
  FROM customer_metrics

  UNION ALL
  SELECT "Customer value keys unique",
    CAST(customer_rows - distinct_customers AS STRING), "0",
    customer_rows = distinct_customers
  FROM customer_metrics

  UNION ALL
  SELECT "Customer predictions valid",
    CAST(invalid_predictions AS STRING), "0 invalid",
    invalid_predictions = 0
  FROM customer_metrics

  UNION ALL
  SELECT "Acquisition creative features retained",
    CAST(missing_creative_features AS STRING), "0 missing",
    missing_creative_features = 0
  FROM customer_metrics

  UNION ALL
  SELECT "Campaign value mart populated",
    CAST(campaign_rows AS STRING), "> 0", campaign_rows > 0
  FROM campaign_metrics

  UNION ALL
  SELECT "Campaign value grain unique",
    CAST(campaign_rows - distinct_campaign_grains AS STRING), "0",
    campaign_rows = distinct_campaign_grains
  FROM campaign_metrics

  UNION ALL
  SELECT "Campaign value metrics valid",
    CAST(invalid_campaign_metrics AS STRING), "0 invalid",
    invalid_campaign_metrics = 0
  FROM campaign_metrics

  UNION ALL
  SELECT "Value-adjusted ROAS formula valid",
    CAST(invalid_value_adjusted_roas AS STRING), "0 invalid",
    invalid_value_adjusted_roas = 0
  FROM campaign_metrics

  UNION ALL
  SELECT "Campaign spend reconciles",
    CONCAT(CAST(mart_spend AS STRING), "/", CAST(fact_spend AS STRING)), "equal",
    mart_spend = fact_spend
  FROM reconciliation

  UNION ALL
  SELECT "Campaign claimed revenue reconciles",
    CONCAT(CAST(mart_claimed_revenue AS STRING), "/", CAST(fact_claimed_revenue AS STRING)), "equal",
    mart_claimed_revenue = fact_claimed_revenue
  FROM reconciliation

  UNION ALL
  SELECT "Attributed CRM revenue reconciles",
    CONCAT(CAST(mart_attributed_revenue AS STRING), "/", CAST(fact_attributed_revenue AS STRING)), "equal",
    mart_attributed_revenue = fact_attributed_revenue
  FROM reconciliation

  UNION ALL
  SELECT "Predicted campaign value reconciles",
    CONCAT(CAST(campaign_predicted_value AS STRING), "/", CAST(customer_predicted_value AS STRING)), "equal",
    ABS(campaign_predicted_value - customer_predicted_value) < 0.000001
  FROM reconciliation

  UNION ALL
  SELECT "Campaign drivers populated",
    CAST(driver_rows AS STRING), "> 0", driver_rows > 0
  FROM driver_metrics

  UNION ALL
  SELECT "Campaign driver grain unique",
    CAST(driver_rows - distinct_driver_grains AS STRING), "0",
    driver_rows = distinct_driver_grains
  FROM driver_metrics

  UNION ALL
  SELECT "Campaign driver metrics valid",
    CAST(invalid_driver_metrics AS STRING), "0 invalid",
    invalid_driver_metrics = 0
  FROM driver_metrics

  UNION ALL
  SELECT "Campaign creative drivers retained",
    CAST(missing_creative_features AS STRING), "0 missing",
    missing_creative_features = 0
  FROM driver_metrics

  UNION ALL
  SELECT "Meta Winter wins platform ROAS",
    CONCAT(
      "Meta=", CAST(meta_winter_platform_roas AS STRING),
      ", Shopping=", CAST(shopping_platform_roas AS STRING)
    ), "Meta > Shopping",
    meta_winter_platform_roas > shopping_platform_roas
  FROM story_pivot

  UNION ALL
  SELECT "Shopping wins value-adjusted ROAS",
    CONCAT(
      "Shopping=", CAST(shopping_value_roas AS STRING),
      ", Meta=", CAST(meta_winter_value_roas AS STRING)
    ), "Shopping > Meta",
    shopping_value_roas > meta_winter_value_roas
  FROM story_pivot

  UNION ALL
  SELECT "Mart lineage retained",
    CAST(
      c.missing_lineage + v.missing_lineage + d.missing_lineage
      AS STRING
    ), "0 missing",
    c.missing_lineage + v.missing_lineage + d.missing_lineage = 0
  FROM customer_metrics AS c
  CROSS JOIN campaign_metrics AS v
  CROSS JOIN driver_metrics AS d

  UNION ALL
  SELECT "No raw PII in final marts",
    CAST(COUNT(*) AS STRING), "0", COUNT(*) = 0
  FROM `kloof-marketing-pipeline.kloof_gold.INFORMATION_SCHEMA.COLUMNS`
  WHERE table_name IN (
    "mart_customer_value", "mart_campaign_value", "mart_campaign_drivers"
  )
  AND column_name IN (
    "email", "phone", "first_name", "last_name",
    "normalized_email", "normalized_phone"
  )
)

SELECT
  check_name,
  observed,
  expected,
  IF(passed, "PASS", "FAIL") AS status
FROM checks
ORDER BY check_name;
