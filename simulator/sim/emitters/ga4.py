"""Step 6: GA4 BigQuery-export-shaped events, one JSON object per line.

Key realism: event_params is a list of key/value records, the click ID only appears on the
landing page, and purchases sometimes never fire or fire twice.
"""
from __future__ import annotations

import gzip
import json
from datetime import date, timedelta
from pathlib import Path

from sim.core import SAST, seeded, slugify

OS_BY_DEVICE = {"mobile": ["Android", "iOS"], "desktop": ["Windows", "Macintosh"], "tablet": ["iOS", "Android"]}


def p_str(key, value):
    return {"key": key, "value": {"string_value": value}}


def p_int(key, value):
    return {"key": key, "value": {"int_value": value}}


def p_dbl(key, value):
    return {"key": key, "value": {"double_value": value}}


def _micros(ts, rng) -> int:
    return int(ts.timestamp()) * 1_000_000 + rng.randint(0, 999_999)


def _item(sku, name, price, qty):
    return {"item_id": sku, "item_name": name, "price": price, "quantity": qty}


def session_events(s, catalog, dq) -> list[dict]:
    rng = seeded("ga4", s.session_key)
    os_name = rng.choice(OS_BY_DEVICE[s.device])
    events = []

    def add(name, ts, page, extra=(), ecommerce=None, items=None, first=False):
        params = [p_int("ga_session_id", s.ga_session_id), p_int("ga_session_number", s.session_number),
                  p_str("page_location", page), *extra]
        if first and s.referrer:
            params.append(p_str("page_referrer", s.referrer))
        if not first:
            params.append(p_int("engagement_time_msec", rng.randint(800, 60000)))
        if s.internal:  # DQ08: tagged as internal, but nobody filtered it out
            params.append(p_str("traffic_type", "internal"))
        rng.shuffle(params)  # real exports do not promise an order: query by key, not position
        events.append({
            "event_date": ts.astimezone(SAST).strftime("%Y%m%d"),
            "event_timestamp": _micros(ts, rng),
            "event_name": name,
            "event_params": params,
            "user_pseudo_id": s.pseudo_id,
            "device": {"category": s.device, "operating_system": os_name},
            "geo": {"country": "South Africa", "city": s.city},
            "collected_traffic_source": s.collected_traffic_source if first else None,
            "ecommerce": ecommerce,
            "items": items or [],
        })

    t = s.start
    add("session_start", t, s.landing_url, first=True)
    add("page_view", t + timedelta(milliseconds=400), s.landing_url,
        extra=[p_str("page_title", "Kloof Outdoor")], first=True)

    order = s.order
    if order is None:
        product = rng.choice(catalog)
        item = [_item(product["id"], product["name"], float(product["price"]), 1)]
        page = f"https://kloof.co.za/products/{slugify(product['name'])}"
        if s.depth >= 1:
            add("view_item", t + timedelta(seconds=rng.randint(15, 90)), page, items=item)
        if s.depth >= 2:
            add("add_to_cart", t + timedelta(seconds=rng.randint(100, 170)), page, items=item)
        return events

    items = [_item(*i) for i in order.items]
    span = max((order.ts - t).total_seconds(), 60)
    first_product = f"https://kloof.co.za/products/{slugify(order.items[0][1])}"
    add("view_item", t + timedelta(seconds=span * 0.2), first_product, items=items[:1])
    add("add_to_cart", t + timedelta(seconds=span * 0.45), first_product, items=items)
    add("begin_checkout", t + timedelta(seconds=span * 0.7), "https://kloof.co.za/checkout", items=items)
    if order.ga4_fired:
        value = order.revenue
        if value_bug_hits(order, dq):  # DQ06: a tag release sent cents instead of rands
            value = round(value * dq["DQ06_ga4_value_bug"]["multiplier"], 2)
        purchase = dict(
            extra=[p_str("transaction_id", order.order_id), p_dbl("value", value),
                   p_str("currency", "ZAR")],
            ecommerce={"transaction_id": order.order_id, "purchase_revenue": value,
                       "total_item_quantity": len(items)},
            items=items,
        )
        add("purchase", order.ts, "https://kloof.co.za/checkout/thank-you", **purchase)
        if order.ga4_duplicated:  # thank-you page reloaded, tag fires again
            add("purchase", order.ts + timedelta(seconds=rng.randint(2, 20)),
                "https://kloof.co.za/checkout/thank-you", **purchase)
    return events


def value_bug_hits(order, dq) -> bool:
    bug = dq["DQ06_ga4_value_bug"]
    return bug["start"] <= order.ts.date() <= bug["end"]


def arrival(session_key: str, i: int, dq) -> tuple[int, bool]:
    """DQ02: how many days late this event arrives, and whether it is also re-sent next day."""
    r = seeded("dq02", session_key, i).random()
    late, very_late, resent = (dq["DQ02_ga4_late_event_rate"], dq["DQ02_ga4_very_late_event_rate"],
                               dq["DQ02_ga4_resent_event_rate"])
    if r < very_late:
        return 2, False
    if r < very_late + late:
        return 1, False
    return 0, r < very_late + late + resent


def write_ga4(cfg, engine, d: date, root: Path, manifest: list) -> int:
    """The file for day D holds D's on-time events plus late arrivals from D-1 and D-2."""
    out = root / "ga4" / f"dt={d}"
    out.mkdir(parents=True, exist_ok=True)
    dq = cfg["dq"]
    events, late_counts = [], {}
    for src_day in (d - timedelta(days=2), d - timedelta(days=1), d):
        cache = engine.__dict__.setdefault("_ga4_cache", {})
        for key in [k for k in cache if k < d - timedelta(days=2)]:
            del cache[key]
        if src_day not in cache:
            cache[src_day] = [(s, session_events(s, cfg["catalog"], dq))
                              for s in engine.sessions_by_day.get(src_day, [])]
        for s, session_evts in cache[src_day]:
            for i, e in enumerate(session_evts):
                offset, resent = arrival(s.session_key, i, dq)
                arrives = src_day + timedelta(days=offset)
                if arrives == d:
                    events.append(e)
                if resent and src_day + timedelta(days=1) == d:
                    events.append(e)
                is_purchase = e["event_name"] == "purchase"
                if arrives == d and offset > 0:
                    late_counts[(src_day, offset)] = late_counts.get((src_day, offset), 0) + 1
                    if is_purchase:
                        manifest.append(("DQ02", "ga4", d, e["ecommerce"]["transaction_id"],
                                         f"purchase from {src_day} arrived {offset} day(s) late"))
                if resent and src_day + timedelta(days=1) == d:
                    late_counts[(src_day, "resent")] = late_counts.get((src_day, "resent"), 0) + 1
                    if is_purchase:
                        manifest.append(("DQ02", "ga4", d, e["ecommerce"]["transaction_id"],
                                         f"purchase from {src_day} re-sent (duplicate)"))
        if src_day != d:
            continue
        internal = 0
        for s in engine.sessions_by_day.get(d, []):
            internal += s.internal
            if s.order and s.order.ga4_fired and value_bug_hits(s.order, dq):
                manifest.append(("DQ06", "ga4", d, s.order.order_id,
                                 f"purchase value x{dq['DQ06_ga4_value_bug']['multiplier']}"))
            if s.order and s.order.is_test:
                manifest.append(("DQ07", "ga4", d, s.order.order_id, "test order purchase event"))
        if internal:
            manifest.append(("DQ08", "ga4", d, f"{internal} sessions", "traffic_type=internal"))
    for (src_day, kind), n in sorted(late_counts.items(), key=str):
        label = "re-sent" if kind == "resent" else f"{kind} day(s) late"
        manifest.append(("DQ02", "ga4", d, f"event_date={src_day}", f"{n} events {label}"))
    events.sort(key=lambda e: e["event_timestamp"])
    # gzip keeps uploads small; mtime=0 keeps the bytes identical between reruns
    with open(out / "events.ndjson.gz", "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as fh:
        for e in events:
            fh.write((json.dumps(e, separators=(",", ":")) + "\n").encode())
    return len(events)
