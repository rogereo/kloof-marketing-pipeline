"""Command line: `python -m sim backfill` and `python -m sim daily`."""
from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

from sim.core import daterange, load_config, to_date, yesterday_sast
from sim.emitters.ads import AdIndex, write_fx, write_google, write_meta
from sim.emitters.ga4 import write_ga4
from sim.emitters.other import (write_creatives, write_crm, write_manifest, write_truth_day,
                                write_truth_snapshots, write_weather)
from sim.world.engine import Engine
from sim.world.weather import WeatherStore


def run(config: str, out: str, end: date, emit_days: list[date], cache: str, offline: bool) -> dict:
    t0 = time.time()
    cfg = load_config(config)
    root, truth = Path(out) / "landing", Path(out) / "truth"
    weather = WeatherStore(cfg, cache, offline=offline)
    weather.ensure(cfg["start_date"], end)
    engine = Engine(cfg, weather)
    engine.run(end, set(emit_days))
    idx = AdIndex(engine)

    stats = {"days": len(emit_days), "ga4_events": 0, "crm_customers": 0, "crm_orders": 0, "creatives": 0,
             "dq_issue_records": 0}
    for d in emit_days:
        manifest: list = []
        write_google(cfg, idx, d, root)
        write_meta(cfg, idx, d, root, manifest)
        write_fx(cfg, d, root, manifest)
        stats["ga4_events"] += write_ga4(cfg, engine, d, root, manifest)
        c, o = write_crm(cfg, engine, d, root, manifest)
        stats["crm_customers"] += c
        stats["crm_orders"] += o
        stats["creatives"] += write_creatives(engine, d, root)
        write_weather(cfg, weather, d, root)
        write_truth_day(engine, d, truth)
        if d == cfg["dq"]["DQ10_campaign_rename"]["date"]:
            rename = cfg["dq"]["DQ10_campaign_rename"]
            manifest.append(("DQ10", "google_ads", d, rename["campaign"], f"renamed to {rename['new_name']}"))
        write_manifest(manifest, d, truth)
        stats["dq_issue_records"] += len(manifest)
    write_truth_snapshots(engine, weather, cfg, end, truth)

    sources = {s for c in cfg["cities"] for s in [weather.get(c["name"], end)["source"]]}
    stats.update(people_total=len(engine.people), weather_source_on_last_day=", ".join(sorted(sources)),
                 seconds=round(time.time() - t0, 1))
    return stats


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="sim", description="Kloof Outdoor data simulator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, help_text in (("backfill", "write every day from start_date to --end"),
                            ("daily", "write a single day (default: yesterday)")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--config", default="config.yaml")
        p.add_argument("--out", default="output")
        p.add_argument("--cache", default="cache", help="weather cache folder")
        p.add_argument("--offline", action="store_true", help="skip the weather API, use synthetic weather")
        if name == "backfill":
            p.add_argument("--end", type=to_date, default=None, help="last day (default: yesterday)")
        else:
            p.add_argument("--date", type=to_date, default=None, help="day to write (default: yesterday)")
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.cmd == "backfill":
        end = args.end or yesterday_sast()
        emit = list(daterange(cfg["start_date"], end))
    else:
        end = args.date or yesterday_sast()
        emit = [end]
    print(f"{args.cmd}: simulating {cfg['start_date']} to {end}, writing {len(emit)} day(s) to {args.out}/")
    stats = run(args.config, args.out, end, emit, args.cache, args.offline)
    for k, v in stats.items():
        print(f"  {k:28s} {v}")
