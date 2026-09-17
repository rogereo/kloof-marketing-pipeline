WITH metrics AS (
  SELECT
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_customers`) AS customer_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT customer_id) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_customers`) AS duplicate_customers,
    (SELECT COUNTIF(email_hash IS NULL AND phone_hash IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_customers`) AS customers_without_identity,
    (SELECT COUNTIF(city_standard NOT IN ('Cape Town', 'Johannesburg', 'Durban') OR city_standard IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_customers`) AS invalid_cities,
    (SELECT COUNTIF(is_internal_customer) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_customers`) AS internal_customers,
    (SELECT COUNT(*)
     FROM `kloof-marketing-pipeline.kloof_silver.INFORMATION_SCHEMA.COLUMNS`
     WHERE table_name = 'stg_crm_customers'
       AND column_name IN ('email', 'phone', 'first_name', 'last_name', 'normalized_email', 'normalized_phone')) AS raw_pii_columns,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_orders`) AS order_rows,
    (SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_orders`) AS duplicate_orders,
    (SELECT COUNTIF(is_test_order) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_orders`) AS flagged_test_orders,
    (SELECT COUNT(*) - COUNT(DISTINCT CONCAT(order_id, '|', sku)) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_order_items`) AS duplicate_order_items,
    (SELECT COUNT(*) - COUNT(DISTINCT gclid) FROM `kloof-marketing-pipeline.kloof_silver.stg_google_clicks`) AS duplicate_gclids,
    (SELECT COUNT(*) FROM `kloof-marketing-pipeline.kloof_silver.stg_fx_rates`) AS fx_rows,
    (SELECT DATE_DIFF(MAX(rate_date), MIN(rate_date), DAY) + 1 FROM `kloof-marketing-pipeline.kloof_silver.stg_fx_rates`) AS fx_expected_days,
    (SELECT COUNTIF(rate IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_fx_rates`) AS missing_fx_rates,
    ((SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_customers`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_orders`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_crm_order_items`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_google_clicks`)
      + (SELECT COUNTIF(dt IS NULL OR source_file_name IS NULL) FROM `kloof-marketing-pipeline.kloof_silver.stg_fx_rates`)) AS missing_lineage
)

SELECT check_name, observed, expected, IF(passed, 'PASS', 'FAIL') AS status
FROM metrics,
UNNEST([
  STRUCT('Customers loaded' AS check_name, CAST(customer_rows AS STRING) AS observed, '> 0' AS expected, customer_rows > 0 AS passed),
  STRUCT('Customer IDs unique', CAST(duplicate_customers AS STRING), '0', duplicate_customers = 0),
  STRUCT('Every customer has an identity hash', CAST(customers_without_identity AS STRING), '0', customers_without_identity = 0),
  STRUCT('Cities standardised', CAST(invalid_cities AS STRING), '0 invalid', invalid_cities = 0),
  STRUCT('Internal customer detected', CAST(internal_customers AS STRING), '> 0', internal_customers > 0),
  STRUCT('No raw PII columns in silver', CAST(raw_pii_columns AS STRING), '0', raw_pii_columns = 0),
  STRUCT('Orders loaded', CAST(order_rows AS STRING), '> 0', order_rows > 0),
  STRUCT('Latest order version unique', CAST(duplicate_orders AS STRING), '0', duplicate_orders = 0),
  STRUCT('QA orders detected', CAST(flagged_test_orders AS STRING), '> 0', flagged_test_orders > 0),
  STRUCT('Order item keys unique', CAST(duplicate_order_items AS STRING), '0', duplicate_order_items = 0),
  STRUCT('Google click IDs unique', CAST(duplicate_gclids AS STRING), '0', duplicate_gclids = 0),
  STRUCT('FX date spine complete', CONCAT(CAST(fx_rows AS STRING), '/', CAST(fx_expected_days AS STRING)), 'rows = calendar days', fx_rows = fx_expected_days),
  STRUCT('No missing FX rates', CAST(missing_fx_rates AS STRING), '0', missing_fx_rates = 0),
  STRUCT('Source lineage retained', CAST(missing_lineage AS STRING), '0 missing', missing_lineage = 0)
])
ORDER BY check_name;
