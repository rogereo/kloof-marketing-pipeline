WITH model_training AS (
  SELECT
    COUNT(*) AS training_info_rows,
    COUNTIF(eval_loss IS NOT NULL) AS evaluated_iterations
  FROM ML.TRAINING_INFO(
    MODEL `kloof-marketing-pipeline.kloof_gold.customer_pltv_model`
  )
),

evaluation AS (
  SELECT
    COUNT(*) AS evaluation_rows,
    COUNTIF(
      mean_absolute_error IS NULL
      OR mean_absolute_error < 0
      OR mean_squared_error IS NULL
      OR mean_squared_error < 0
      OR r2_score IS NULL
    ) AS invalid_evaluation_rows
  FROM `kloof-marketing-pipeline.kloof_gold.ml_customer_pltv_evaluation`
),

data_end AS (
  SELECT MAX(calendar_date) AS max_observed_date
  FROM `kloof-marketing-pipeline.kloof_gold.dim_date`
),

expected AS (
  SELECT COUNT(*) AS expected_prediction_rows
  FROM `kloof-marketing-pipeline.kloof_gold.mart_customer_features` AS f
  CROSS JOIN data_end AS d
  WHERE f.acquisition_date <= DATE_SUB(d.max_observed_date, INTERVAL 7 DAY)
),

predictions AS (
  SELECT
    COUNT(*) AS prediction_rows,
    COUNT(DISTINCT customer_key) AS distinct_customers,
    COUNTIF(predicted_future_value_90d < 0) AS negative_predictions,
    COUNT(DISTINCT value_segment) AS segment_count,
    COUNTIF(dt IS NULL OR source_file_name IS NULL) AS missing_lineage,
    MIN(IF(value_segment = "high", predicted_future_value_90d, NULL)) AS min_high,
    MAX(IF(value_segment = "steady", predicted_future_value_90d, NULL)) AS max_steady,
    MIN(IF(value_segment = "steady", predicted_future_value_90d, NULL)) AS min_steady,
    MAX(IF(value_segment = "low", predicted_future_value_90d, NULL)) AS max_low
  FROM `kloof-marketing-pipeline.kloof_gold.ml_customer_pltv`
),

checks AS (
  SELECT
    "PLTV model training info available" AS check_name,
    CAST(training_info_rows AS STRING) AS observed,
    "> 0" AS expected,
    training_info_rows > 0 AS passed
  FROM model_training

  UNION ALL
  SELECT
    "Model training evaluated holdout loss",
    CAST(evaluated_iterations AS STRING),
    "> 0",
    evaluated_iterations > 0
  FROM model_training

  UNION ALL
  SELECT
    "Evaluation metrics persisted",
    CAST(evaluation_rows AS STRING),
    "1",
    evaluation_rows = 1
  FROM evaluation

  UNION ALL
  SELECT
    "Evaluation metrics valid",
    CAST(invalid_evaluation_rows AS STRING),
    "0 invalid",
    invalid_evaluation_rows = 0
  FROM evaluation

  UNION ALL
  SELECT
    "Eligible customers scored",
    CONCAT(CAST(p.prediction_rows AS STRING), "/", CAST(e.expected_prediction_rows AS STRING)),
    "equal",
    p.prediction_rows = e.expected_prediction_rows
  FROM predictions AS p CROSS JOIN expected AS e

  UNION ALL
  SELECT
    "Prediction keys unique",
    CAST(prediction_rows - distinct_customers AS STRING),
    "0",
    prediction_rows = distinct_customers
  FROM predictions

  UNION ALL
  SELECT
    "Predicted values non-negative",
    CAST(negative_predictions AS STRING),
    "0",
    negative_predictions = 0
  FROM predictions

  UNION ALL
  SELECT
    "All value segments populated",
    CAST(segment_count AS STRING),
    "3",
    segment_count = 3
  FROM predictions

  UNION ALL
  SELECT
    "Value segment ordering valid",
    CONCAT(
      "high_min=", CAST(min_high AS STRING),
      ", steady_max=", CAST(max_steady AS STRING),
      ", steady_min=", CAST(min_steady AS STRING),
      ", low_max=", CAST(max_low AS STRING)
    ),
    "high >= steady >= low",
    min_high >= max_steady AND min_steady >= max_low
  FROM predictions

  UNION ALL
  SELECT
    "Target excluded from model features",
    CAST(COUNTIF(input = "future_value_90d") AS STRING),
    "0",
    COUNTIF(input = "future_value_90d") = 0
  FROM ML.FEATURE_INFO(
    MODEL `kloof-marketing-pipeline.kloof_gold.customer_pltv_model`
  )

  UNION ALL
  SELECT
    "No raw PII in predictions",
    CAST(COUNT(*) AS STRING),
    "0",
    COUNT(*) = 0
  FROM `kloof-marketing-pipeline.kloof_gold.INFORMATION_SCHEMA.COLUMNS`
  WHERE table_name = "ml_customer_pltv"
    AND column_name IN (
      "email", "phone", "first_name", "last_name",
      "normalized_email", "normalized_phone"
    )

  UNION ALL
  SELECT
    "Prediction lineage retained",
    CAST(missing_lineage AS STRING),
    "0 missing",
    missing_lineage = 0
  FROM predictions
)

SELECT
  check_name,
  observed,
  expected,
  IF(passed, "PASS", "FAIL") AS status
FROM checks
ORDER BY check_name;