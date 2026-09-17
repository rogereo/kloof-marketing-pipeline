"""Step 1: campaigns and ads, each ad with hidden creative attributes."""
from __future__ import annotations

from datetime import timedelta

from sim.core import seeded, slugify
from sim.models import Ad, Campaign

TONES = ["urgent", "informative", "aspirational", "playful"]
CTAS = {"shop_now": "Shop now", "learn_more": "Learn more", "get_offer": "Claim the offer", "sign_up": "Join the club"}
PRODUCT_USE = {
    "Drakensberg shell jacket": ("mountain weather", "fully taped seams"),
    "Cederberg hiking boots": ("rocky trails", "grippy Vibram soles"),
    "Karoo fleece": ("cold desert nights", "recycled warm fibre"),
    "Tsitsikamma rain pants": ("forest downpours", "stretch waterproof fabric"),
    "Table Mountain daypack": ("day hikes", "a padded laptop sleeve"),
}


def make_copy(tone: str, discount: int, cta: str, product: str) -> tuple[str, str]:
    use, feature = PRODUCT_USE[product]
    cta_text = CTAS[cta]
    if tone == "urgent":
        headline = f"{discount}% off, ends Sunday" if discount else "Last chance this week"
        body = (f"Winter won't wait. Our {product} is {discount}% off until Sunday. {cta_text}."
                if discount else f"Winter won't wait. Get the {product} before the cold front. {cta_text}.")
    elif tone == "informative":
        headline = f"Built for {use}"
        body = f"Our {product} is made for {use}, with {feature}. {cta_text}."
    elif tone == "aspirational":
        headline = "Some trails change you"
        body = f"Some trails change you. Find yours with the {product}. {cta_text}."
    else:
        headline = "Rain? Bring it."
        body = f"Rain? Bring it. The {product} laughs at puddles. {cta_text}."
    if discount and tone != "urgent":
        body += f" Now {discount}% off."
    return headline, body


def _ids(platform: str, ci: int, ai: int, group: int) -> tuple[str, str, str]:
    """Return (campaign_id, group_id, ad_id) shaped like each platform's real IDs."""
    if platform == "google":
        return f"2187300{ci}", f"14500{ci}{group}", f"69881{ci}{ai:04d}"
    return f"120210{ci:02d}0000000000", f"120210{ci:02d}1{group:09d}", f"120210{ci:02d}{ai:010d}"


def build_campaigns(cfg: dict) -> list[Campaign]:
    rng = seeded(cfg["seed"], "campaigns")
    start = cfg["start_date"]
    products = list(PRODUCT_USE)
    campaigns = []
    for ci, c in enumerate(cfg["campaigns"], start=1):
        camp_id, _, _ = _ids(c["platform"], ci, 0, 0)
        camp = Campaign(
            key=c["key"], platform_id=camp_id, name=c["name"], platform=c["platform"],
            budget=c["daily_budget_zar"], cpc=c["cpc_zar"], ctr=c["ctr"], cvr=c["cvr"],
            weather_sensitivity=c["weather_sensitivity"], existing_click_share=c["existing_click_share"],
            value_mix=c["value_mix"], utm_campaign=slugify(c["name"]),
        )
        rename = cfg["dq"]["DQ10_campaign_rename"]
        if rename["campaign"] == c["key"]:
            camp.renamed_on, camp.new_name = rename["date"], rename["new_name"]
        specs = []
        for ai in range(1, c["n_ads"] + 1):
            specs.append(dict(
                tone=rng.choice(TONES), discount_pct=rng.choice(c["discounts"]),
                cta=rng.choice(list(CTAS)), product=rng.choice(products),
                launch_date=start + timedelta(days=0 if ai <= 2 else rng.randint(0, 200)),
                quality=round(rng.uniform(0.8, 1.2), 3), weight=round(rng.uniform(0.5, 1.5), 3),
            ))
        for extra in cfg.get("scheduled_ads", []):
            if extra["campaign"] == c["key"]:
                specs.append(dict(extra, quality=1.0, weight=1.2))
        for ai, spec in enumerate(specs, start=1):
            group = (ai - 1) % 2 + 1
            _, group_id, ad_id = _ids(c["platform"], ci, ai, group)
            headline, body = make_copy(spec["tone"], spec["discount_pct"], spec["cta"], spec["product"])
            camp.ads.append(Ad(
                ad_id=ad_id, campaign_key=c["key"], platform=c["platform"], group_id=group_id,
                group_name=f"{c['name']} | Group {group}",
                name=f"{spec['product']} | {spec['tone']} | v{ai}",
                tone=spec["tone"], discount_pct=spec["discount_pct"], cta=spec["cta"],
                product=spec["product"], quality=spec["quality"], weight=spec["weight"],
                launch_date=spec["launch_date"], headline=headline, copy=body,
            ))
        campaigns.append(camp)
    return campaigns
