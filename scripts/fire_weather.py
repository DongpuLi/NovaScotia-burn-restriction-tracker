"""
Nova Scotia Fire Weather module.

Initial v1.1.0 scaffold:
- fire_weather_forecast.json
- fire_weather_actuals.json
- county_fire_weather.json
- station_county_map.json
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"


EMPTY_FORECAST = {
    "date": None,
    "updated_at": None,
    "source": "https://novascotia.ca/natr/forestprotection/wildfire/fwi/fire-weather-forecast.asp",
    "stations": {}
}

EMPTY_ACTUALS = {
    "date": None,
    "updated_at": None,
    "source": "https://novascotia.ca/natr/forestprotection/wildfire/fwi/Fire-Weather-Forecast-Actuals.asp",
    "stations": {}
}

EMPTY_COUNTY_FIRE_WEATHER = {}

EMPTY_STATION_COUNTY_MAP = {}


def save_json_to_both(filename: str, data) -> None:
    for directory in (DATA_DIR, DOCS_DIR):
        path = directory / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def ensure_fire_weather_files() -> None:
    files = {
        "fire_weather_forecast.json": EMPTY_FORECAST,
        "fire_weather_actuals.json": EMPTY_ACTUALS,
        "county_fire_weather.json": EMPTY_COUNTY_FIRE_WEATHER,
        "station_county_map.json": EMPTY_STATION_COUNTY_MAP,
    }

    for filename, default_data in files.items():
        data_path = DATA_DIR / filename
        docs_path = DOCS_DIR / filename

        if not data_path.exists():
            save_json_to_both(filename, default_data)
            continue

        if not docs_path.exists():
            with open(data_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
            save_json_to_both(filename, existing_data)


if __name__ == "__main__":
    ensure_fire_weather_files()
    print("Fire weather files ensured.")