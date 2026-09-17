"""Step 5: ad platform emitters (Google Ads CSV, Meta insights JSON lines) plus the FX reference."""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sim.core import seeded
from sim.world.weather import trailing_days

GOOGLE_ACCOUNT = "812-554-9001"
META_ACCOUNT = "act_1029384756"


def fx_rate(cfg: dict, d: date) -> float:
    """USD to ZAR rate for a day: a gentle wave plus noise, stable across runs.

    DQ11: markets close on weekends, so Saturday and Sunday use Friday's rate.
    """
    if cfg["dq"]["DQ11_fx_weekend_gaps"] and d.weekday() >= 5:
        d = d - timedelta(days=d.weekday() - 4)
    base = cfg["fx"]["usd_zar_base"]
    wave = 0.02 * math.sin(d.toordinal() / 9)
    noise = seeded("fx", d).uniform(-0.004, 0.004)
    return round(base * (1 + wave + noise), 4)


class AdIndex:
    """Look-ups the emitters need: spend by ad-day, claims by platform/ad/day."""

    def __init__(self, engine):
        self.engine = engine
        self.spend = {(s.day, s.ad_id): s for s in engine.spend}
        self.claims = defaultdict(list)
        for c in engine.claims:
            self.claims[(c.platform, c.claim_date, c.ad_id)].append(c)
        self.campaigns = {c.key: c for c in engine.campaigns}


def write_fx(cfg, d: date, root: Path, manifest: list) -> None:
    out = root / "fx_rates" / f"dt={d}"
    out.mkdir(parents=True, exist_ok=True)
    weekend_gap = cfg["dq"]["DQ11_fx_weekend_gaps"] and d.weekday() >= 5
    with open(out / "usd_zar.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["rate_date", "base_currency", "quote_currency", "rate"])
        if weekend_gap:
            manifest.append(("DQ11", "fx_rates", d, d.isoformat(), "weekend: header only, no rate"))
        else:
            w.writerow([d.isoformat(), "USD", "ZAR", fx_rate(cfg, d)])


def write_google(cfg, idx: AdIndex, d: date, root: Path) -> None:
    out = root / "google_ads" / f"dt={d}"
    out.mkdir(parents=True, exist_ok=True)
    schema_changed = d >= cfg["mess"]["google_schema_change_date"]
    cols = ["segments_date", "customer_id", "campaign_id", "campaign_name", "ad_group_id",
            "ad_group_name", "ad_group_ad_ad_id", "metrics_impressions", "metrics_clicks",
            "metrics_cost_micros"]
    if schema_changed:
        cols.append("metrics_all_conversions")   # new column lands in the middle: order shifts
    cols += ["metrics_conversions", "metrics_conversions_value"]

    with open(out / "ad_performance.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cols)
        for camp in idx.engine.campaigns:
            if camp.platform != "google":
                continue
            for ad in camp.ads:
                s = idx.spend.get((d, ad.ad_id))
                if s is None:
                    continue
                claims = idx.claims[("google", d, ad.ad_id)]
                conv = float(len(claims))
                row = [d.isoformat(), GOOGLE_ACCOUNT, camp.platform_id, camp.name_on(d), ad.group_id,
                       ad.group_name, ad.ad_id, s.impressions, s.clicks, int(round(s.spend_zar * 1_000_000))]
                if schema_changed:
                    row.append(round(conv * 1.12, 1))
                row += [round(conv, 1), round(sum(c.revenue for c in claims), 2)]
                w.writerow(row)

    with open(out / "click_view.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["segments_date", "click_view_gclid", "campaign_id", "ad_group_id",
                    "ad_group_ad_ad_id", "click_view_area_of_interest_city"])
        for s in idx.engine.sessions_by_day.get(d, []):
            if s.click and s.click["platform"] == "google":
                ad = idx.engine.ads[s.click["ad_id"]]
                camp = idx.campaigns[ad.campaign_key]
                w.writerow([d.isoformat(), s.click["click_id"], camp.platform_id, ad.group_id, ad.ad_id, s.city])


def write_meta(cfg, idx: AdIndex, run_day: date, root: Path, manifest: list) -> None:
    """One pull per run day, covering the trailing window, as Meta numbers keep changing."""
    out = root / "meta_ads" / f"dt={run_day}"
    out.mkdir(parents=True, exist_ok=True)
    window = cfg["mess"]["meta_restatement_days"]
    pulled_at = datetime.combine(run_day + timedelta(days=1), time(4, 0), timezone.utc)
    lines = []
    for d in trailing_days(run_day, cfg["start_date"], window):
        age = (run_day - d).days
        rate = fx_rate(cfg, d)
        for camp in idx.engine.campaigns:
            if camp.platform != "meta":
                continue
            for ad in camp.ads:
                s = idx.spend.get((d, ad.ad_id))
                if s is None:
                    continue
                visible = [c for c in idx.claims[("meta", d, ad.ad_id)] if c.lag_days <= age]
                actions = [{"action_type": "link_click", "value": str(s.clicks)}]
                values = []
                if visible:
                    actions.append({"action_type": "offsite_conversion.fb_pixel_purchase",
                                    "value": str(len(visible))})
                    values.append({"action_type": "offsite_conversion.fb_pixel_purchase",
                                   "value": f"{sum(c.revenue for c in visible) / rate:.2f}"})
                record = {
                    "account_id": META_ACCOUNT, "account_currency": "USD",
                    "date_start": d.isoformat(), "date_stop": d.isoformat(),
                    "campaign_id": camp.platform_id, "campaign_name": camp.name,
                    "adset_id": ad.group_id, "adset_name": ad.group_name,
                    "ad_id": ad.ad_id, "ad_name": ad.name,
                    "impressions": str(s.impressions), "clicks": str(s.clicks),
                    "spend": f"{s.spend_zar / rate:.2f}",
                    "actions": actions,
                    "attribution_setting": "7d_click_1d_view",
                    "_pulled_at": pulled_at.isoformat().replace("+00:00", "Z"),
                }
                if values:
                    record["action_values"] = values
                lines.append((record, json.dumps(record, separators=(",", ":"))))
    rng = seeded("dq05", run_day)
    if lines and rng.random() < cfg["dq"]["DQ05_meta_truncated_pull_rate"]:
        i = rng.randrange(len(lines))  # DQ05: the pull was cut off mid-line
        record, text = lines[i]
        lines[i] = (record, text[: rng.randint(40, len(text) - 40)])
        manifest.append(("DQ05", "meta_ads", run_day, f"{record['ad_id']}|{record['date_start']}",
                         "truncated JSON line"))
    with open(out / "insights.jsonl", "w") as fh:
        for _, text in lines:
            fh.write(text + "\n")
