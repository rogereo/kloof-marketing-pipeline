# Step 5 Batch 1

This batch adds:

- one blocking manual assertion for each DQ01-DQ12 fix;
- a strict yesterday-partition freshness assertion for all ten bronze sources;
- silver-to-gold reconciliation for order count, CRM revenue and ad spend;
- validation queries for the batch.

Execution tags:

- `quality_batch1`: DQ01-DQ12 and reconciliation assertions;
- `quality_freshness`: yesterday-source freshness only;
- `quality`: every quality assertion, for the production workflow.

Run `sql/quality/check_source_freshness.sql` before the freshness tag. If a source is stale,
deliver yesterday's simulator partition before running `quality_freshness`.
