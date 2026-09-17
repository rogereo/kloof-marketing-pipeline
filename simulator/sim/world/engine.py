"""Steps 2 and 4: customers and the daily journey loop.

The engine always simulates from start_date forward, so any given day comes out identical
whether you run a full backfill or a single daily run. Heavy per-session detail is only
kept for the days being written out.
"""
from __future__ import annotations

import string
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from sim.core import SAST, daterange, e164, seeded, weighted
from sim.models import Claim, CrmCustomer, Order, Person, Session, SpendRow
from sim.world.campaigns import build_campaigns
from sim.world.weather import WeatherStore, weather_boost

FIRST_NAMES = ["Thandi", "Sipho", "Aisha", "Pieter", "Lerato", "Johan", "Naledi", "Ruan", "Zanele",
               "Kyle", "Ayanda", "Chloe", "Bongani", "Megan", "Themba", "Priya", "Liam", "Nomsa",
               "Ethan", "Karabo", "Fatima", "Dylan", "Palesa", "Jade"]
LAST_NAMES = ["Mokoena", "Naidoo", "van der Merwe", "Dlamini", "Botha", "Khumalo", "Pillay",
              "Smith", "Nkosi", "Pretorius", "Ndlovu", "Jacobs", "Mahlangu", "Fourie", "Govender"]
HOURS = list(range(6, 24))
HOUR_WEIGHTS = [1, 2, 3, 3, 3, 3, 4, 4, 3, 3, 4, 5, 6, 7, 7, 6, 4, 2]
DEVICES = {"mobile": 0.68, "desktop": 0.27, "tablet": 0.05}
META_LAG = {0: 55, 1: 15, 2: 10, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2}
SITE = "https://kloof.co.za"


class Engine:
    def __init__(self, cfg: dict, weather: WeatherStore):
        self.cfg = cfg
        self.mess = cfg["mess"]
        self.weather = weather
        self.start: date = cfg["start_date"]
        self.scale = cfg["traffic_scale"]
        self.campaigns = build_campaigns(cfg)
        self.ads = {a.ad_id: a for c in self.campaigns for a in c.ads}
        self.city_names = [c["name"] for c in cfg["cities"]]
        self.city_shares = {c["name"]: c["share"] for c in cfg["cities"]}
        self.catalog = cfg["catalog"]

        self.people: dict[str, Person] = {}
        self.people_by_city: dict[str, list[Person]] = defaultdict(list)
        self.pending_registrations: dict[date, list[str]] = defaultdict(list)
        self.orders: list[Order] = []
        self.claims: list[Claim] = []
        self.spend: list[SpendRow] = []
        self.crm_customers: list[CrmCustomer] = []
        self.sessions_by_day: dict[date, list[Session]] = {}
        self.test_orders: list[Order] = []          # DQ07, kept out of the truth orders
        self.dq = cfg["dq"]
        self.qa_customer: CrmCustomer | None = None
        self._seq = {"order": 100000, "crm": 0, "person": 0}

    # ================= main loop =================
    def run(self, end: date, keep_days: set[date]) -> None:
        # GA4 files for day D also carry late events from D-1 and D-2 (DQ02), so keep those sessions too
        keep = set(keep_days) | {k - timedelta(days=n) for k in keep_days for n in (1, 2)}
        for d in daterange(self.start, end):
            self._simulate_day(d, d in keep)

    def _simulate_day(self, d: date, keep: bool) -> None:
        rng = seeded(self.cfg["seed"], "day", d)
        sessions: list[Session] = []
        wx = {city: self.weather.get(city, d) for city in self.city_names}

        for pid in self.pending_registrations.pop(d, []):
            self._register(self.people[pid], d, rng)

        # paid media
        for camp in self.campaigns:
            live = [a for a in camp.ads if a.launch_date <= d]
            if not live:
                continue
            total = camp.budget * self.scale * rng.uniform(0.9, 1.05)
            wsum = sum(a.weight for a in live)
            for ad in live:
                ad_spend = round(total * ad.weight / wsum, 2)
                clicks = int(round(ad_spend / (camp.cpc * rng.uniform(0.85, 1.15))))
                impressions = int(clicks / (camp.ctr * ad.quality) * rng.uniform(0.9, 1.1))
                self.spend.append(SpendRow(d, camp.platform, camp.key, ad.ad_id, ad_spend, clicks, impressions))
                for _ in range(clicks):
                    self._paid_click(d, camp, ad, rng, wx, sessions)

        # organic and direct first visits
        org = self.cfg["organic"]
        for _ in range(int(org["sessions_per_day"] * self.scale * rng.uniform(0.85, 1.15))):
            self._organic_visit(d, rng, sessions)

        # existing customers coming back
        for person in list(self.people.values()):
            if person.acq_date < d:
                hazard = self.cfg["value_types"][person.value_type]["daily_repeat_hazard"]
                if rng.random() < hazard:
                    self._repeat_visit(d, person, rng, sessions)

        self._staff_activity(d, sessions)

        if keep:
            self.sessions_by_day[d] = sessions

    # ================= DQ07 / DQ08: staff and QA activity =================
    def _staff_activity(self, d, sessions):
        rng = seeded(self.cfg["seed"], "dq-staff", d)
        if self.qa_customer is None:
            ts = datetime.combine(self.start, time(8, 5), SAST)
            self._seq["crm"] += 1
            self.qa_customer = CrmCustomer(
                crm_id=f"C-{self._seq['crm']:06d}", pid="QA", email="qa.team@kloofoutdoor.co.za",
                first_name="QA", last_name="Test", phone="021 555 0100", city="Cape Town",
                created_at=ts, is_guest=False, marketing_opt_in=False, export_date=self.start)
            self.crm_customers.append(self.qa_customer)
        if d.weekday() >= 5:
            return
        staff_ids = [f"{900000001 + i}.1773900000" for i in range(5)]
        for _ in range(self.dq["DQ08_internal_sessions_per_weekday"]):
            ts = datetime.combine(d, time(rng.randint(8, 16), rng.randint(0, 59), rng.randint(0, 59)), SAST)
            sessions.append(self._staff_session(d, ts, rng.choice(staff_ids), rng, sessions))
        if rng.random() < self.dq["DQ07_test_orders_per_week"] / 5:
            ts = datetime.combine(d, time(rng.randint(9, 15), rng.randint(0, 59), 0), SAST)
            session = self._staff_session(d, ts, staff_ids[0], rng, sessions)
            sku = self.catalog[-1]
            self._seq["order"] += 1
            order = Order(
                order_id=f"KL-{self._seq['order']}", pid="QA", crm_id=self.qa_customer.crm_id,
                ts=ts + timedelta(minutes=4), items=[(sku["id"], sku["name"], float(sku["price"]), 1)],
                subtotal=float(sku["price"]), discount=float(sku["price"]) - 1.0, revenue=1.0,
                status="completed", is_first=False, channel="direct", campaign_key=None, ad_id=None,
                ga4_fired=True, ga4_duplicated=False, is_test=True)
            session.order = order
            sessions.append(session)
            self.test_orders.append(order)

    def _staff_session(self, d, ts, pseudo, rng, sessions) -> Session:
        return Session(
            session_key=f"{d.isoformat()}-{len(sessions):06d}", ga_session_id=int(ts.timestamp()),
            session_number=rng.randint(20, 400), pseudo_id=pseudo, start=ts, city="Cape Town",
            device="desktop", landing_url=SITE + "/", collected_traffic_source=None, referrer=None,
            depth=rng.choice([1, 2]), internal=True)

    # ================= visit types =================
    def _paid_click(self, d, camp, ad, rng, wx, sessions):
        city = weighted(rng, self.city_shares)
        ts = self._session_time(d, rng)
        existing = None
        if self.people_by_city[city] and rng.random() < camp.existing_click_share:
            existing = rng.choice(self.people_by_city[city])
        click_id = self._click_id(camp.platform, rng)
        cvr = camp.cvr * ad.quality * (1 + camp.weather_sensitivity * weather_boost(wx[city]))
        if existing:
            cvr *= 1.5
        converts = rng.random() < cvr
        missing_click = rng.random() < self.mess["missing_click_id_rate"]
        missing_utm = missing_click and rng.random() < self.mess["missing_utm_given_missing_click_rate"]
        landing, cts = self._paid_landing(d, camp, ad, click_id, missing_click, missing_utm, rng)

        person = existing
        if converts and person is None:
            mix = self._discount_shift(camp.value_mix, ad.discount_pct)
            person = self._new_person(d, ts, city, mix, rng, f"paid_{camp.platform}", camp.key, ad.ad_id)
        if person is not None:
            person.last_click[camp.platform] = (d, ad.ad_id)

        session = self._session(d, ts, city, person, rng, landing, cts, None, sessions)
        session.click = {"platform": camp.platform, "click_id": click_id, "ad_id": ad.ad_id,
                         "campaign_key": camp.key, "url_has_click_id": not missing_click}
        if converts:
            order = self._place_order(d, ts, person, rng, f"paid_{camp.platform}", camp.key, ad.ad_id,
                                      ad.discount_pct)
            session.order = order
            self._claims_for(d, order, person, rng, paid=(camp.platform, ad.ad_id))

    def _organic_visit(self, d, rng, sessions):
        org = self.cfg["organic"]
        city = weighted(rng, self.city_shares)
        ts = self._session_time(d, rng)
        source = weighted(rng, org["source_mix"])
        converts = rng.random() < org["conversion_rate"]
        referrer = "https://www.google.com/" if source == "organic" else None
        landing = SITE + rng.choice(["/", "/collections/jackets", "/blog/best-hikes-cape-town"])
        person = None
        if converts:
            person = self._new_person(d, ts, city, org["value_mix"], rng, source, None, None)
        session = self._session(d, ts, city, person, rng, landing, None, referrer, sessions)
        if converts:
            order = self._place_order(d, ts, person, rng, source, None, None, 0)
            session.order = order
            self._claims_for(d, order, person, rng)

    def _repeat_visit(self, d, person, rng, sessions):
        ts = self._session_time(d, rng)
        source = weighted(rng, self.cfg["repeat_source_mix"])
        cts, referrer, landing = None, None, SITE + "/"
        if source == "email":
            landing = SITE + "/?" + urlencode({"utm_source": "newsletter", "utm_medium": "email",
                                               "utm_campaign": "weekly_digest"})
            cts = {"manual_source": "newsletter", "manual_medium": "email",
                   "manual_campaign_name": "weekly_digest"}
        elif source == "organic":
            referrer = "https://www.google.com/"
        session = self._session(d, ts, person.city, person, rng, landing, cts, referrer, sessions)
        order = self._place_order(d, ts, person, rng, source, None, None, 0)
        session.order = order
        self._claims_for(d, order, person, rng)

    # ================= building blocks =================
    def _session(self, d, ts, city, person, rng, landing, cts, referrer, sessions) -> Session:
        if person is not None:
            person.session_number += 1
            pseudo, device, number = person.pseudo_id, person.device, person.session_number
        else:
            pseudo = self._pseudo_id(ts, rng)
            device, number = weighted(rng, DEVICES), 1
        session = Session(
            session_key=f"{d.isoformat()}-{len(sessions):06d}", ga_session_id=int(ts.timestamp()),
            session_number=number, pseudo_id=pseudo, start=ts, city=city, device=device,
            landing_url=landing, collected_traffic_source=cts, referrer=referrer,
            depth=rng.choices([0, 1, 2], weights=[45, 40, 15])[0],
        )
        sessions.append(session)
        return session

    def _new_person(self, d, ts, city, mix, rng, channel, campaign_key, ad_id) -> Person:
        self._seq["person"] += 1
        n = self._seq["person"]
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        local = f"{first}.{last}".lower().replace(" ", "")
        phone_digits = f"{rng.choice([60, 71, 72, 73, 76, 79, 81, 82, 83, 84])}{rng.randint(100, 999)}{rng.randint(1000, 9999)}"
        person = Person(
            pid=f"P{n:06d}", value_type=weighted(rng, mix), city=city, first_name=first, last_name=last,
            email=f"{local}{n}@example.com", phone_digits=phone_digits, pseudo_id=self._pseudo_id(ts, rng),
            device=weighted(rng, DEVICES), acq_date=d, acq_channel=channel,
            acq_campaign=campaign_key, acq_ad=ad_id,
        )
        guest_dup = rng.random() < self.mess["guest_duplicate_customer_rate"]
        is_guest = guest_dup or rng.random() < 0.25
        email = person.email
        if guest_dup:  # guests type their email by hand: odd casing and stray spaces
            email = f"  {first}.{last.replace(' ', '')}{n}@Example.com "
            if seeded("dq12", person.pid).random() < self.dq["DQ12_blank_guest_email_rate"]:
                email = ""  # DQ12: optional field left empty; only the phone can link this record
            self.pending_registrations[d + timedelta(days=rng.randint(1, 20))].append(person.pid)
        p = phone_digits
        phone = f"+27 {p[:2]} {p[2:5]} {p[5:]}"
        created = ts - timedelta(seconds=30)
        late = seeded("dq04", person.pid).random() < self.dq["DQ04_late_customer_record_rate"]
        export_date = created.date() + timedelta(days=1 if late else 0)  # DQ04
        self._add_crm(person, email, phone, created, is_guest, rng, export_date)
        self.people[person.pid] = person
        self.people_by_city[city].append(person)
        return person

    def _register(self, person: Person, d: date, rng) -> None:
        """A guest comes back and creates a proper account: a second CRM id for the same human."""
        ts = datetime.combine(d, time(rng.randint(7, 22), rng.randint(0, 59), rng.randint(0, 59)), SAST)
        p = person.phone_digits  # same number, local format this time
        self._add_crm(person, person.email, f"0{p[:2]} {p[2:5]} {p[5:]}", ts, False, rng, d)

    def _add_crm(self, person, email, phone, ts, is_guest, rng, export_date) -> None:
        self._seq["crm"] += 1
        crm_id = f"C-{self._seq['crm']:06d}"
        person.crm_ids.append(crm_id)
        person.active_crm_id = crm_id
        self.crm_customers.append(CrmCustomer(
            crm_id=crm_id, pid=person.pid, email=email, first_name=person.first_name,
            last_name=person.last_name, phone=phone, city=person.city, created_at=ts,
            is_guest=is_guest, marketing_opt_in=rng.random() < 0.6, export_date=export_date))

    def _place_order(self, d, ts, person, rng, channel, campaign_key, ad_id, discount_pct) -> Order:
        vt = self.cfg["value_types"][person.value_type]
        n_items = rng.choices([x[0] for x in vt["items"]], weights=[x[1] for x in vt["items"]])[0]
        picks = rng.sample(self.catalog, n_items)
        items = [(p["id"], p["name"], float(p["price"]), 1) for p in picks]
        subtotal = sum(i[2] for i in items)
        discount = round(subtotal * discount_pct / 100, 2)
        self._seq["order"] += 1
        person.n_orders += 1
        drop = rng.random() < self.mess["ga4_purchase_drop_rate"]
        dup = (not drop) and rng.random() < self.mess["ga4_duplicate_purchase_rate"]
        order = Order(
            order_id=f"KL-{self._seq['order']}", pid=person.pid, crm_id=person.active_crm_id,
            ts=ts + timedelta(seconds=rng.randint(180, 900)), items=items, subtotal=subtotal,
            discount=discount, revenue=round(subtotal - discount, 2),
            status="refunded" if rng.random() < self.mess["refund_rate"] else "completed",
            is_first=person.n_orders == 1, channel=channel, campaign_key=campaign_key, ad_id=ad_id,
            ga4_fired=not drop, ga4_duplicated=dup,
        )
        if order.status == "refunded":  # DQ03: the refund shows up as an update days later
            r = seeded("dq03", order.order_id)
            lo, hi = self.dq["DQ03_refund_delay_days"]
            order.refunded_at = order.ts + timedelta(days=r.randint(lo, hi), minutes=r.randint(0, 600))
        self.orders.append(order)
        return order

    def _claims_for(self, d, order, person, rng, paid=None) -> None:
        """Decide which ad platforms take credit for this order (often more than one)."""
        claimed = set()
        if paid:
            platform, ad_id = paid
            self._claim(d, platform, ad_id, order, rng, "click")
            claimed.add(platform)
        for platform in sorted(person.last_click):
            if platform in claimed:
                continue
            click_day, ad_id = person.last_click[platform]
            window = self.mess["post_click_window_days"][platform]
            if (d - click_day).days <= window and rng.random() < self.mess["post_click_claim_rate"][platform]:
                self._claim(d, platform, ad_id, order, rng, "post_click")
                claimed.add(platform)
        if "meta" not in claimed and rng.random() < self.mess["meta_view_through_rate"]:
            # bigger budgets buy more impressions, so they collect more view-through credit
            live = [(a, c.budget * a.weight) for c in self.campaigns if c.platform == "meta"
                    for a in c.ads if a.launch_date <= d]
            if live:
                ad = rng.choices([a for a, _ in live], weights=[w for _, w in live])[0]
                self._claim(d, "meta", ad.ad_id, order, rng, "view_through")

    def _claim(self, d, platform, ad_id, order, rng, claim_type) -> None:
        lag = 0
        if platform == "meta":
            lag = min(rng.choices(list(META_LAG), weights=list(META_LAG.values()))[0],
                      self.mess["meta_restatement_days"])
        self.claims.append(Claim(d, platform, ad_id, order.order_id, order.revenue, lag, claim_type))

    # ================= small helpers =================
    @staticmethod
    def _discount_shift(mix: dict, discount_pct: int) -> dict:
        """Deep discounts pull in more one-time bargain hunters."""
        shift = discount_pct / 300
        out = dict(mix)
        taken = min(shift, out["vip"] + out["steady"])
        total = out["vip"] + out["steady"]
        if total:
            out["vip"] -= taken * mix["vip"] / total
            out["steady"] -= taken * mix["steady"] / total
        out["one_and_done"] += taken
        return out

    def _paid_landing(self, d, camp, ad, click_id, missing_click, missing_utm, rng):
        path = rng.choice(["/", "/collections/jackets", "/collections/boots", "/sale"])
        params, cts = {}, {}
        if not missing_utm:
            if camp.platform == "google":
                params.update(utm_source="google", utm_medium="cpc", utm_campaign=camp.name_on(d))
            else:
                params.update(utm_source="facebook", utm_medium="paid_social",
                              utm_campaign=camp.utm_campaign, utm_content=ad.ad_id)
            cts.update(manual_source=params["utm_source"], manual_medium=params["utm_medium"],
                       manual_campaign_name=params["utm_campaign"])
            if "utm_content" in params:
                cts["manual_content"] = params["utm_content"]
        if not missing_click:
            key = "gclid" if camp.platform == "google" else "fbclid"
            params[key] = click_id
            if camp.platform == "google":
                cts["gclid"] = click_id
        url = SITE + path + ("?" + urlencode(params) if params else "")
        return url, (cts or None)

    @staticmethod
    def _click_id(platform, rng) -> str:
        alphabet = string.ascii_letters + string.digits + "-_"
        if platform == "google":
            return "Cj0KCQjw" + "".join(rng.choice(alphabet) for _ in range(24))
        return "IwAR" + "".join(rng.choice(alphabet) for _ in range(40))

    @staticmethod
    def _pseudo_id(ts, rng) -> str:
        return f"{rng.randint(10**8, 10**9 - 1)}.{int(ts.timestamp())}"

    @staticmethod
    def _session_time(d, rng) -> datetime:
        hour = rng.choices(HOURS, weights=HOUR_WEIGHTS)[0]
        minute_cap = 29 if hour == 23 else 59
        return datetime.combine(d, time(hour, rng.randint(0, minute_cap), rng.randint(0, 59)), SAST)
