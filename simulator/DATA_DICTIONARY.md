# Data dictionary

Everything in `output/landing/`, which is the only folder the pipeline may read.
Schemas for BigQuery live in `schemas/`. Known problems in each file are listed in `KNOWN_ISSUES.md`.

All folders are partitioned as `<source>/dt=YYYY-MM-DD/`, where `dt` is the day the file was
**delivered**, which is not always the day the data describes (see DQ02, DQ03, DQ04, SH05).

## Sources at a glance

| Source | Files per dt | Format | Structure | Grain (one row per) | Business key |
|---|---|---|---|---|---|
| Google Ads | `ad_performance.csv` | CSV | Structured | ad per day | `ad_group_ad_ad_id` + `segments_date` |
| Google Ads | `click_view.csv` | CSV | Structured | paid click | `click_view_gclid` |
| Meta Ads | `insights.jsonl` | JSON lines | Semi-structured | ad per day, per pull | `ad_id` + `date_start` (+ `_pulled_at`) |
| GA4 | `events.ndjson.gz` | Gzipped JSON lines | Semi-structured, nested | event | none (build a fingerprint) |
| CRM | `customers.csv` | CSV | Structured, PII | customer record | `customer_id` |
| CRM | `orders.csv` | CSV | Structured | order version | `order_id` + `updated_at` |
| CRM | `order_items.csv` | CSV | Structured | order line | `order_id` + `sku` |
| Creatives | `ad_<id>/copy.txt`, `banner.png` | Text, PNG | Unstructured | ad | `ad_id` (from the folder name) |
| Weather | `<city>.json` | JSON | Semi-structured, parallel arrays | city file with 7 days | city (from file name) + date |
| FX rates | `usd_zar.csv` | CSV | Structured | day | `rate_date` |

## Join keys between sources

| From | To | Key | Notes |
|---|---|---|---|
| Google Ads performance | Google click view | `ad_group_ad_ad_id` | |
| Google click view | GA4 | `click_view_gclid` = `gclid` in `page_location` | Also in `collected_traffic_source.gclid` |
| Meta insights | GA4 | `ad_id` = `utm_content`; click via `fbclid` in `page_location` | Meta has no click-level file |
| GA4 | CRM orders | `ecommerce.transaction_id` = `order_id` | |
| CRM orders | CRM customers | `customer_id` | May arrive a day early (DQ04) |
| CRM customers | person | normalised email, else normalised phone | Two IDs can be one person (SH11, DQ12) |
| Creatives | Ads | folder `ad_<id>` = ad ID | Both platforms |
| Weather | GA4 / CRM | city + date | City from file name, dates in SAST |
| FX rates | Meta | `rate_date` = `date_start` | No weekend rows (DQ11) |

## Google Ads: `ad_performance.csv`

| Column | Example | Notes |
|---|---|---|
| segments_date | 2026-09-15 | |
| customer_id | 812-554-9001 | Ad account, not a shopper |
| campaign_id | 21873002 | Stable; name can change (DQ10) |
| campaign_name | ZA_PMax_AllProducts | |
| ad_group_id, ad_group_name | 1450021, ZA_Shopping_AllProducts \| Group 1 | |
| ad_group_ad_ad_id | 6988120001 | |
| metrics_impressions, metrics_clicks | 1241, 99 | |
| metrics_cost_micros | 748120000 | Rands x 1,000,000 (SH01) |
| metrics_all_conversions | 7.8 | Only from 2026-09-01 (SH02) |
| metrics_conversions, metrics_conversions_value | 7.0, 8441.0 | Google's claim, not real sales (SH10) |

## Google Ads: `click_view.csv`

`segments_date`, `click_view_gclid`, `campaign_id`, `ad_group_id`, `ad_group_ad_ad_id`,
`click_view_area_of_interest_city`.

## Meta Ads: `insights.jsonl`

| Field | Example | Notes |
|---|---|---|
| account_id, account_currency | act_1029384756, USD | |
| date_start, date_stop | 2026-09-09 | The day described |
| campaign_id, campaign_name | 120210040000000000, Winter Sale \| Prospecting | |
| adset_id, adset_name, ad_id, ad_name | | |
| impressions, clicks, spend | "13584", "166", "58.34" | Strings; spend in USD (SH03) |
| actions | `[{"action_type":"offsite_conversion.fb_pixel_purchase","value":"11"}]` | Array (SH04) |
| action_values | same shape, USD value | Only present when there are purchases |
| attribution_setting | 7d_click_1d_view | |
| _pulled_at | 2026-09-16T04:00:00Z | Latest pull wins (SH05) |

Each file holds the trailing 7 days. Some lines are cut off (DQ05).

## GA4: `events.ndjson.gz`

Schema: `schemas/ga4_events.json`. Top level: `event_date` (YYYYMMDD, SAST), `event_timestamp`
(UTC microseconds), `event_name`, `event_params`, `user_pseudo_id`, `device`, `geo`,
`collected_traffic_source`, `ecommerce`, `items`.

| Event | When | Useful parameters |
|---|---|---|
| session_start, page_view | Start of every session | `ga_session_id`, `ga_session_number`, `page_location` (click IDs, UTMs), `page_referrer` |
| view_item, add_to_cart, begin_checkout | During the session | `items` |
| purchase | Order placed | `transaction_id`, `value`, `currency`, plus `ecommerce` |

Session key: `user_pseudo_id` + `ga_session_id`. Some events carry `traffic_type = internal` (DQ08).

## CRM

**customers.csv:** `customer_id`, `email` (raw, can be messy or blank), `first_name`, `last_name`,
`phone` (`+27 82 555 0142` or `082 555 0142`), `city` (free text), `created_at` (+02:00),
`is_guest`, `marketing_opt_in`. Treat email, names and phone as PII.

**orders.csv:** `order_id`, `customer_id`, `order_ts` (+02:00), `currency` (ZAR), `subtotal`,
`discount`, `revenue`, `status` (`completed` or `refunded`), `item_count`, `updated_at`.
The same order can appear again later with a new status (DQ03).

**order_items.csv:** `order_id`, `sku`, `product_name`, `unit_price`, `quantity`.

## Creatives

One folder per ad, delivered on the ad's launch day. `copy.txt` holds the ad text; `banner.png` is a
600 x 314 image with headline, product, optional discount badge and call to action.
Attributes to extract: `tone` (urgent, informative, aspirational, playful), `discount_pct`,
`cta` (shop_now, learn_more, get_offer, sign_up), `product`.

## Weather

Open-Meteo response shape, schema `schemas/weather_daily.json`. `daily.time`,
`daily.temperature_2m_max`, `daily.temperature_2m_min` and `daily.precipitation_sum` are parallel
arrays covering 7 days. Files: `cape_town.json`, `johannesburg.json`, `durban.json` (SH09).

## FX rates

`rate_date`, `base_currency` (USD), `quote_currency` (ZAR), `rate`. Header only on weekends (DQ11).

## Reference lists

**Campaigns**

| Key | Platform | ID | Name |
|---|---|---|---|
| G_BRAND | Google | 21873001 | ZA_Search_Brand |
| G_SHOP | Google | 21873002 | ZA_Shopping_AllProducts, then ZA_PMax_AllProducts from 1 Jul |
| G_GENERIC | Google | 21873003 | ZA_Search_Generic_Jackets |
| M_WINTER | Meta | 120210040000000000 | Winter Sale \| Prospecting |
| M_RETARGET | Meta | 120210050000000000 | Retargeting \| Viewed Product |
| M_AWARE | Meta | 120210060000000000 | Trail Stories \| Awareness |

**Cities:** Cape Town, Johannesburg, Durban.
**Internal identifiers (DQ07):** email domain `kloofoutdoor.co.za`.

## Truth store (grading only)

`output/truth/` holds what really happened: `people.csv` (hidden value types), `ads.csv` (hidden
creative attributes), `orders/`, `spend/`, `claims/`, `weather.csv` and `dq_manifest/`.
Load it into a separate `kloof_truth` dataset for scorecards. No bronze, silver or gold model may
read from it.
