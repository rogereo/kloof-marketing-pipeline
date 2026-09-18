# Step 5 Batch 1

This batch adds:

- one blocking manual assertion for each DQ01-DQ12 fix;
- strict yesterday-partition freshness for daily feeds, secured staging freshness for CRM customers, and availability for the event-driven creative feed;
- silver-to-gold reconciliation for order count, CRM revenue and ad spend;
- validation queries for the batch.

Execution tags:

- `quality_batch1`: DQ01-DQ12 and reconciliation assertions;
- `quality_freshness`: yesterday-source freshness only;
- `quality`: every quality assertion, for the production workflow.

Run `sql/quality/check_source_freshness.sql` before the freshness tag. If a daily source is stale,
deliver yesterday's simulator partition before running `quality_freshness`. Refresh
`stg_crm_customers` after delivery because raw CRM PII is hidden by a row-access policy.
