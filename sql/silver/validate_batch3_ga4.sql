WITH session_metrics AS (
  SELECT
    user_pseudo_id,
    ga_session_id,
    LOGICAL_OR(is_internal_traffic) AS is_internal_session,
    MAX(session_gclid) AS gclid,
    MAX(session_fbclid) AS fbclid,
    MAX(session_campaign_name) AS campaign_name,
    COUNT(DISTINCT session_gclid) AS gclid_values,
    COUNT(DISTINCT session_fbclid) AS fbclid_values
  FROM `kloof-marketing-pipeline.kloof_silver.stg_ga4_events`
  GROUP BY user_pseudo_id, ga_session_id
),

value_anomalies AS (
  SELECT COUNT(*) AS anomaly_count
  FROM `kloof-marketing-pipeline.kloof_silver.stg_ga4_events` AS g
  JOIN `kloof-marketing-pipeline.kloof_silver.stg_crm_orders` AS o
    ON g.transaction_id = o.order_id
  WHERE g.event_name = "purchase"
    AND g.ga4_reported_value IS NOT NULL
    AND o.revenue > 0
    AND SAFE_DIVIDE(g.ga4_reported_value, o.revenue) NOT BETWEEN 0.5 AND 2
),

metrics AS (
  SELECT
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.stg_ga4_events`) AS event_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT event_fingerprint) FROM `kloof-marketing-pipeline.kloof_silver.stg_ga4_events`) AS duplicate_fingerprints,
    (SELECT COUNT(*) - COUNT(DISTINCT transaction_id) FROM `kloof-marketing-pipeline.kloof_silver.stg_ga4_events` WHERE event_name = "purchase") AS duplicate_purchase_transactions,
    (SELECT COUNTIF(report_date_sast != event_date) FROM `kloof-marketing-pipeline.kloof_silver.stg_ga4_events`) AS mismatched_report_dates,
    (SELECT COUNTIF(ga_session_id IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_ga4_events`) AS missing_session_ids,
    (SELECT COUNTIF(arrived_late) FROM `kloof-marketing-pipeline.kloof_silver.stg_ga4_events`) AS late_events,
    (SELECT COUNTIF(is_internal_session) FROM session_metrics) AS internal_sessions,
    (SELECT COUNTIF(gclid IS NOT NULL OR fbclid IS NOT NULL) FROM session_metrics) AS paid_click_sessions,
    (SELECT COUNTIF(gclid_values > 1 OR fbclid_values > 1) FROM session_metrics) AS inconsistent_session_click_ids,
    (SELECT COUNTIF(is_provisional != (event_date >= DATE_SUB(max_event_date, INTERVAL 1 DAY)))
     FROM `kloof-marketing-pipeline.kloof_silver.stg_ga4_events`
     CROSS JOIN (SELECT MAX(event_date) AS max_event_date FROM `kloof-marketing-pipeline.kloof_silver.stg_ga4_events`)) AS invalid_provisional_flags,
    (SELECT anomaly_count FROM value_anomalies) AS ga4_value_anomalies,
    (SELECT COUNT(*)
     FROM `kloof-marketing-pipeline.kloof_silver.INFORMATION_SCHEMA.COLUMNS`
     WHERE table_name = "stg_ga4_events"
       AND column_name IN ("revenue", "purchase_revenue")) AS authoritative_revenue_columns,
    (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_ga4_events`) AS missing_lineage
)

SELECT check_name, observed, expected, IF(passed, "PASS", "FAIL") AS status
FROM metrics,
UNNEST([
  STRUCT("GA4 events loaded" AS check_name, CAST(event_rows AS STRING) AS observed, "> 0" AS expected, event_rows > 0 AS passed),
  STRUCT("Event fingerprints unique", CAST(duplicate_fingerprints AS STRING), "0", duplicate_fingerprints = 0),
  STRUCT("Purchase transaction IDs unique", CAST(duplicate_purchase_transactions AS STRING), "0", duplicate_purchase_transactions = 0),
  STRUCT("UTC to SAST report dates agree", CAST(mismatched_report_dates AS STRING), "0", mismatched_report_dates = 0),
  STRUCT("GA4 session IDs extracted", CAST(missing_session_ids AS STRING), "0 missing", missing_session_ids = 0),
  STRUCT("Late GA4 events detected", CAST(late_events AS STRING), "> 0", late_events > 0),
  STRUCT("Internal sessions detected", CAST(internal_sessions AS STRING), "> 0", internal_sessions > 0),
  STRUCT("Paid click IDs extracted", CAST(paid_click_sessions AS STRING), "> 0", paid_click_sessions > 0),
  STRUCT("Click IDs carried consistently", CAST(inconsistent_session_click_ids AS STRING), "0 inconsistent", inconsistent_session_click_ids = 0),
  STRUCT("Latest two days provisional", CAST(invalid_provisional_flags AS STRING), "0 invalid", invalid_provisional_flags = 0),
  STRUCT("GA4 value anomalies detected", CAST(ga4_value_anomalies AS STRING), "> 0", ga4_value_anomalies > 0),
  STRUCT("No authoritative GA4 revenue column", CAST(authoritative_revenue_columns AS STRING), "0", authoritative_revenue_columns = 0),
  STRUCT("Source lineage retained", CAST(missing_lineage AS STRING), "0 missing", missing_lineage = 0)
])
ORDER BY check_name;
