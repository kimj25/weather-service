"""Tests for the weather microservice.

Covers the pure helpers (parse_weathercode, build_daily_breakdown) and the
API wrappers (get_forecast, get_historical, get_weather_data) without making
any real network calls — requests and the fetch functions are mocked.
"""

from datetime import datetime, timedelta

import pytest

import weather

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.mark.parametrize(
    "code, expected",
    [
        (0, "Clear Sky"),
        (1, "Partly Cloudy"),
        (3, "Partly Cloudy"),
        (45, "Foggy"),
        (51, "Drizzle"),
        (61, "Rainy"),
        (71, "Snowy"),
        (80, "Rain Showers"),
        (95, "Thunderstorm"),
        (999, "Unknown"),
    ],
)
def test_parse_weathercode(code, expected):
    """Each Open-Meteo weather code maps to the expected human readable label."""
    assert weather.parse_weathercode(code) == expected


def test_build_daily_breakdown_forecast():
    """Forecast responses use the API date as-is and handle missing values."""
    data = {
        "daily": {
            "time": ["2026-08-10", "2026-08-11"],
            "temperature_2m_max": [25.0, None],
            "temperature_2m_min": [15.0, 14.0],
            "precipitation_sum": [0.0, 3.5],
            "weathercode": [0, 61],
        }
    }
    breakdown = weather.build_daily_breakdown(data, "2026-08-10")

    assert len(breakdown) == 2
    assert breakdown[0] == {
        "date": "2026-08-10",
        "high": 25.0,
        "low": 15.0,
        "conditions": "Clear Sky",
        "precipitation_mm": 0.0,
    }
    # missing high should fall back to "N/A" and the code 61 should read "Rainy"
    assert breakdown[1]["high"] == "N/A"
    assert breakdown[1]["conditions"] == "Rainy"


def test_build_daily_breakdown_historical_uses_actual_dates():
    """Historical responses swap last year's dates for the real travel dates."""
    data = {
        "daily": {
            "time": ["2025-08-10", "2025-08-11"],
            "temperature_2m_max": [25.0, 26.0],
            "temperature_2m_min": [15.0, 16.0],
            "precipitation_sum": [0.0, 0.0],
            "weathercode": [0, 0],
        }
    }
    breakdown = weather.build_daily_breakdown(data, "2026-08-10", is_historical=True)

    assert [day["date"] for day in breakdown] == ["2026-08-10", "2026-08-11"]


def test_get_forecast_calls_api_with_params(monkeypatch):
    """get_forecast builds the right URL, params, and a 30s timeout."""
    captured = {}

    # intercept requests.get and record the call arguments
    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return FakeResponse({"ok": True})

    monkeypatch.setattr(weather.requests, "get", fake_get)

    result = weather.get_forecast("45.5", "-122.6", "2026-08-10", "2026-08-12")

    assert result == {"ok": True}
    assert captured["url"] == FORECAST_URL
    assert captured["params"]["start_date"] == "2026-08-10"
    assert captured["params"]["end_date"] == "2026-08-12"
    assert captured["params"]["timezone"] == "auto"
    assert captured["timeout"] == 30


def test_get_forecast_returns_none_on_error(monkeypatch):
    """Network errors should surface as None so the caller can return an error."""

    def fake_get(url, params, timeout):
        raise weather.requests.ConnectionError

    monkeypatch.setattr(weather.requests, "get", fake_get)

    assert weather.get_forecast("45.5", "-122.6", "2026-08-10", "2026-08-12") is None


def test_get_historical_uses_last_year_dates(monkeypatch):
    """Historical requests query the same dates from one year earlier."""
    captured = {}

    def fake_get(url, params, timeout):
        captured["params"] = params
        return FakeResponse({"ok": True})

    monkeypatch.setattr(weather.requests, "get", fake_get)

    result = weather.get_historical("45.5", "-122.6", "2026-08-10", "2026-08-12")

    assert result == {"ok": True}
    assert captured["params"]["start_date"] == "2025-08-10"
    assert captured["params"]["end_date"] == "2025-08-12"


def days_from_today(days):
    """Return an ISO date that is `days` away from today (for branching tests)."""
    return (datetime.today() + timedelta(days=days)).strftime("%Y-%m-%d")


def test_get_weather_data_uses_forecast_within_16_days(monkeypatch):
    """Trips within 16 days should fetch from the forecast API."""
    monkeypatch.setattr(
        weather,
        "get_forecast",
        # return a one-day payload so we can assert on the response shape
        lambda latitude, longitude, dep, ret: {
            "daily": {
                "time": [days_from_today(2)],
                "temperature_2m_max": [20.0],
                "temperature_2m_min": [10.0],
                "precipitation_sum": [0.0],
                "weathercode": [0],
            }
        },
    )

    result = weather.get_weather_data(45.5, -122.6, days_from_today(2), days_from_today(4))

    assert result["data_type"] == "forecast"
    assert result["unit"] == "C"
    assert len(result["daily"]) == 1


def test_get_weather_data_uses_historical_beyond_16_days(monkeypatch):
    """Trips beyond 16 days should fall back to the historical archive."""
    monkeypatch.setattr(
        weather,
        "get_historical",
        lambda latitude, longitude, dep, ret: {
            "daily": {
                "time": [days_from_today(30)],
                "temperature_2m_max": [20.0],
                "temperature_2m_min": [10.0],
                "precipitation_sum": [0.0],
                "weathercode": [0],
            }
        },
    )

    result = weather.get_weather_data(45.5, -122.6, days_from_today(30), days_from_today(32))

    assert result["data_type"] == "historical"


def test_get_weather_data_returns_error_when_api_fails(monkeypatch):
    """A None response from the API layer should produce an error payload."""
    monkeypatch.setattr(weather, "get_forecast", lambda *args: None)

    result = weather.get_weather_data(45.5, -122.6, days_from_today(2), days_from_today(4))

    assert "error" in result


def test_get_weather_data_returns_error_when_no_daily_data(monkeypatch):
    """An empty daily block should produce an error payload."""
    monkeypatch.setattr(weather, "get_forecast", lambda *args: {"daily": {}})

    result = weather.get_weather_data(45.5, -122.6, days_from_today(2), days_from_today(4))

    assert "error" in result
