-- Kloof Outdoor bronze external tables.
-- Run in US after uploading output/landing unchanged to:
-- gs://kloof-marketing-pipeline-kloof-landing/landing
--
-- Run this file before secure_crm_customers.sql. Replacing crm_customers
-- removes its row access policy, so always reapply the security file.

CREATE OR REPLACE EXTERNAL TABLE
  `kloof-marketing-pipeline.kloof_bronze.google_ads_performance_raw`
(
  raw_line STRING
)
WITH PARTITION COLUMNS (dt DATE)
OPTIONS (
  format = 'CSV',
  uris = [
    'gs://kloof-marketing-pipeline-kloof-landing/landing/google_ads/*ad_performance.csv'
  ],
  hive_partition_uri_prefix =
    'gs://kloof-marketing-pipeline-kloof-landing/landing/google_ads',
  field_delimiter = '\t',
  quote = '',
  skip_leading_rows = 0,
  require_hive_partition_filter = false
);

CREATE OR REPLACE EXTERNAL TABLE
  `kloof-marketing-pipeline.kloof_bronze.google_ads_clicks`
(
  segments_date STRING,
  click_view_gclid STRING,
  campaign_id STRING,
  ad_group_id STRING,
  ad_group_ad_ad_id STRING,
  click_view_area_of_interest_city STRING
)
WITH PARTITION COLUMNS (dt DATE)
OPTIONS (
  format = 'CSV',
  uris = [
    'gs://kloof-marketing-pipeline-kloof-landing/landing/google_ads/*click_view.csv'
  ],
  hive_partition_uri_prefix =
    'gs://kloof-marketing-pipeline-kloof-landing/landing/google_ads',
  field_delimiter = ',',
  skip_leading_rows = 1,
  require_hive_partition_filter = false
);

CREATE OR REPLACE EXTERNAL TABLE
  `kloof-marketing-pipeline.kloof_bronze.meta_ads_insights_raw`
(
  raw_line STRING
)
WITH PARTITION COLUMNS (dt DATE)
OPTIONS (
  format = 'CSV',
  uris = [
    'gs://kloof-marketing-pipeline-kloof-landing/landing/meta_ads/*.jsonl'
  ],
  hive_partition_uri_prefix =
    'gs://kloof-marketing-pipeline-kloof-landing/landing/meta_ads',
  field_delimiter = '\t',
  quote = '',
  skip_leading_rows = 0,
  require_hive_partition_filter = false
);

CREATE OR REPLACE EXTERNAL TABLE
  `kloof-marketing-pipeline.kloof_bronze.ga4_events`
(
  event_date STRING,
  event_timestamp INT64,
  event_name STRING,
  event_params ARRAY<
    STRUCT<
      key STRING,
      value STRUCT<
        string_value STRING,
        int_value INT64,
        float_value FLOAT64,
        double_value FLOAT64
      >
    >
  >,
  user_pseudo_id STRING,
  device STRUCT<
    category STRING,
    operating_system STRING
  >,
  geo STRUCT<
    country STRING,
    city STRING
  >,
  collected_traffic_source STRUCT<
    manual_campaign_id STRING,
    manual_campaign_name STRING,
    manual_source STRING,
    manual_medium STRING,
    manual_term STRING,
    manual_content STRING,
    gclid STRING,
    dclid STRING,
    srsltid STRING
  >,
  ecommerce STRUCT<
    transaction_id STRING,
    purchase_revenue FLOAT64,
    total_item_quantity INT64
  >,
  items ARRAY<
    STRUCT<
      item_id STRING,
      item_name STRING,
      price FLOAT64,
      quantity INT64
    >
  >
)
WITH PARTITION COLUMNS (dt DATE)
OPTIONS (
  format = 'NEWLINE_DELIMITED_JSON',
  uris = [
    'gs://kloof-marketing-pipeline-kloof-landing/landing/ga4/*.ndjson.gz'
  ],
  hive_partition_uri_prefix =
    'gs://kloof-marketing-pipeline-kloof-landing/landing/ga4',
  compression = 'GZIP',
  require_hive_partition_filter = false
);

-- BigLake is used for crm_customers so row-level PII security is supported.
CREATE OR REPLACE EXTERNAL TABLE
  `kloof-marketing-pipeline.kloof_bronze.crm_customers`
(
  customer_id STRING,
  email STRING,
  first_name STRING,
  last_name STRING,
  phone STRING,
  city STRING,
  created_at STRING,
  is_guest STRING,
  marketing_opt_in STRING
)
WITH PARTITION COLUMNS (dt DATE)
WITH CONNECTION `kloof-marketing-pipeline.us.kloof_vertex_ai`
OPTIONS (
  format = 'CSV',
  uris = [
    'gs://kloof-marketing-pipeline-kloof-landing/landing/crm/*customers.csv'
  ],
  hive_partition_uri_prefix =
    'gs://kloof-marketing-pipeline-kloof-landing/landing/crm',
  field_delimiter = ',',
  skip_leading_rows = 1,
  require_hive_partition_filter = false
);

CREATE OR REPLACE EXTERNAL TABLE
  `kloof-marketing-pipeline.kloof_bronze.crm_orders`
(
  order_id STRING,
  customer_id STRING,
  order_ts STRING,
  currency STRING,
  subtotal STRING,
  discount STRING,
  revenue STRING,
  status STRING,
  item_count STRING,
  updated_at STRING
)
WITH PARTITION COLUMNS (dt DATE)
OPTIONS (
  format = 'CSV',
  uris = [
    'gs://kloof-marketing-pipeline-kloof-landing/landing/crm/*orders.csv'
  ],
  hive_partition_uri_prefix =
    'gs://kloof-marketing-pipeline-kloof-landing/landing/crm',
  field_delimiter = ',',
  skip_leading_rows = 1,
  require_hive_partition_filter = false
);

CREATE OR REPLACE EXTERNAL TABLE
  `kloof-marketing-pipeline.kloof_bronze.crm_order_items`
(
  order_id STRING,
  sku STRING,
  product_name STRING,
  unit_price STRING,
  quantity STRING
)
WITH PARTITION COLUMNS (dt DATE)
OPTIONS (
  format = 'CSV',
  uris = [
    'gs://kloof-marketing-pipeline-kloof-landing/landing/crm/*order_items.csv'
  ],
  hive_partition_uri_prefix =
    'gs://kloof-marketing-pipeline-kloof-landing/landing/crm',
  field_delimiter = ',',
  skip_leading_rows = 1,
  require_hive_partition_filter = false
);

CREATE OR REPLACE EXTERNAL TABLE
  `kloof-marketing-pipeline.kloof_bronze.creative_copy_raw`
(
  raw_line STRING
)
WITH PARTITION COLUMNS (dt DATE)
OPTIONS (
  format = 'CSV',
  uris = [
    'gs://kloof-marketing-pipeline-kloof-landing/landing/creatives/*.txt'
  ],
  hive_partition_uri_prefix =
    'gs://kloof-marketing-pipeline-kloof-landing/landing/creatives',
  field_delimiter = '\t',
  quote = '',
  skip_leading_rows = 0,
  require_hive_partition_filter = false
);

CREATE OR REPLACE EXTERNAL TABLE
  `kloof-marketing-pipeline.kloof_bronze.weather_daily`
(
  latitude FLOAT64,
  longitude FLOAT64,
  generationtime_ms FLOAT64,
  utc_offset_seconds INT64,
  timezone STRING,
  timezone_abbreviation STRING,
  elevation FLOAT64,
  daily_units STRUCT<
    time STRING,
    temperature_2m_max STRING,
    temperature_2m_min STRING,
    precipitation_sum STRING
  >,
  daily STRUCT<
    time ARRAY<STRING>,
    temperature_2m_max ARRAY<FLOAT64>,
    temperature_2m_min ARRAY<FLOAT64>,
    precipitation_sum ARRAY<FLOAT64>
  >
)
WITH PARTITION COLUMNS (dt DATE)
OPTIONS (
  format = 'NEWLINE_DELIMITED_JSON',
  uris = [
    'gs://kloof-marketing-pipeline-kloof-landing/landing/weather/*.json'
  ],
  hive_partition_uri_prefix =
    'gs://kloof-marketing-pipeline-kloof-landing/landing/weather',
  require_hive_partition_filter = false
);

CREATE OR REPLACE EXTERNAL TABLE
  `kloof-marketing-pipeline.kloof_bronze.fx_rates`
(
  rate_date STRING,
  base_currency STRING,
  quote_currency STRING,
  rate STRING
)
WITH PARTITION COLUMNS (dt DATE)
OPTIONS (
  format = 'CSV',
  uris = [
    'gs://kloof-marketing-pipeline-kloof-landing/landing/fx_rates/*usd_zar.csv'
  ],
  hive_partition_uri_prefix =
    'gs://kloof-marketing-pipeline-kloof-landing/landing/fx_rates',
  field_delimiter = ',',
  skip_leading_rows = 1,
  require_hive_partition_filter = false
);
