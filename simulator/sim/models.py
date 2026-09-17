"""The nouns of the simulated world."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Ad:
    ad_id: str
    campaign_key: str
    platform: str            # google | meta
    group_id: str            # Google ad group or Meta ad set
    group_name: str
    name: str
    tone: str                # hidden truth: urgent | informative | aspirational | playful
    discount_pct: int        # hidden truth
    cta: str                 # hidden truth
    product: str
    quality: float
    weight: float
    launch_date: date
    headline: str
    copy: str


@dataclass
class Campaign:
    key: str
    platform_id: str
    name: str
    platform: str
    budget: float
    cpc: float
    ctr: float
    cvr: float
    weather_sensitivity: float
    existing_click_share: float
    value_mix: dict
    utm_campaign: str
    ads: list = field(default_factory=list)
    renamed_on: date | None = None
    new_name: str | None = None

    def name_on(self, d: date) -> str:
        """DQ10: a campaign can be renamed while keeping its ID."""
        return self.new_name if self.renamed_on and d >= self.renamed_on else self.name


@dataclass
class Person:
    pid: str
    value_type: str          # hidden truth: vip | steady | one_and_done
    city: str
    first_name: str
    last_name: str
    email: str               # clean version; CRM may store a messy one
    phone_digits: str        # 9 digits after the leading 0, formatted differently per system
    pseudo_id: str           # GA4 cookie id
    device: str
    acq_date: date
    acq_channel: str
    acq_campaign: str | None
    acq_ad: str | None
    crm_ids: list = field(default_factory=list)
    active_crm_id: str = ""
    last_click: dict = field(default_factory=dict)   # platform -> (date, ad_id)
    session_number: int = 0
    n_orders: int = 0


@dataclass
class Order:
    order_id: str
    pid: str
    crm_id: str
    ts: datetime
    items: list              # list of (sku, name, price, qty)
    subtotal: float
    discount: float
    revenue: float
    status: str
    is_first: bool
    channel: str             # paid_google | paid_meta | organic | direct | email
    campaign_key: str | None
    ad_id: str | None
    ga4_fired: bool
    ga4_duplicated: bool
    refunded_at: datetime | None = None   # DQ03: refunds arrive as a later update
    is_test: bool = False                 # DQ07: QA order, not a real sale


@dataclass
class Session:
    session_key: str
    ga_session_id: int
    session_number: int
    pseudo_id: str
    start: datetime
    city: str
    device: str
    landing_url: str
    collected_traffic_source: dict | None
    referrer: str | None
    depth: int
    click: dict | None = None
    order: Order | None = None
    internal: bool = False               # DQ08: staff traffic


@dataclass
class Claim:
    claim_date: date
    platform: str
    ad_id: str
    order_id: str
    revenue: float
    lag_days: int
    claim_type: str          # click | post_click | view_through


@dataclass
class SpendRow:
    day: date
    platform: str
    campaign_key: str
    ad_id: str
    spend_zar: float
    clicks: int
    impressions: int


@dataclass
class CrmCustomer:
    crm_id: str
    pid: str
    email: str
    first_name: str
    last_name: str
    phone: str
    city: str
    created_at: datetime
    is_guest: bool
    marketing_opt_in: bool
    export_date: date | None = None      # DQ04: can land a day after it was created
