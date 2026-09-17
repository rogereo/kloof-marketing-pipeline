-- Run after create_external_tables.sql.
-- A TRUE filter grants the pipeline service account every customer row;
-- principals not listed in a row policy see no rows.

CREATE OR REPLACE ROW ACCESS POLICY pipeline_service_account_only
ON `kloof-marketing-pipeline.kloof_bronze.crm_customers`
GRANT TO (
  "serviceAccount:dataform-runner@kloof-marketing-pipeline.iam.gserviceaccount.com"
)
FILTER USING (TRUE);
