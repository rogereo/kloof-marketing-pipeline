"""One proactive test per build step. Run with: pytest -q"""
import csv
import glob
import gzip
import hashlib
import json
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from sim.cli import run
from sim.core import daterange
from sim.emitters.ads import fx_rate
from sim.core import load_config

ROOT = Path(__file__).resolve().parents[1]
# window covers the campaign rename (1 Jul), schema change (1 Sep) and value bug (8-10 Sep)
START, END = date(2026, 6, 25), date(2026, 9, 10)


@pytest.fixture(scope="session")
def cfg_path(tmp_path_factory):
    cfg = yaml.safe_load(open(ROOT / "config.yaml"))
    cfg["start_date"] = START.isoformat()
    cfg["traffic_scale"] = 0.4
    path = tmp_path_factory.mktemp("cfg") / "config.yaml"
    path.write_text(yaml.safe_dump(cfg))
    return path


def backfill(cfg_path, out, end=END):
    return run(str(cfg_path), str(out), end, list(daterange(START, end)), str(out / "cache"), offline=True)


@pytest.fixture(scope="session")
def world(cfg_path, tmp_path_factory):
    out = tmp_path_factory.mktemp("run")
    backfill(cfg_path, out)
    return out


def rows(pattern):
    return [r for f in sorted(glob.glob(str(pattern))) for r in csv.DictReader(open(f))]


def json_lines(path):
    """Parse JSON lines, skipping broken ones (DQ05), the way silver has to."""
    for line in open(path):
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def manifest(code=None):
    return lambda world: [r for r in rows(world / "truth/dq_manifest/*/manifest.csv")
                          if code is None or r["issue_code"] == code]


def ga4_events(world):
    for f in sorted(glob.glob(str(world / "landing/ga4/*/events.ndjson.gz"))):
        for line in gzip.open(f, "rt"):
            yield f.split("dt=")[1][:10], json.loads(line)


def param(e, key):
    for p in e["event_params"]:
        if p["key"] == key:
            return next(v for v in p["value"].values() if v is not None)
    return None


def tree_hash(folder: Path) -> dict:
    return {str(p.relative_to(folder)): hashlib.md5(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


# Step 0: same seed, same bytes
def test_reruns_are_identical(cfg_path, world, tmp_path):
    backfill(cfg_path, tmp_path)
    assert tree_hash(world / "landing") == tree_hash(tmp_path / "landing")


# Step 9: a daily run produces exactly what the backfill produced for that day
def test_daily_matches_backfill(cfg_path, world, tmp_path):
    day = END
    run(str(cfg_path), str(tmp_path), day, [day], str(tmp_path / "cache"), offline=True)
    a = {k: v for k, v in tree_hash(world / "landing").items() if f"dt={day}" in k}
    b = tree_hash(tmp_path / "landing")
    assert a == b


# Step 1: every ad belongs to a known campaign, hidden attributes are filled in
def test_ads_have_campaigns_and_attributes(world):
    keys = {c["key"] for c in yaml.safe_load(open(ROOT / "config.yaml"))["campaigns"]}
    ads = rows(world / "truth/ads.csv")
    assert ads and all(a["campaign_key"] in keys for a in ads)
    assert all(a["tone"] and a["cta"] and a["product"] for a in ads)


# Step 2: every customer has a hidden type, and each type shows up
def test_value_types_present(world):
    types = Counter(p["value_type"] for p in rows(world / "truth/people.csv"))
    assert set(types) == {"vip", "steady", "one_and_done"}


# Step 3: weather has no gaps, and each file carries a 7-day window
def test_weather_complete(world):
    w = rows(world / "truth/weather.csv")
    assert len(w) == 3 * len(list(daterange(START, END)))
    payload = json.loads((world / f"landing/weather/dt={END}/cape_town.json").read_text())
    assert len(payload["daily"]["time"]) == 7 and "city" not in payload


# Step 4: vip customers buy more often than one-time buyers
def test_vip_orders_more(world):
    people = rows(world / "truth/people.csv")
    def avg(t):
        v = [int(p["orders_to_date"]) for p in people if p["value_type"] == t]
        return sum(v) / len(v)
    assert avg("vip") > avg("one_and_done")


# Step 5: emitted spend reconciles to truth; Meta claims more than it truly drove
def test_spend_reconciles(world, cfg_path):
    cfg = load_config(cfg_path)
    truth = sum(float(r["spend_zar"]) for r in rows(world / "truth/spend/*/spend.csv"))
    google = sum(int(r["metrics_cost_micros"]) / 1e6 for r in rows(world / "landing/google_ads/*/ad_performance.csv"))
    latest = {}  # the silver rule: keep the latest valid pull per ad-day
    for f in sorted(glob.glob(str(world / "landing/meta_ads/*/insights.jsonl"))):
        for r in json_lines(f):
            latest[(r["ad_id"], r["date_start"])] = r
    meta = sum(float(r["spend"]) * fx_rate(cfg, date.fromisoformat(r["date_start"])) for r in latest.values())
    assert abs((google + meta) - truth) < 0.005 * truth


def test_meta_overclaims(world):
    claims = [c for c in rows(world / "truth/claims/*/claims.csv") if c["platform"] == "meta"]
    real = [o for o in rows(world / "truth/orders/*/orders.csv") if o["channel"] == "paid_meta"]
    assert len(claims) > len(real)


def test_google_schema_change(world):
    before = open(world / "landing/google_ads/dt=2026-08-31/ad_performance.csv").readline()
    after = open(world / "landing/google_ads/dt=2026-09-01/ad_performance.csv").readline()
    assert "metrics_all_conversions" not in before and "metrics_all_conversions" in after


# Step 6: GA4 purchases match truth, apart from the injected mess
def test_ga4_purchases(world):
    orders = {o["order_id"]: o for o in rows(world / "truth/orders/*/orders.csv")}
    ids = Counter(e["ecommerce"]["transaction_id"] for _, e in ga4_events(world) if e["event_name"] == "purchase")
    tests = {r["record_key"] for r in manifest("DQ07")(world) if r["source"] == "ga4"}
    resent = {r["record_key"] for r in manifest("DQ02")(world) if "re-sent" in r["detail"]}
    fired = {k for k, o in orders.items() if o["ga4_purchase_fired"] == "True"}
    dup = {k for k, o in orders.items() if o["ga4_purchase_duplicated"] == "True"}
    recent = {k for k, o in orders.items() if o["order_ts"][:10] >= str(END - timedelta(days=1))}
    assert set(ids) <= fired | tests
    assert (fired | tests) - set(ids) <= recent          # only the last days can still be in transit
    multi = {k for k, n in ids.items() if n >= 2}
    assert multi <= dup | resent
    assert dup - recent <= multi


def test_click_id_only_on_landing(world):
    f = next(iter(glob.glob(str(world / "landing/ga4/*/events.ndjson.gz"))))
    for line in gzip.open(f, "rt"):
        e = json.loads(line)
        page = next(p["value"]["string_value"] for p in e["event_params"] if p["key"] == "page_location")
        if e["event_name"] not in ("session_start", "page_view"):
            assert "gclid" not in page and "fbclid" not in page


# Step 7: email plus phone matching resolves CRM ids back to real people (DQ12 needs the phone)
def phone_e164(raw):
    digits = re.sub(r"\D", "", raw)
    return "+" + digits if digits.startswith("27") else "+27" + digits[1:]


def test_crm_identity_resolution(world):
    customers = [c for c in rows(world / "landing/crm/*/customers.csv") if "kloofoutdoor" not in c["email"]]
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for c in customers:
        email = c["email"].strip().lower()
        nodes = ([f"e:{email}"] if email else []) + [f"p:{phone_e164(c['phone'])}"]
        for n in nodes[1:]:
            parent[find(n)] = find(nodes[0])
    components = {find(f"p:{phone_e164(c['phone'])}") for c in customers}
    exported = {c["customer_id"] for c in customers}
    people = [p for p in rows(world / "truth/people.csv")
              if exported & set(p["crm_customer_ids"].split("|"))]
    assert len(components) == len(people) < len(customers)
    email_only = {c["email"].strip().lower() or c["customer_id"] for c in customers}
    assert len(email_only) > len(people)                   # email alone is not enough


# Step 8: one creative folder per ad launched in the window
def test_creatives(world):
    launched = [a for a in rows(world / "truth/ads.csv")
                if START <= date.fromisoformat(a["launch_date"]) <= END]
    folders = glob.glob(str(world / "landing/creatives/*/ad_*"))
    assert len(folders) == len(launched)
    assert all((Path(f) / "copy.txt").exists() and (Path(f) / "banner.png").exists() for f in folders)


# Step 9: each Meta pull re-sends the trailing 7 days
def test_meta_trailing_window(world):
    f = world / f"landing/meta_ads/dt={END}/insights.jsonl"
    days = {r["date_start"] for r in json_lines(f)}
    assert len(days) == 7 and max(days) == END.isoformat()


# ---------- planted data quality issues: the manifest must describe the files exactly ----------
def test_manifest_has_all_issue_codes(world):
    assert {r["issue_code"] for r in manifest()(world)} == {f"DQ{i:02d}" for i in range(1, 13)}


def test_dq01_duplicate_exports(world):
    flagged = {r["file_dt"] for r in manifest("DQ01")(world)}
    for f in glob.glob(str(world / "landing/crm/*/orders.csv")):
        day = f.split("dt=")[1][:10]
        keys = Counter((r["order_id"], r["status"]) for r in rows(f))
        assert (max(keys.values(), default=1) > 1) == (day in flagged)


def test_dq03_refunds_follow_a_sale(world):
    seen = set()
    for f in sorted(glob.glob(str(world / "landing/crm/*/orders.csv"))):
        batch = rows(f)
        seen |= {r["order_id"] for r in batch if r["status"] == "completed"}
        refunds = [r for r in batch if r["status"] == "refunded"]
        assert all(r["order_id"] in seen and r["updated_at"] > r["order_ts"] for r in refunds)
    assert len({r["record_key"] for r in manifest("DQ03")(world)}) > 0


def test_dq04_orders_arrive_before_their_customer(world):
    first_seen = {}
    for f in sorted(glob.glob(str(world / "landing/crm/*/customers.csv"))):
        for r in rows(f):
            first_seen[r["customer_id"]] = f.split("dt=")[1][:10]
    late = {r["record_key"] for r in manifest("DQ04")(world)}
    orders = rows(world / "landing/crm/*/orders.csv")
    orphans = {o["customer_id"] for o in orders if o["customer_id"] in late
               and o["order_ts"][:10] < first_seen[o["customer_id"]]}
    assert orphans and orphans <= late


def test_dq05_truncated_lines_match_manifest(world):
    bad = Counter()
    for f in glob.glob(str(world / "landing/meta_ads/*/insights.jsonl")):
        for line in open(f):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                bad[f.split("dt=")[1][:10]] += 1
    assert bad == Counter(r["file_dt"] for r in manifest("DQ05")(world))


def test_dq06_value_bug(world):
    crm = {o["order_id"]: float(o["revenue"]) for o in rows(world / "truth/orders/*/orders.csv")}
    flagged = {r["record_key"] for r in manifest("DQ06")(world)}
    for _, e in ga4_events(world):
        if e["event_name"] == "purchase" and e["ecommerce"]["transaction_id"] in crm:
            tid = e["ecommerce"]["transaction_id"]
            expected = crm[tid] * (100 if tid in flagged else 1)
            assert abs(e["ecommerce"]["purchase_revenue"] - expected) < 0.01


def test_dq07_and_dq08_internal_traffic(world):
    internal = {(e["user_pseudo_id"], param(e, "ga_session_id"))
                for _, e in ga4_events(world) if param(e, "traffic_type") == "internal"}
    expected = sum(int(r["record_key"].split()[0]) for r in manifest("DQ08")(world))
    assert len(internal) == expected
    test_orders = [o for o in rows(world / "landing/crm/*/orders.csv") if o["revenue"] == "1.00"]
    assert {o["order_id"] for o in test_orders} == {r["record_key"] for r in manifest("DQ07")(world)
                                                   if r["source"] == "crm" and r["record_key"].startswith("KL-")}


def test_dq09_city_variants(world):
    cities = Counter(c["city"] for c in rows(world / "landing/crm/*/customers.csv"))
    assert len(cities) > 3 and {"Cape Town", "Johannesburg", "Durban"} <= set(cities)


def test_dq10_campaign_rename(world):
    names = {r["campaign_name"] for r in rows(world / "landing/google_ads/*/ad_performance.csv")
             if r["campaign_id"] == "21873002"}
    assert names == {"ZA_Shopping_AllProducts", "ZA_PMax_AllProducts"}


def test_dq11_fx_weekends_empty(world):
    for f in glob.glob(str(world / "landing/fx_rates/*/usd_zar.csv")):
        day = date.fromisoformat(f.split("dt=")[1][:10])
        assert (len(rows(f)) == 0) == (day.weekday() >= 5)


# ---------- data contracts: files must fit the BigQuery schemas in schemas/ ----------
TYPES = {"STRING": (str,), "INTEGER": (int,), "FLOAT": (float, int), "RECORD": (dict,)}


def conforms(value, field):
    if value is None:
        return field["mode"] != "REQUIRED"
    if field["mode"] == "REPEATED":
        return isinstance(value, list) and all(conforms(v, dict(field, mode="NULLABLE")) for v in value)
    if not isinstance(value, TYPES[field["type"]]) or isinstance(value, bool):
        return False
    if field["type"] == "RECORD":
        names = {f["name"]: f for f in field["fields"]}
        return set(value) <= set(names) and all(conforms(v, names[k]) for k, v in value.items())
    return True


def test_ga4_matches_schema(world):
    schema = {"name": "root", "type": "RECORD", "mode": "NULLABLE",
              "fields": json.load(open(ROOT / "schemas/ga4_events.json"))}
    for i, (_, e) in enumerate(ga4_events(world)):
        assert conforms(e, schema), e
        if i > 20000:
            break


def test_weather_matches_schema(world):
    schema = {"name": "root", "type": "RECORD", "mode": "NULLABLE",
              "fields": json.load(open(ROOT / "schemas/weather_daily.json"))}
    for f in glob.glob(str(world / "landing/weather/*/*.json")):
        assert conforms(json.load(open(f)), schema)


def test_csv_headers_match_schemas(world):
    pairs = {"crm/*/customers.csv": "crm_customers", "crm/*/orders.csv": "crm_orders",
             "crm/*/order_items.csv": "crm_order_items", "fx_rates/*/usd_zar.csv": "fx_rates",
             "google_ads/*/click_view.csv": "google_click_view"}
    for pattern, name in pairs.items():
        expected = [c["name"] for c in json.load(open(ROOT / f"schemas/{name}.json"))]
        for f in glob.glob(str(world / "landing" / pattern)):
            assert open(f).readline().strip().split(",") == expected
