# Kloof Outdoor data simulator

A seeded Python simulator that creates six months of marketing data for a fictional South African
outdoor retailer, in the native shape of six source systems, with realistic mess built in.
It also writes a **truth store**: what really happened, so the pipeline can be graded.

**Business question the data is built for:** *Where should Kloof move next month's ad budget to win
customers who will be worth the most over the next 90 days?*

| Document | What it covers |
|---|---|
| `DATA_DICTIONARY.md` | Every file, column, grain and join key |
| `KNOWN_ISSUES.md` | 11 shape issues and 12 planted data quality issues, with fixes and checks |
| `schemas/` | BigQuery schemas for the bronze tables |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m sim backfill --end 2026-09-15      # history: 20 Mar to 15 Sep (about a minute)
python -m pytest -q                          # 27 checks
python scripts/dq_report.py output/truth     # planted data quality issues, by code
python scripts/story_check.py output/truth   # the answer key your gold marts should match
```

Thursday and Friday mornings (writes yesterday, uploads, retests):

```bash
BUCKET=your-bucket-name ./scripts/daily.sh
```

Add `--offline` to any command to skip the weather API and use synthetic weather.
Delete `cache/` only if you want to re-fetch weather; it changes the simulated past.

## Why 180 days when the dashboard shows 30

The model uses each customer's first 7 days as features and their revenue in days 8 to 97 as the
label, so a training row needs 97 days of history. The dashboard defaults to the last 30 days.

## Output layout

```
output/
  landing/                        <- upload this to GCS as-is
    google_ads/dt=YYYY-MM-DD/     ad_performance.csv, click_view.csv
    meta_ads/dt=YYYY-MM-DD/       insights.jsonl   (trailing 7 days, every run)
    ga4/dt=YYYY-MM-DD/            events.ndjson.gz
    crm/dt=YYYY-MM-DD/            customers.csv, orders.csv, order_items.csv
    creatives/dt=YYYY-MM-DD/      ad_<id>/copy.txt, ad_<id>/banner.png
    weather/dt=YYYY-MM-DD/        cape_town.json, johannesburg.json, durban.json
    fx_rates/dt=YYYY-MM-DD/       usd_zar.csv   (reference data for Meta's USD)
  truth/                          <- never load into the pipeline; tests and scorecards only
    people.csv  ads.csv  weather.csv
    orders/  spend/  claims/      (dt= partitioned)
    dq_manifest/                  every planted data quality issue, by code (dt= partitioned)
```

## Build steps

| Step | Objective | Where | Proactive test |
|---|---|---|---|
| 0 Skeleton | Seeded randomness so reruns are byte-identical | `sim/core.py` | `test_reruns_are_identical` |
| 1 Campaigns and ads | 6 campaigns, 21 ads, hidden tone / discount / CTA | `sim/world/campaigns.py` | `test_ads_have_campaigns_and_attributes` |
| 2 Customers | People with hidden value types | `sim/world/engine.py` (`_new_person`) | `test_value_types_present` |
| 3 Weather | Real Open-Meteo history, cached, synthetic fallback | `sim/world/weather.py` | `test_weather_complete` |
| 4 Journey engine | Daily loop: spend, clicks, sessions, orders, repeat buying, claims | `sim/world/engine.py` | `test_vip_orders_more` |
| 5 Ad emitters | Google CSV (micros, schema change) and Meta JSON (USD, restatements) | `sim/emitters/ads.py` | `test_spend_reconciles`, `test_meta_overclaims`, `test_google_schema_change` |
| 6 GA4 emitter | Nested events; click ID only on landing pages | `sim/emitters/ga4.py` | `test_ga4_purchases`, `test_click_id_only_on_landing` |
| 7 CRM emitter | PII, local timestamps, guest duplicates, email or phone matching | `sim/emitters/other.py` | `test_crm_identity_resolution` |
| 8 Creatives | Copy and banner per ad at launch | `sim/emitters/other.py` | `test_creatives` |
| 9 Daily mode | One day at a time, identical to the backfill | `sim/cli.py` | `test_daily_matches_backfill`, `test_meta_trailing_window` |

## Data quality issues

The simulator plants two kinds of problems, each with a code used everywhere (config, manifest,
docs, Dataform tags). Full detail, fixes and checks are in `KNOWN_ISSUES.md`.

- **SH01 to SH11, shape:** correct but awkward data (micros, nested JSON, USD, schema change,
  7-day restatements, click IDs only on landing pages).
- **DQ01 to DQ12, quality:** duplicated exports, late and re-sent events, refund updates,
  late customer records, truncated JSON, a revenue tag bug, test orders, internal traffic,
  city typos, a campaign rename, weekend FX gaps, blank emails.

Each DQ issue has its own seeded generator and config switch under `dq:` in `config.yaml`, and
every affected record is listed in `output/truth/dq_manifest/`.

## Tests

| Group | Checks |
|---|---|
| Build steps 0 to 9 | Reruns identical, daily run equals backfill, spend reconciles, GA4 and CRM agree with truth |
| Planted issues | The manifest describes the files exactly, for every DQ code |
| Data contracts | GA4, weather and CSV files fit the schemas in `schemas/` |

## The planted story (offline weather, seed 42)

| Campaign | Platform ROAS | Actual ROAS | Value-adjusted ROAS | One-time buyers |
|---|---|---|---|---|
| G_SHOP | 4.54 | 3.70 | 7.66 | 33% |
| M_WINTER | 5.22 | 2.37 | 3.90 | 90% |

Meta Winter Sale looks better than Shopping in the ad platform and is clearly worse once
customers are valued. Exact numbers shift slightly when real weather is used.
