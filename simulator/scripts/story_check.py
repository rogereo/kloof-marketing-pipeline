"""Print the campaign story straight from the truth store.

This is the answer key: the numbers your gold marts should get close to.
"Value ROAS" here uses each customer's TRUE type, so it is the best any model could do.
Windows match PROJECT_BRIEF.md: features from days 0-7 after the first order, label = completed
revenue in days 8-97.

Usage: python scripts/story_check.py output/truth
"""
import csv
import glob
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

FEATURE_DAYS, LABEL_DAYS = 7, 90


def read(pattern):
    return [r for f in sorted(glob.glob(pattern)) for r in csv.DictReader(open(f))]


def main(truth: Path):
    people = {p["person_id"]: p for p in read(str(truth / "people.csv"))}
    ads = {a["ad_id"]: a for a in read(str(truth / "ads.csv"))}
    orders = read(str(truth / "orders/*/orders.csv"))
    claims = read(str(truth / "claims/*/claims.csv"))
    spend = read(str(truth / "spend/*/spend.csv"))
    end = max(datetime.fromisoformat(o["order_ts"]).date() for o in orders)

    # 1. average value in days 8 to 97 after first order, per hidden type (mature cohorts only)
    future = defaultdict(float)
    for o in orders:
        p = people[o["person_id"]]
        age = (datetime.fromisoformat(o["order_ts"]).date() - date.fromisoformat(p["acquired_date"])).days
        if o["status"] == "completed" and FEATURE_DAYS < age <= FEATURE_DAYS + LABEL_DAYS:
            future[o["person_id"]] += float(o["revenue"])
    mature = [p for p in people.values() if date.fromisoformat(p["acquired_date"]) <= end - timedelta(days=FEATURE_DAYS + LABEL_DAYS)]
    by_type = defaultdict(list)
    for p in mature:
        by_type[p["value_type"]].append(future[p["person_id"]])
    avg = {k: sum(v) / len(v) for k, v in by_type.items()}
    print(f"Mature cohort (acquired on or before {end - timedelta(days=FEATURE_DAYS + LABEL_DAYS)}): {len(mature)} customers")
    for k in ("vip", "steady", "one_and_done"):
        print(f"  {k:13s} n={len(by_type[k]):5d}  avg value days 8-97: R{avg.get(k, 0):,.0f}")

    # 2. campaign scoreboard
    sp, clicks = Counter(), Counter()
    for s in spend:
        sp[s["campaign_key"]] += float(s["spend_zar"])
        clicks[s["campaign_key"]] += int(s["clicks"])
    real_rev, firsts, value, mix = Counter(), Counter(), Counter(), defaultdict(Counter)
    for o in orders:
        k = o["campaign_key"]
        if not k or o["status"] != "completed":
            continue
        real_rev[k] += float(o["revenue"])
        if o["is_first_order"] == "True":
            vt = people[o["person_id"]]["value_type"]
            firsts[k] += 1
            value[k] += float(o["revenue"]) + avg.get(vt, 0)
            mix[k][vt] += 1
    claim_n, claim_rev = Counter(), Counter()
    for c in claims:
        k = ads[c["ad_id"]]["campaign_key"]
        claim_n[k] += 1
        claim_rev[k] += float(c["revenue"])

    print(f"\n{'campaign':11s} {'spend':>10s} {'new cust':>8s} {'claims':>7s} {'platform':>9s} "
          f"{'actual':>7s} {'value':>7s} {'one-time %':>10s}")
    for k in sorted(sp):
        s = sp[k]
        share = 100 * mix[k]["one_and_done"] / max(firsts[k], 1)
        print(f"{k:11s} {s:10,.0f} {firsts[k]:8d} {claim_n[k]:7d} {claim_rev[k] / s:9.2f} "
              f"{real_rev[k] / s:7.2f} {value[k] / s:7.2f} {share:9.0f}%")
    print("\nplatform = what the ad platform reports | actual = real CRM revenue (paid clicks only)"
          "\nvalue = first-order revenue + expected value in days 8-97 of the customers acquired")
    print(f"\nTotals: {len(orders)} orders, {len(claims)} platform claims, {len(people)} people")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "output/truth"))
