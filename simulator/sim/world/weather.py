"""Step 3: daily weather per city.

Tries Open-Meteo's historical archive first, then its forecast API (which covers the last
few days the archive has not published yet), then falls back to synthetic seasonal weather.
Everything fetched is cached, so the simulated past never changes between runs.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from sim.core import daterange, seeded, yesterday_sast

DAILY_VARS = "temperature_2m_max,temperature_2m_min,precipitation_sum"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Rough climate shape per city: (mean max temp, seasonal swing, rain chance in Jul, rain chance in Jan)
CLIMATE = {
    "cape_town": (21.5, 5.0, 0.40, 0.08),
    "johannesburg": (22.0, 5.0, 0.03, 0.45),
    "durban": (25.0, 3.0, 0.12, 0.40),
}


class WeatherStore:
    def __init__(self, cfg: dict, cache_dir: str | Path, offline: bool = False):
        self.cfg = cfg
        self.cities = {c["name"]: c for c in cfg["cities"]}
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.data: dict[str, dict[str, dict]] = {}

    # ---------- public ----------
    def ensure(self, start: date, end: date) -> None:
        for name, city in self.cities.items():
            path = self.cache_dir / f"weather_{city['slug']}.json"
            cached = json.loads(path.read_text()) if path.exists() else {}
            missing = [d for d in daterange(start, end) if d.isoformat() not in cached]
            if missing and not self.offline:
                self._fill_from_api(city, missing, cached)
            for d in daterange(start, end):
                if d.isoformat() not in cached:
                    cached[d.isoformat()] = self._synthetic(city["slug"], d)
            path.write_text(json.dumps(dict(sorted(cached.items())), indent=1))
            self.data[name] = cached

    def get(self, city: str, d: date) -> dict:
        return self.data[city][d.isoformat()]

    # ---------- sources ----------
    def _fill_from_api(self, city: dict, missing: list[date], cached: dict) -> None:
        base = {"latitude": city["lat"], "longitude": city["lon"], "daily": DAILY_VARS,
                "timezone": "Africa/Johannesburg"}
        # the archive publishes with a delay of several days, so only ask it for older dates
        archive_end = min(max(missing), yesterday_sast() - timedelta(days=7))
        if min(missing) <= archive_end:
            archive = dict(base, start_date=min(missing).isoformat(), end_date=archive_end.isoformat())
            self._merge(self._fetch(ARCHIVE_URL, archive), cached, "open-meteo-archive")
        still = [d for d in missing if d.isoformat() not in cached]
        if still:
            self._merge(self._fetch(FORECAST_URL, dict(base, past_days=92, forecast_days=1)),
                        cached, "open-meteo-forecast", only={d.isoformat() for d in still})

    def _fetch(self, url: str, params: dict) -> dict | None:
        try:
            with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=8) as resp:
                return json.loads(resp.read())
        except Exception as exc:  # network blocked, API down, etc.
            print(f"  weather: {url} unavailable ({type(exc).__name__}); using fallback")
            return None

    @staticmethod
    def _merge(payload: dict | None, cached: dict, source: str, only: set | None = None) -> None:
        if not payload or "daily" not in payload:
            return
        daily = payload["daily"]
        for i, day in enumerate(daily["time"]):
            if only is not None and day not in only:
                continue
            tmax, tmin, rain = (daily["temperature_2m_max"][i], daily["temperature_2m_min"][i],
                                daily["precipitation_sum"][i])
            if None in (tmax, tmin, rain):
                continue
            cached[day] = {"tmax": tmax, "tmin": tmin, "precip": rain, "source": source}

    @staticmethod
    def _synthetic(slug: str, d: date) -> dict:
        mean, swing, rain_jul, rain_jan = CLIMATE.get(slug, (22.0, 4.0, 0.2, 0.2))
        season = math.cos(2 * math.pi * (d.timetuple().tm_yday - 15) / 365)  # +1 mid-Jan, -1 mid-Jul
        rng = seeded("weather", slug, d)
        tmax = mean + swing * season + rng.gauss(0, 2.2)
        rain_p = rain_jul + (rain_jan - rain_jul) * (season + 1) / 2
        precip = round(rng.expovariate(1 / 7), 1) if rng.random() < rain_p else 0.0
        if precip > 2:
            tmax -= 3
        tmax = round(tmax, 1)
        return {"tmax": tmax, "tmin": round(tmax - rng.uniform(7, 11), 1), "precip": precip,
                "source": "synthetic"}


def weather_boost(w: dict) -> float:
    """How much cold or wet weather lifts demand for outdoor gear (-0.5 to +1.0)."""
    idx = 0.0
    if w["precip"] >= 2:
        idx += 0.6
    if w["tmax"] < 17:
        idx += 0.4
    if w["tmax"] > 27:
        idx -= 0.4
    return max(-0.5, min(1.0, idx))


def trailing_days(d: date, start: date, n: int = 7) -> list[date]:
    return [x for x in (d - timedelta(days=k) for k in range(n - 1, -1, -1)) if x >= start]
