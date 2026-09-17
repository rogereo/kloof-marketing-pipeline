WITH checks AS (
  SELECT
    "All 12 DQ codes monitored" AS check_name,
    CAST(COUNT(*) AS STRING) AS observed,
    "12" AS expected,
    IF(COUNT(*) = 12, "PASS", "FAIL") AS status
  FROM `kloof-marketing-pipeline.kloof_ops.ops_dq_results`
  WHERE recorded_at = (
    SELECT MAX(recorded_at)
    FROM `kloof-marketing-pipeline.kloof_ops.ops_dq_results`
  )

  UNION ALL
  SELECT
    "All detected counts non-negative",
    CAST(COUNTIF(detected_count < 0 OR affected_rows_this_run < 0) AS STRING),
    "0 invalid",
    IF(COUNTIF(detected_count < 0 OR affected_rows_this_run < 0) = 0, "PASS", "FAIL")
  FROM `kloof-marketing-pipeline.kloof_ops.ops_dq_results`

  UNION ALL
  SELECT
    "All planted DQ codes matched",
    CAST(COUNTIF(status != "MATCHED") AS STRING),
    "0 mismatches",
    IF(COUNT(*) = 12 AND COUNTIF(status != "MATCHED") = 0, "PASS", "FAIL")
  FROM `kloof-marketing-pipeline.kloof_ops.ops_dq_scorecard`

  UNION ALL
  SELECT
    "Truth isolated to scorecard",
    CAST(COUNTIF(table_name = "ops_dq_scorecard") AS STRING),
    "1 truth-reading model",
    IF(COUNTIF(table_name = "ops_dq_scorecard") = 1, "PASS", "FAIL")
  FROM `kloof-marketing-pipeline.kloof_ops.INFORMATION_SCHEMA.TABLES`
  WHERE table_name = "ops_dq_scorecard"
)

SELECT *
FROM checks
ORDER BY check_name;

