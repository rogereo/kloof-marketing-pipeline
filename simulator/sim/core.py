"""Shared helpers: seeded randomness, config loading, dates."""
from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

SAST = timezone(timedelta(hours=2), name="SAST")  # South Africa has no daylight saving


def seeded(*parts) -> random.Random:
    """A random generator whose output depends only on the parts passed in.

    Same parts in, same numbers out, on any machine. This is what makes reruns identical.
    """
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def weighted(rng: random.Random, mapping: dict):
    keys = list(mapping)
    return rng.choices(keys, weights=[mapping[k] for k in keys], k=1)[0]


def to_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def yesterday_sast() -> date:
    return (datetime.now(SAST) - timedelta(days=1)).date()


def load_config(path: str | Path) -> dict:
    with open(path) as fh:
        cfg = yaml.safe_load(fh)
    cfg["start_date"] = to_date(cfg["start_date"])
    cfg["mess"]["google_schema_change_date"] = to_date(cfg["mess"]["google_schema_change_date"])
    bug = cfg["dq"]["DQ06_ga4_value_bug"]
    bug["start"], bug["end"] = to_date(bug["start"]), to_date(bug["end"])
    cfg["dq"]["DQ10_campaign_rename"]["date"] = to_date(cfg["dq"]["DQ10_campaign_rename"]["date"])
    for ad in cfg.get("scheduled_ads", []):
        ad["launch_date"] = to_date(ad["launch_date"])
    return cfg


def slugify(text: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "_" for ch in text)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


def e164(digits: str) -> str:
    """South African number in international form, e.g. +27825550142."""
    return "+27" + digits
