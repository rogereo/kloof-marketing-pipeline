const bronzeTables = [
  "google_ads_performance_raw",
  "google_ads_clicks",
  "meta_ads_insights_raw",
  "ga4_events",
  "crm_customers",
  "crm_orders",
  "crm_order_items",
  "creative_copy_raw",
  "weather_daily",
  "fx_rates"
];

bronzeTables.forEach((tableName) => {
  declare({
    database: "kloof-marketing-pipeline",
    schema: "kloof_bronze",
    name: tableName
  });
});
