"""Thin wrapper around the Flask middleware API."""

import os
from typing import Optional
import requests

API_BASE = os.getenv(
    "API_BASE_URL",
    "https://weather-flask-297113273467.europe-west6.run.app",
)
_TIMEOUT = 10


def _get(path: str, params: Optional[dict] = None):
    """Return (data, error_string). One of them is always None."""
    try:
        resp = requests.get(f"{API_BASE}{path}", params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json(), None
    except requests.exceptions.ConnectionError:
        return None, "Cannot reach the API — check your network or the API_BASE_URL."
    except requests.exceptions.Timeout:
        return None, "API request timed out."
    except requests.exceptions.HTTPError as exc:
        return None, f"API error {exc.response.status_code}: {exc.response.text[:120]}"
    except Exception as exc:
        return None, str(exc)


def get_snapshot(city: Optional[str] = None):
    """Indoor + alerts + outdoor in one call — used by the dashboard landing page."""
    params = {"city": city} if city else None
    return _get("/snapshot", params)


def get_history(hours: int = 24, limit: int = 800):
    return _get("/indoor/history", {"hours": hours, "limit": limit})


def get_stats(hours: int = 24):
    return _get("/indoor/stats", {"hours": hours})


def get_forecast(days: int = 5, city: Optional[str] = None):
    params: dict = {"days": days}
    if city:
        params["city"] = city
    return _get("/weather/forecast", params)


def get_alerts():
    return _get("/indoor/alerts")
