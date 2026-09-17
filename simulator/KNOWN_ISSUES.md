# Known data issues

Every problem planted in the landing data, with the code that identifies it everywhere:
in `config.yaml`, in `output/truth/dq_manifest/`, in this file, and later in the Dataform tags.

There are two kinds:

- **SH (shape):** the data is correct but awkward. Silver reshapes it.
- **DQ (quality):** the data is wrong, incomplete, duplicated or late. Silver detects it, fixes it
  or quarantines it, and logs what it did.

## How each issue is guarded

Every DQ issue gets two checks, and the difference matters:

1. **Detect (on bronze, non-blocking).** A query counts how many affected rows arrived today and writes
   the count to `ops_dq_results`. Non-zero is *expected*; the number feeds the Data Health dashboard page.
2. **Assert (on silver, blocking).** A Dataform assertion proves the fix worked. It must return zero
   rows. If it fails, the run stops and gold keeps yesterday's data.

`scripts/dq_report.py` prints how many records of each issue were planted. Loading the manifest into a
separate `truth` dataset lets a scorecard compare *detected* against *planted*. The manifest is for
grading only: no silver model may read it.

| Severity | Meaning |
|---|---|
| Block | Assertion failure stops the run before gold |
| Monitor | Logged and charted, run continues |

---

## Part A: shape issues

| Code | Source | What you see | Silver fix | Check |
|---|---|---|---|---|
| SH01 | Google | `metrics_cost_micros` = 748120000 | `/ 1e6` to get rands | `rowConditions`: cost >= 0 |
| SH02 | Google | `metrics_all_conversions` column appears from 1 Sep, shifting column order | Load by header name, not position; allow the new column to be null before 1 Sep | Assert row counts per day > 0 across the change |
| SH03 | Meta | Numbers as strings; spend in USD | `SAFE_CAST`; join FX (see DQ11) | `nonNull` on spend_zar |
| SH04 | Meta | `actions` / `action_values` arrays of `{action_type, value}` | `UNNEST` and pivot `offsite_conversion.fb_pixel_purchase` | Purchases >= 0 |
| SH05 | Meta | Each pull re-sends the last 7 days; conversions grow between pulls | Incremental merge keeping the latest `_pulled_at` per `ad_id` + `date_start` | `uniqueKey: [ad_id, date]` |
| SH06 | GA4 | `event_params` is a shuffled list of `{key, value:{string/int/double}}` | `(SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id')` | `nonNull` on session id |
| SH07 | GA4 | `gclid` / `fbclid` only on the landing `session_start` and `page_view` | Extract from `page_location`, carry across the session with a window function | Match-rate monitor |
| SH08 | GA4 vs CRM | GA4 in UTC microseconds, CRM in `+02:00` text | Convert both to `TIMESTAMP` (UTC); report dates in `Africa/Johannesburg` | Order dates agree between sources |
| SH09 | Weather | Parallel arrays; the city name is not in the payload | Zip arrays with `UNNEST ... WITH OFFSET`; take the city from the file name | One row per city per day |
| SH10 | Meta vs CRM | Meta claims more purchases than happened (view-through, post-click) | Do not sum platform conversions as sales; CRM is the source of truth | Monitor claimed / actual ratio |
| SH11 | CRM | Same person under two customer IDs (guest, then registered) | Identity key from normalised email, falling back to phone (see DQ12) | One `customer_key` per person |

---

## Part B: quality issues

### DQ01: CRM orders exported twice
- **Dimension:** uniqueness · **Source:** `crm/orders.csv` · **Severity:** block
- **What you see:** on a few days every row in `orders.csv` appears twice.
- **Real cause:** the export job was retried and appended instead of overwriting.
- **Detect:** `COUNT(*) - COUNT(DISTINCT TO_JSON_STRING(t))` per file > 0.
- **Fix:** deduplicate exact copies before anything else.
- **Assert on silver:** no duplicate `(order_id, status, updated_at)`.

### DQ02: GA4 events late or re-sent
- **Dimension:** timeliness, uniqueness · **Source:** `ga4/events.ndjson.gz` · **Severity:** block (duplicates), monitor (lateness)
- **What you see:** a file for day D contains some events whose `event_date` is D-1 or D-2, and some
  events appear in two files.
- **Real cause:** GA4 keeps updating a day's export for up to three days.
- **Detect:** rows where `event_date` differs from the file's `dt`; repeated event fingerprints.
- **Fix:** partition silver by `event_date`, not by load date; reprocess the last 3 days on every run;
  deduplicate on a fingerprint (`user_pseudo_id`, `event_timestamp`, `event_name`, `ga_session_id`).
- **Assert on silver:** fingerprint is unique; each purchase `transaction_id` appears once.
- **Note:** the last one or two days are always incomplete. Mark them as provisional on the dashboard.

### DQ03: Refunds arrive as a later update
- **Dimension:** timeliness (change data) · **Source:** `crm/orders.csv` · **Severity:** block
- **What you see:** an order appears as `completed` on its sale day, then again 2 to 10 days later as
  `refunded` with a newer `updated_at`.
- **Real cause:** order status changes after the sale; the export sends changed rows.
- **Detect:** `order_id` already present in silver with an older `updated_at`.
- **Fix:** keep the latest version per `order_id` (`QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY updated_at DESC) = 1`).
  Revenue for past days changes, so gold must rebuild recent weeks.
- **Assert on silver:** `order_id` is unique; refunded orders never count as revenue in gold.

### DQ04: Customer record arrives a day after the order
- **Dimension:** timeliness, integrity · **Source:** `crm/customers.csv` · **Severity:** monitor
- **What you see:** an order references a `customer_id` that is not in any customer file yet.
- **Real cause:** the customer and order exports run at different times.
- **Detect:** orders whose `customer_id` has no match (anti-join).
- **Fix:** keep the order and give it a placeholder customer; the next run fills it in
  (a late-arriving dimension).
- **Assert on silver:** no order older than 2 days without a real customer.

### DQ05: Truncated Meta JSON line
- **Dimension:** validity · **Source:** `meta_ads/insights.jsonl` · **Severity:** monitor
- **What you see:** one line in some pulls is cut off and is not valid JSON.
- **Real cause:** the API pull was interrupted mid-write.
- **Detect:** load raw lines as strings; `SAFE.PARSE_JSON(line) IS NULL`.
- **Fix:** send the line to `quarantine_meta_ads` with a reason. Because Meta re-sends 7 days, the next
  pull usually covers the gap.
- **Assert on silver:** every live Meta ad has a row for every day older than 7 days.

### DQ06: GA4 purchase value 100 times too high
- **Dimension:** validity, accuracy · **Source:** `ga4` purchase events, 8 to 10 Sep · **Severity:** monitor
- **What you see:** `purchase_revenue` is exactly 100 times the CRM revenue for the same order.
- **Real cause:** a tag release sent cents instead of rands.
- **Detect:** compare GA4 value with CRM revenue per `transaction_id`; flag ratios far from 1.
- **Fix:** CRM is the source of truth for revenue. Never use GA4 revenue in gold.
- **Assert on silver:** gold revenue equals CRM revenue.

### DQ07: QA test orders in production
- **Dimension:** validity · **Source:** `crm` and `ga4` · **Severity:** block
- **What you see:** R1.00 orders from `qa.team@kloofoutdoor.co.za`.
- **Real cause:** the QA team tests checkout on the live site.
- **Detect:** internal email domain, or revenue below a threshold.
- **Fix:** exclusion list (seed table) of internal customer IDs and domains; exclude from facts, keep
  in an audit table.
- **Assert on silver:** no fact row belongs to an internal customer.

### DQ08: Internal staff traffic
- **Dimension:** validity · **Source:** `ga4` · **Severity:** monitor
- **What you see:** weekday sessions with event parameter `traffic_type = internal`.
- **Real cause:** GA4 tagged office traffic but the filter was never switched on.
- **Detect:** `traffic_type = 'internal'`.
- **Fix:** exclude from sessions and conversion rates.
- **Assert on silver:** no internal sessions in `fct_sessions`.

### DQ09: Free-text city variants
- **Dimension:** consistency · **Source:** `crm/customers.csv` · **Severity:** block
- **What you see:** `JHB`, `Joburg`, `cape town `, `Kaapstad`, `Durbs` ...
- **Real cause:** city is a free-text field at checkout.
- **Detect:** city not in the reference list.
- **Fix:** trim, lowercase, then map through a `city_mapping` seed table.
- **Assert on silver:** every city is one of the three standard names.

### DQ10: Campaign renamed, same ID
- **Dimension:** consistency · **Source:** `google_ads` · **Severity:** monitor
- **What you see:** campaign `21873002` is `ZA_Shopping_AllProducts` before 1 Jul and
  `ZA_PMax_AllProducts` after. UTM tags change name too.
- **Real cause:** the Shopping campaign was migrated to Performance Max.
- **Detect:** more than one name per `campaign_id`.
- **Fix:** always join on IDs; `dim_campaign` shows the latest name and keeps the old one as history
  (slowly changing dimension). For UTM fallback, map every historical name to the ID.
- **Assert on silver:** one current row per `campaign_id`.

### DQ11: No FX rate on weekends
- **Dimension:** completeness · **Source:** `fx_rates/usd_zar.csv` · **Severity:** block
- **What you see:** Saturday and Sunday files contain only the header.
- **Real cause:** currency markets close on weekends.
- **Detect:** calendar dates with no rate.
- **Fix:** build a full date spine and carry the last known rate forward
  (`LAST_VALUE(rate IGNORE NULLS) OVER (ORDER BY date)`).
- **Assert on silver:** every date has a rate; no Meta row has a null `spend_zar`.

### DQ12: Blank email on a guest record
- **Dimension:** completeness · **Source:** `crm/customers.csv` · **Severity:** block
- **What you see:** some guest customers have an empty email. The same person later registers with an
  email, and the phone number is written differently (`+27 82 555 0142` vs `082 555 0142`).
- **Real cause:** email is optional at guest checkout.
- **Detect:** empty email.
- **Fix:** normalise phones to `+27XXXXXXXXX`; match on hashed email, else hashed phone.
- **Assert on silver:** no `customer_key` is null; the number of distinct people matches the identity graph.

---

## Planted volumes (seed 42, 20 Mar to 15 Sep)

Run `python scripts/dq_report.py output/truth` for the numbers in your own output. Offline weather gives:

| Code | Records | Unit |
|---|---|---|
| DQ01 | 228 | duplicated order rows over 4 days |
| DQ02 | about 21,000 | GA4 events late or re-sent (280 of them purchases) |
| DQ03 | 292 | refund updates |
| DQ04 | 153 | customers exported late |
| DQ05 | 13 | truncated Meta lines |
| DQ06 | 211 | orders with inflated GA4 value |
| DQ07 | 53 | QA test orders (plus the QA account) |
| DQ08 | 1,973 | internal sessions |
| DQ09 | 516 | customers with non-standard city |
| DQ10 | 1 | renamed campaign |
| DQ11 | 52 | weekend days without a rate |
| DQ12 | 98 | guest records with blank email |
