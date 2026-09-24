"""OpenWeatherMap client with a short in-process cache to stay within free-tier limits."""

import time
import requests
import config

OWM_BASE     = "https://api.openweathermap.org/data/2.5"
OWM_ICON_URL = "https://openweathermap.org/img/wn/{icon}@2x.png"

# ── Simple TTL cache (avoids hammering the free API) ─────────────────────────
_cache: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 600  # seconds (10 min)


def _cached(key: str, fetch_fn):
    now = time.time()
    if key in _cache:
        stored_at, value = _cache[key]
        if now - stored_at < _CACHE_TTL:
            return value
    value = fetch_fn()
    _cache[key] = (now, value)
    return value


def _icon(code: str) -> str:
    return OWM_ICON_URL.format(icon=code)


def _get(endpoint: str, params: dict) -> dict:
    params["appid"] = config.OWM_API_KEY
    params["units"] = "metric"
    resp = requests.get(f"{OWM_BASE}/{endpoint}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_current(city: str | None = None, country: str | None = None) -> dict:
    city    = city    or config.OWM_CITY
    country = country or config.OWM_COUNTRY
    key     = f"current:{city}:{country}"

    def fetch():
        data = _get("weather", {"q": f"{city},{country}"})
        return {
            "city":        data["name"],
            "country":     data["sys"]["country"],
            "temp":        round(data["main"]["temp"], 1),
            "feels_like":  round(data["main"]["feels_like"], 1),
            "temp_min":    round(data["main"]["temp_min"], 1),
            "temp_max":    round(data["main"]["temp_max"], 1),
            "humidity":    data["main"]["humidity"],
            "pressure":    data["main"]["pressure"],
            "description": data["weather"][0]["description"].capitalize(),
            "icon":        data["weather"][0]["icon"],
            "icon_url":    _icon(data["weather"][0]["icon"]),
            "wind_speed":  data["wind"]["speed"],
            "wind_deg":    data["wind"].get("deg", 0),
            "clouds":      data["clouds"]["all"],
            "visibility":  data.get("visibility", 0),
            "sunrise":     data["sys"]["sunrise"],
            "sunset":      data["sys"]["sunset"],
            "dt":          data["dt"],
        }

    return _cached(key, fetch)


def get_forecast(city: str | None = None, country: str | None = None, days: int = 5) -> list[dict]:
    """Return one summary entry per calendar day (up to *days* days)."""
    city    = city    or config.OWM_CITY
    country = country or config.OWM_COUNTRY
    days    = max(1, min(int(days), 7))
    key     = f"forecast:{city}:{country}:{days}"

    def fetch():
        data  = _get("forecast", {"q": f"{city},{country}", "cnt": days * 8})
        daily: dict[str, dict] = {}

        for item in data["list"]:
            date = item["dt_txt"][:10]
            if date not in daily:
                daily[date] = {
                    "date":        date,
                    "temp_min":    item["main"]["temp_min"],
                    "temp_max":    item["main"]["temp_max"],
                    "humidity":    item["main"]["humidity"],
                    "description": item["weather"][0]["description"].capitalize(),
                    "icon":        item["weather"][0]["icon"],
                    "icon_url":    _icon(item["weather"][0]["icon"]),
                    "wind_speed":  item["wind"]["speed"],
                    "pop":         round(item.get("pop", 0) * 100),  # % precipitation
                }
            else:
                daily[date]["temp_min"] = min(daily[date]["temp_min"], item["main"]["temp_min"])
                daily[date]["temp_max"] = max(daily[date]["temp_max"], item["main"]["temp_max"])
                # keep the entry with highest pop for the day's icon
                if item.get("pop", 0) > daily[date]["pop"] / 100:
                    daily[date]["pop"]         = round(item["pop"] * 100)
                    daily[date]["icon"]        = item["weather"][0]["icon"]
                    daily[date]["icon_url"]    = _icon(item["weather"][0]["icon"])
                    daily[date]["description"] = item["weather"][0]["description"].capitalize()

        result = list(daily.values())[:days]
        for d in result:
            d["temp_min"] = round(d["temp_min"], 1)
            d["temp_max"] = round(d["temp_max"], 1)
        return result

    return _cached(key, fetch)


def will_rain_today(city: str | None = None, country: str | None = None) -> bool:
    """Return True if there's >30% precipitation probability today."""
    forecast = get_forecast(city, country, days=1)
    return bool(forecast) and forecast[0]["pop"] > 30
