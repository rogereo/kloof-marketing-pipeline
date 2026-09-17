WITH expected AS (
  SELECT
    COUNTIF(first_order_date IS NOT NULL) AS expected_customers
  FROM `kloof-marketing-pipeline.kloof_gold.dim_customer`
),

actual AS (
  SELECT
    COUNT(*) AS feature_rows,
    COUNT(DISTINCT customer_key) AS distinct_customers,
    COUNTIF(is_training_eligible) AS training_rows,
    COUNTIF(NOT is_training_eligible) AS scoring_only_rows,
    COUNTIF(
      orders_7d < 1
      OR completed_orders_7d < 0
      OR completed_revenue_7d < 0
      OR sessions_7d < 0
      OR future_value_90d < 0
    ) AS invalid_metrics,
    COUNTIF(dt IS NULL OR source_file_name IS NULL) AS missing_lineage
  FROM `kloof-marketing-pipeline.kloof_gold.mart_customer_features`
),

expected_windows AS (
  SELECT
    SUM(IF(
      o.status = "completed"
      AND o.order_date BETWEEN c.first_order_date
        AND DATE_ADD(c.first_order_date, INTERVAL 7 DAY),
      o.completed_revenue,
      0
    )) AS expected_feature_revenue,
    SUM(IF(
      o.status = "completed"
      AND o.order_date BETWEEN DATE_ADD(c.first_order_date, INTERVAL 8 DAY)
        AND DATE_ADD(c.first_order_date, INTERVAL 97 DAY),
      o.completed_revenue,
      0
    )) AS expected_label_revenue
  FROM `kloof-marketing-pipeline.kloof_gold.dim_customer` AS c
  JOIN `kloof-marketing-pipeline.kloof_gold.fct_orders` AS o
    USING (customer_key)
  WHERE c.first_order_date IS NOT NULL
),

actual_windows AS (
  SELECT
    SUM(completed_revenue_7d) AS actual_feature_revenue,
    SUM(future_value_90d) AS actual_label_revenue
  FROM `kloof-marketing-pipeline.kloof_gold.mart_customer_features`
),

checks AS (
  SELECT
    "Feature rows match acquired customers" AS check_name,
    CAST(a.feature_rows AS STRING) AS observed,
    CAST(e.expected_customers AS STRING) AS expected,
    a.feature_rows = e.expected_customers AS passed
  FROM actual AS a CROSS JOIN expected AS e

  UNION ALL
  SELECT
    "Customer feature keys unique",
    CAST(feature_rows - distinct_customers AS STRING),
    "0",
    feature_rows = distinct_customers
  FROM actual

  UNION ALL
  SELECT
    "Feature metrics valid",
    CAST(invalid_metrics AS STRING),
    "0 invalid",
    invalid_metrics = 0
  FROM actual

  UNION ALL
  SELECT
    "Feature revenue window reconciles",
    CONCAT(CAST(aw.actual_feature_revenue AS STRING), "/", CAST(ew.expected_feature_revenue AS STRING)),
    "equal",
    aw.actual_feature_revenue = ew.expected_feature_revenue
  FROM actual_windows AS aw CROSS JOIN expected_windows AS ew

  UNION ALL
  SELECT
    "90-day label window reconciles",
    CONCAT(CAST(aw.actual_label_revenue AS STRING), "/", CAST(ew.expected_label_revenue AS STRING)),
    "equal",
    aw.actual_label_revenue = ew.expected_label_revenue
  FROM actual_windows AS aw CROSS JOIN expected_windows AS ew

  UNION ALL
  SELECT
    "Training cohort present",
    CAST(training_rows AS STRING),
    "> 0",
    training_rows > 0
  FROM actual

  UNION ALL
  SELECT
    "Scoring-only cohort present",
    CAST(scoring_only_rows AS STRING),
    "> 0",
    scoring_only_rows > 0
  FROM actual

  UNION ALL
  SELECT
    "Training cutoff enforced",
    CAST(COUNTIF(
      is_training_eligible != (acquisition_date <= DATE "2026-06-10")
    ) AS STRING),
    "0 invalid",
    COUNTIF(
      is_training_eligible != (acquisition_date <= DATE "2026-06-10")
    ) = 0
  FROM `kloof-marketing-pipeline.kloof_gold.mart_customer_features`

  UNION ALL
  SELECT
    "No raw PII columns",
    CAST(COUNT(*) AS STRING),
    "0",
    COUNT(*) = 0
  FROM `kloof-marketing-pipeline.kloof_gold.INFORMATION_SCHEMA.COLUMNS`
  WHERE table_name = "mart_customer_features"
    AND column_name IN (
      "email", "phone", "first_name", "last_name",
      "normalized_email", "normalized_phone"
    )

  UNION ALL
  SELECT
    "Source lineage retained",
    CAST(missing_lineage AS STRING),
    "0 missing",
    missing_lineage = 0
  FROM actual
)

SELECT
  check_name,
  observed,
  expected,
  IF(passed, "PASS", "FAIL") AS status
FROM checks
ORDER BY check_name;
