"""Steps 7 and 8, weather output, and the truth store."""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from sim.core import e164, seeded
from sim.world.weather import trailing_days

TONE_COLOURS = {"urgent": (200, 60, 40), "informative": (40, 90, 160),
                "aspirational": (40, 110, 80), "playful": (230, 160, 30)}


def _csv(path: Path, header: list, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(r)
            n += 1
    return n


# ---------------- Step 7: CRM ----------------
CITY_VARIANTS = {  # DQ09: what people type into a free-text city box
    "Johannesburg": ["Joburg", "JHB", "johannesburg", " Johannesburg"],
    "Cape Town": ["CPT", "cape town", "Cape Town ", "Kaapstad"],
    "Durban": ["DBN", "Durbs", "durban"],
}


def write_crm(cfg, engine, d: date, root: Path, manifest: list) -> tuple[int, int]:
    dq = cfg["dq"]
    out = root / "crm" / f"dt={d}"

    customer_rows = []
    for c in engine.crm_customers:
        if c.export_date != d:
            continue
        city = c.city
        r = seeded("dq09", c.crm_id)
        if r.random() < dq["DQ09_city_variant_rate"]:
            city = r.choice(CITY_VARIANTS[c.city])
            manifest.append(("DQ09", "crm", d, c.crm_id, f"city {city!r} means {c.city}"))
        if c.export_date != c.created_at.date():
            manifest.append(("DQ04", "crm", d, c.crm_id, f"created {c.created_at.date()}, exported a day late"))
        if c.email == "":
            manifest.append(("DQ12", "crm", d, c.crm_id, "blank email; phone is the only link"))
        if c.pid == "QA":
            manifest.append(("DQ07", "crm", d, c.crm_id, "QA test customer"))
        customer_rows.append([c.crm_id, c.email, c.first_name, c.last_name, c.phone, city,
                              c.created_at.isoformat(), str(c.is_guest).lower(),
                              str(c.marketing_opt_in).lower()])
    n_c = _csv(out / "customers.csv",
               ["customer_id", "email", "first_name", "last_name", "phone", "city", "created_at",
                "is_guest", "marketing_opt_in"], customer_rows)

    placed = [o for o in engine.orders + engine.test_orders if o.ts.date() == d]
    placed.sort(key=lambda o: o.ts)
    order_rows = [[o.order_id, o.crm_id, o.ts.isoformat(), "ZAR", f"{o.subtotal:.2f}", f"{o.discount:.2f}",
                   f"{o.revenue:.2f}", "completed", len(o.items), o.ts.isoformat()] for o in placed]
    for o in placed:
        if o.is_test:
            manifest.append(("DQ07", "crm", d, o.order_id, "R1.00 QA test order"))
    for o in engine.orders:  # DQ03: refunds arrive as a second row for the same order
        if o.refunded_at is not None and o.refunded_at.date() == d:
            order_rows.append([o.order_id, o.crm_id, o.ts.isoformat(), "ZAR", f"{o.subtotal:.2f}",
                               f"{o.discount:.2f}", f"{o.revenue:.2f}", "refunded", len(o.items),
                               o.refunded_at.isoformat()])
            manifest.append(("DQ03", "crm", d, o.order_id, f"refund update for order placed {o.ts.date()}"))
    if seeded("dq01", d).random() < dq["DQ01_crm_duplicate_export_day_rate"]:
        manifest.append(("DQ01", "crm", d, "orders.csv", f"{len(order_rows)} rows exported twice"))
        order_rows = order_rows + order_rows  # the export job ran twice and appended
    n_o = _csv(out / "orders.csv",
               ["order_id", "customer_id", "order_ts", "currency", "subtotal", "discount", "revenue",
                "status", "item_count", "updated_at"], order_rows)
    _csv(out / "order_items.csv", ["order_id", "sku", "product_name", "unit_price", "quantity"],
         ([o.order_id, sku, name, f"{price:.2f}", qty] for o in placed for sku, name, price, qty in o.items))
    return n_c, n_o


# ---------------- Step 8: creatives ----------------
def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "C:/Windows/Fonts/arialbd.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def write_creatives(engine, d: date, root: Path) -> int:
    launched = [a for a in engine.ads.values() if a.launch_date == d]
    for ad in launched:
        folder = root / "creatives" / f"dt={d}" / f"ad_{ad.ad_id}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "copy.txt").write_text(ad.copy + "\n")
        img = Image.new("RGB", (600, 314), TONE_COLOURS[ad.tone])
        draw = ImageDraw.Draw(img)
        draw.text((30, 40), "KLOOF OUTDOOR", font=_font(18), fill=(255, 255, 255))
        draw.text((30, 110), ad.headline, font=_font(34), fill=(255, 255, 255))
        draw.text((30, 170), ad.product, font=_font(22), fill=(255, 255, 255))
        if ad.discount_pct:
            draw.ellipse((470, 30, 570, 130), fill=(255, 255, 255))
            draw.text((490, 62), f"-{ad.discount_pct}%", font=_font(26), fill=TONE_COLOURS[ad.tone])
        cta = {"shop_now": "SHOP NOW", "learn_more": "LEARN MORE",
               "get_offer": "GET THE OFFER", "sign_up": "SIGN UP"}[ad.cta]
        draw.rectangle((30, 240, 250, 285), fill=(255, 255, 255))
        draw.text((45, 250), cta, font=_font(20), fill=(30, 30, 30))
        img.save(folder / "banner.png")
    return len(launched)


# ---------------- Weather output ----------------
def write_weather(cfg, weather, d: date, root: Path) -> int:
    out = root / "weather" / f"dt={d}"
    out.mkdir(parents=True, exist_ok=True)
    days = trailing_days(d, cfg["start_date"], 7)
    for city in cfg["cities"]:
        values = [weather.get(city["name"], x) for x in days]
        payload = {  # same shape as Open-Meteo; note the city name is NOT in the payload
            "latitude": city["lat"], "longitude": city["lon"], "generationtime_ms": 0.31,
            "utc_offset_seconds": 7200, "timezone": "Africa/Johannesburg",
            "timezone_abbreviation": "SAST", "elevation": city["elevation"],
            "daily_units": {"time": "iso8601", "temperature_2m_max": "°C",
                            "temperature_2m_min": "°C", "precipitation_sum": "mm"},
            "daily": {"time": [x.isoformat() for x in days],
                      "temperature_2m_max": [v["tmax"] for v in values],
                      "temperature_2m_min": [v["tmin"] for v in values],
                      "precipitation_sum": [v["precip"] for v in values]},
        }
        (out / f"{city['slug']}.json").write_text(json.dumps(payload, ensure_ascii=False))
    return len(cfg["cities"])


# ---------------- Truth store ----------------
def write_truth_day(engine, d: date, truth: Path) -> None:
    _csv(truth / "orders" / f"dt={d}" / "orders.csv",
         ["order_id", "person_id", "crm_customer_id", "order_ts", "revenue", "status", "is_first_order",
          "channel", "campaign_key", "ad_id", "ga4_purchase_fired", "ga4_purchase_duplicated", "refunded_at"],
         ([o.order_id, o.pid, o.crm_id, o.ts.isoformat(), f"{o.revenue:.2f}", o.status, o.is_first,
           o.channel, o.campaign_key or "", o.ad_id or "", o.ga4_fired, o.ga4_duplicated,
           o.refunded_at.isoformat() if o.refunded_at else ""]
          for o in engine.orders if o.ts.date() == d))
    _csv(truth / "spend" / f"dt={d}" / "spend.csv",
         ["date", "platform", "campaign_key", "ad_id", "spend_zar", "clicks", "impressions"],
         ([s.day, s.platform, s.campaign_key, s.ad_id, f"{s.spend_zar:.2f}", s.clicks, s.impressions]
          for s in engine.spend if s.day == d))
    _csv(truth / "claims" / f"dt={d}" / "claims.csv",
         ["claim_date", "platform", "ad_id", "order_id", "revenue", "lag_days", "claim_type"],
         ([c.claim_date, c.platform, c.ad_id, c.order_id, f"{c.revenue:.2f}", c.lag_days, c.claim_type]
          for c in engine.claims if c.claim_date == d))


def write_truth_snapshots(engine, weather, cfg, end: date, truth: Path) -> None:
    _csv(truth / "people.csv",
         ["person_id", "value_type", "city", "acquired_date", "acquired_channel", "acquired_campaign_key",
          "acquired_ad_id", "crm_customer_ids", "email_normalised", "phone_normalised", "orders_to_date"],
         ([p.pid, p.value_type, p.city, p.acq_date, p.acq_channel, p.acq_campaign or "", p.acq_ad or "",
           "|".join(p.crm_ids), p.email, e164(p.phone_digits), p.n_orders] for p in engine.people.values()))
    _csv(truth / "ads.csv",
         ["ad_id", "campaign_key", "platform", "tone", "discount_pct", "cta", "product", "launch_date",
          "live_by_end"],
         ([a.ad_id, a.campaign_key, a.platform, a.tone, a.discount_pct, a.cta, a.product, a.launch_date,
           a.launch_date <= end] for a in engine.ads.values()))
    _csv(truth / "weather.csv", ["city", "date", "tmax", "tmin", "precip", "source"],
         ([c["name"], day, v["tmax"], v["tmin"], v["precip"], v["source"]]
          for c in cfg["cities"] for day, v in sorted(weather.data[c["name"]].items())
          if date.fromisoformat(day) <= end))


def write_manifest(rows: list, d: date, truth: Path) -> None:
    _csv(truth / "dq_manifest" / f"dt={d}" / "manifest.csv",
         ["issue_code", "source", "file_dt", "record_key", "detail"],
         sorted(rows, key=lambda r: (r[0], str(r[3]))))
