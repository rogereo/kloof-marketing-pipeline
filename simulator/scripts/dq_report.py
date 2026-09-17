"""Summarise the planted data quality issues: what your silver layer should catch.

Usage: python scripts/dq_report.py output/truth
"""
import csv
import glob
import re
import sys
from collections import defaultdict
from pathlib import Path

NAMES = {
    "DQ01": "CRM orders exported twice",
    "DQ02": "GA4 events late or re-sent",
    "DQ03": "Refund arrives as later update",
    "DQ04": "Customer record a day late",
    "DQ05": "Truncated Meta JSON line",
    "DQ06": "GA4 purchase value x100",
    "DQ07": "QA test orders in production",
    "DQ08": "Internal staff traffic",
    "DQ09": "Free-text city variants",
    "DQ10": "Campaign renamed, same ID",
    "DQ11": "No FX rate on weekends",
    "DQ12": "Blank email on guest record",
}


def main(truth: Path):
    records, days, keys = defaultdict(int), defaultdict(set), defaultdict(set)
    ga4_events = 0
    for f in sorted(glob.glob(str(truth / "dq_manifest/*/manifest.csv"))):
        for r in csv.DictReader(open(f)):
            code = r["issue_code"]
            days[code].add(r["file_dt"])
            if code == "DQ02" and r["record_key"].startswith("event_date="):
                ga4_events += int(re.match(r"(\d+)", r["detail"]).group(1))
                continue
            if code == "DQ01":
                records[code] += int(re.match(r"(\d+)", r["detail"]).group(1))
            elif code == "DQ08":
                records[code] += int(r["record_key"].split()[0])
            else:
                keys[code].add(r["record_key"])  # a record can appear in two sources (e.g. DQ07)

    for code, k in keys.items():
        records[code] = len(k)
    units = {"DQ01": "duplicated rows", "DQ02": "purchase orders", "DQ03": "orders", "DQ04": "customers",
             "DQ05": "ad-days", "DQ06": "orders", "DQ07": "orders + QA acct", "DQ08": "sessions",
             "DQ09": "customers", "DQ10": "campaign", "DQ11": "days", "DQ12": "customers"}
    print(f"{'code':5s} {'issue':34s} {'records':>8s}  {'unit':16s} {'days':>5s}")
    for code, name in NAMES.items():
        print(f"{code:5s} {name:34s} {records[code]:8d}  {units.get(code, 'records'):16s} {len(days[code]):5d}")
    print(f"\nDQ02 also moved or re-sent {ga4_events:,} GA4 events of all types.")
    missing = [c for c in NAMES if not days[c]]
    print("All 12 issues present." if not missing else f"Missing in this window: {', '.join(missing)}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "output/truth"))
