# Step 5 Batch 2

This batch completes Data Quality & Monitoring with:

- `ops_dq_results`: an incremental, append-only snapshot of all DQ01-DQ12 detectors;
- `affected_rows_this_run`: the increase since the previous detector snapshot;
- `ops_dq_scorecard`: detected-versus-planted counts using the official simulator counting rules;
- `assert_dq_scorecard_matched`: a blocking assertion requiring all twelve counts to match;
- `sql/quality/validate_quality_batch2.sql`: final validation evidence.

Only `ops_dq_scorecard` reads `kloof_truth.dq_manifest`. Bronze, silver, gold and the detector
model remain independent of planted truth.

Execution order:

1. Load the complete current manifest into `kloof_truth.dq_manifest`.
2. Run the `quality_monitoring` tag to append a detector snapshot.
3. Run the `quality_scorecard` tag to build and assert the scorecard.
4. Run `sql/quality/validate_quality_batch2.sql` in BigQuery.

