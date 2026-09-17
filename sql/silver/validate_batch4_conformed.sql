WITH metrics AS (
  SELECT
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.int_customer_identity`) AS identity_rows,
    (SELECT COUNT(DISTINCT IF(NOT is_internal_customer, customer_key, NULL)) FROM `kloof-marketing-pipeline.kloof_silver.int_customer_identity`) AS distinct_people,
    (SELECT COUNTIF(is_placeholder) FROM `kloof-marketing-pipeline.kloof_silver.int_customer_identity`) AS late_customer_placeholders,
    (SELECT COUNT(*) - COUNT(DISTINCT customer_id) FROM `kloof-marketing-pipeline.kloof_silver.int_customer_identity`) AS duplicate_customer_ids,
    (SELECT COUNTIF(customer_key IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.int_customer_identity`) AS missing_customer_keys,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.int_sessions`) AS session_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT session_key) FROM `kloof-marketing-pipeline.kloof_silver.int_sessions`) AS duplicate_sessions,
    (SELECT COUNTIF(is_internal_session) FROM `kloof-marketing-pipeline.kloof_silver.int_sessions`) AS internal_sessions,
    (SELECT COUNTIF(customer_key IS NOT NULL) FROM `kloof-marketing-pipeline.kloof_silver.int_sessions`) AS identified_sessions,
    (SELECT COUNTIF(attribution_method = "click_id") FROM `kloof-marketing-pipeline.kloof_silver.int_sessions`) AS click_attributed_sessions,
    (SELECT COUNTIF(attribution_method NOT IN ("click_id", "utm", "unattributed")) FROM `kloof-marketing-pipeline.kloof_silver.int_sessions`) AS invalid_session_attribution,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) AS order_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) AS duplicate_orders,
    (SELECT COUNTIF(is_test_order) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) AS test_orders,
    (SELECT COUNTIF(customer_key IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) AS orders_without_identity,
    (SELECT COUNTIF(attribution_method = "click_id") FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) AS click_attributed_orders,
    (SELECT COUNTIF(attribution_method NOT IN ("click_id", "utm", "unattributed")) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`) AS invalid_order_attribution,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.int_creative_features`) AS creative_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT ad_id) FROM `kloof-marketing-pipeline.kloof_silver.int_creative_features`) AS duplicate_creatives,
    (SELECT COUNTIF(gemini_status != "") FROM `kloof-marketing-pipeline.kloof_silver.int_creative_features`) AS gemini_errors,
    (SELECT COUNTIF(extraction_method != "gemini") FROM `kloof-marketing-pipeline.kloof_silver.int_creative_features`) AS creative_fallbacks,
    (SELECT COUNTIF(tone NOT IN ("urgent", "informative", "aspirational", "playful") OR cta NOT IN ("shop_now", "learn_more", "get_offer", "sign_up") OR discount_pct NOT BETWEEN 0 AND 100 OR product IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.int_creative_features`) AS invalid_creative_features,
    (SELECT COUNT(*)
     FROM `kloof-marketing-pipeline.kloof_silver.INFORMATION_SCHEMA.COLUMNS`
     WHERE table_name IN ("int_customer_identity", "int_sessions", "int_orders_attributed")
       AND column_name IN ("email", "phone", "first_name", "last_name", "normalized_email", "normalized_phone")) AS raw_pii_columns,
    ((SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.int_customer_identity`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.int_sessions`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.int_orders_attributed`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.int_creative_features`)) AS missing_lineage
)

SELECT check_name, observed, expected, IF(passed, "PASS", "FAIL") AS status
FROM metrics,
UNNEST([
  STRUCT("All customer IDs mapped" AS check_name, CAST(identity_rows AS STRING) AS observed, "5,173" AS expected, identity_rows = 5173 AS passed),
  STRUCT("Distinct people conformed", CAST(distinct_people AS STRING), "4,841", distinct_people = 4841),
  STRUCT("Late customer placeholders created", CAST(late_customer_placeholders AS STRING), "3", late_customer_placeholders = 3),
  STRUCT("Customer IDs unique", CAST(duplicate_customer_ids AS STRING), "0", duplicate_customer_ids = 0),
  STRUCT("Every customer has customer_key", CAST(missing_customer_keys AS STRING), "0", missing_customer_keys = 0),
  STRUCT("Sessions loaded", CAST(session_rows AS STRING), "> 0", session_rows > 0),
  STRUCT("Sessions unique", CAST(duplicate_sessions AS STRING), "0", duplicate_sessions = 0),
  STRUCT("Internal sessions excluded", CAST(internal_sessions AS STRING), "0", internal_sessions = 0),
  STRUCT("Sessions linked to identities", CAST(identified_sessions AS STRING), "> 0", identified_sessions > 0),
  STRUCT("Click-attributed sessions present", CAST(click_attributed_sessions AS STRING), "> 0", click_attributed_sessions > 0),
  STRUCT("Session attribution valid", CAST(invalid_session_attribution AS STRING), "0", invalid_session_attribution = 0),
  STRUCT("Genuine orders loaded", CAST(order_rows AS STRING), "10,033", order_rows = 10033),
  STRUCT("Attributed orders unique", CAST(duplicate_orders AS STRING), "0", duplicate_orders = 0),
  STRUCT("QA orders excluded", CAST(test_orders AS STRING), "0", test_orders = 0),
  STRUCT("Orders linked to customer keys", CAST(orders_without_identity AS STRING), "0 missing", orders_without_identity = 0),
  STRUCT("Click-attributed orders present", CAST(click_attributed_orders AS STRING), "> 0", click_attributed_orders > 0),
  STRUCT("Order attribution valid", CAST(invalid_order_attribution AS STRING), "0", invalid_order_attribution = 0),
  STRUCT("Creative features loaded", CAST(creative_rows AS STRING), "17", creative_rows = 17),
  STRUCT("Creative ad IDs unique", CAST(duplicate_creatives AS STRING), "0", duplicate_creatives = 0),
  STRUCT("Gemini calls successful", CAST(gemini_errors AS STRING), "0 errors", gemini_errors = 0),
  STRUCT("Gemini JSON parsed", CAST(creative_fallbacks AS STRING), "0 fallbacks", creative_fallbacks = 0),
  STRUCT("Creative features valid", CAST(invalid_creative_features AS STRING), "0 invalid", invalid_creative_features = 0),
  STRUCT("No raw PII in conformed models", CAST(raw_pii_columns AS STRING), "0", raw_pii_columns = 0),
  STRUCT("Source lineage retained", CAST(missing_lineage AS STRING), "0 missing", missing_lineage = 0)
])
ORDER BY check_name;
