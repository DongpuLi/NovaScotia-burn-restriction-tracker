"""
Nova Scotia Fire Weather module.

v1.1.0 step 2:
- Fetch official Fire Weather Forecast table
- Fetch official Fire Weather Actuals table
- Parse station-level FWI data
- Save JSON files to both data/ and docs/
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"

TIMEZONE = ZoneInfo("America/Halifax")

FORECAST_URL = (
    "https://novascotia.ca/natr/forestprotection/wildfire/fwi/"
    "FWIforecast.xml"
)

ACTUALS_URL = (
    "https://novascotia.ca/natr/forestprotection/wildfire/fwi/"
    "FWIactuals.xml"
)


def save_json_to_both(filename: str, data) -> None:
    for directory in (DATA_DIR, DOCS_DIR):
        path = directory / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(filename: str, default):
    path = DATA_DIR / filename

    if not path.exists() or path.stat().st_size == 0:
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default


def ensure_fire_weather_files() -> None:
    files = {
        "fire_weather_forecast.json": {
            "date": None,
            "updated_at": None,
            "source": FORECAST_URL,
            "stations": {},
        },
        "fire_weather_actuals.json": {
            "date": None,
            "updated_at": None,
            "source": ACTUALS_URL,
            "stations": {},
        },
        "county_fire_weather.json": {},
        "fire_weather_metrics.json": {},
        "fire_weather_evaluations.json": [],
    }

    for filename, default_data in files.items():
        data_path = DATA_DIR / filename
        docs_path = DOCS_DIR / filename

        if not data_path.exists():
            save_json_to_both(filename, default_data)
            continue

        if not docs_path.exists():
            existing_data = load_json(filename, default_data)
            save_json_to_both(filename, existing_data)


def _fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 NovaScotiaBurnRestrictionTracker/1.1 "
            "(community project; GitHub Pages)"
        )
    }

    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.text


def _to_float(value: str):
    value = value.strip()

    if value in {"", "-", "N/A", "NA"}:
        return None

    try:
        return float(value)
    except ValueError:
        return None


def _normalize_station_name(value: str) -> str:
    return " ".join(value.strip().upper().split())


def _normalize_date(value: str) -> str | None:
    """
    Converts DD/MM/YYYY to YYYY-MM-DD.
    Example: 08/07/2026 -> 2026-07-08
    """
    value = value.strip()

    try:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _get_text(node, tag: str) -> str:
    child = node.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _parse_fire_weather_xml(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)

    stations = {}
    detected_date = None

    for node in root.findall(".//weather"):
        station = _normalize_station_name(_get_text(node, "wxStation"))
        date = _normalize_date(_get_text(node, "Date"))

        if not station or date is None:
            continue

        record = {
            "station": station,
            "date": date,
            "temp_c": _to_float(_get_text(node, "Temp")),
            "rh_percent": _to_float(_get_text(node, "Rh")),
            "wind_speed_kph": _to_float(_get_text(node, "Wspd")),
            "wind_direction_deg": _to_float(_get_text(node, "Dir")),
            "rain_24h_mm": _to_float(_get_text(node, "Rn24")),
            "ffmc": _to_float(_get_text(node, "FFMC")),
            "dmc": _to_float(_get_text(node, "DMC")),
            "dc": _to_float(_get_text(node, "DC")),
            "isi": _to_float(_get_text(node, "ISI")),
            "bui": _to_float(_get_text(node, "BUI")),
            "fwi": _to_float(_get_text(node, "FWI")),
        }

        stations[station] = record
        detected_date = detected_date or date

    if not stations:
        raise RuntimeError("No fire weather station rows were parsed from XML.")

    return {
        "date": detected_date,
        "stations": stations,
    }


def fetch_fire_weather_forecast() -> dict:
    now = datetime.now(TIMEZONE)

    xml_text = _fetch_html(FORECAST_URL)
    parsed = _parse_fire_weather_xml(xml_text)

    return {
        "date": parsed["date"],
        "updated_at": now.isoformat(timespec="seconds"),
        "timezone": "America/Halifax",
        "source": FORECAST_URL,
        "stations": parsed["stations"],
    }


def fetch_fire_weather_actuals() -> dict:
    now = datetime.now(TIMEZONE)

    xml_text = _fetch_html(ACTUALS_URL)
    parsed = _parse_fire_weather_xml(xml_text)

    return {
        "date": parsed["date"],
        "updated_at": now.isoformat(timespec="seconds"),
        "timezone": "America/Halifax",
        "source": ACTUALS_URL,
        "stations": parsed["stations"],
    }

def classify_fwi(fwi: float | None) -> str:
    if fwi is None:
        return "unknown"

    if fwi < 5:
        return "low"
    if fwi < 12:
        return "moderate"
    if fwi < 21:
        return "high"
    if fwi < 30:
        return "very_high"

    return "extreme"

def build_county_fire_weather(
    forecast: dict,
    station_county_map: dict,
) -> dict:
    county_records = {}

    for station_name, station_record in forecast.get("stations", {}).items():
        county_ids = station_county_map.get(station_name, [])

        for county_id in county_ids:
            county = county_records.setdefault(
                county_id,
                {
                    "county_id": county_id,
                    "date": forecast.get("date"),
                    "updated_at": forecast.get("updated_at"),
                    "timezone": forecast.get("timezone", "America/Halifax"),
                    "source": forecast.get("source"),
                    "stations": [],
                    "station_count": 0,
                    "aggregation": "max",
                    "temp_c": None,
                    "rh_percent": None,
                    "wind_speed_kph": None,
                    "rain_24h_mm": None,
                    "ffmc": None,
                    "dmc": None,
                    "dc": None,
                    "isi": None,
                    "bui": None,
                    "fwi": None,
                },
            )

            county["stations"].append(station_name)

            for key in [
                "temp_c",
                "wind_speed_kph",
                "rain_24h_mm",
                "ffmc",
                "dmc",
                "dc",
                "isi",
                "bui",
                "fwi",
            ]:
                value = station_record.get(key)
                if value is None:
                    continue
                if county[key] is None or value > county[key]:
                    county[key] = value

            rh = station_record.get("rh_percent")
            if rh is not None:
                if county["rh_percent"] is None or rh < county["rh_percent"]:
                    county["rh_percent"] = rh

    for county in county_records.values():
        county["stations"] = sorted(set(county["stations"]))
        county["station_count"] = len(county["stations"])

    return county_records

def evaluate_fire_weather_forecast(
    forecast: dict,
    actuals: dict,
    existing_evaluations: list,
) -> list:
    forecast_date = forecast.get("date")
    actuals_date = actuals.get("date")

    if not forecast_date or not actuals_date:
        return existing_evaluations

    if forecast_date != actuals_date:
        return existing_evaluations

    evaluations = [
        item for item in existing_evaluations
        if item.get("date") != forecast_date
    ]

    forecast_stations = forecast.get("stations", {})
    actual_stations = actuals.get("stations", {})

    for station, forecast_record in forecast_stations.items():
        actual_record = actual_stations.get(station)
        if not actual_record:
            continue

        forecast_fwi = forecast_record.get("fwi")
        actual_fwi = actual_record.get("fwi")

        forecast_class = classify_fwi(forecast_fwi)
        actual_class = classify_fwi(actual_fwi)

        evaluations.append({
            "date": forecast_date,
            "station": station,
            "forecast_fwi": forecast_fwi,
            "actual_fwi": actual_fwi,
            "forecast_class": forecast_class,
            "actual_class": actual_class,
            "correct_class": forecast_class == actual_class,
            "absolute_error": (
                abs(forecast_fwi - actual_fwi)
                if forecast_fwi is not None and actual_fwi is not None
                else None
            ),
        })

    evaluations.sort(key=lambda x: (x.get("date", ""), x.get("station", "")))
    return evaluations

def build_fire_weather_metrics(evaluations: list) -> dict:
    total = len(evaluations)

    if total == 0:
        return {
            "total_evaluated": 0,
            "correct_class": 0,
            "class_accuracy": None,
            "mean_absolute_error": None,
        }

    correct = sum(1 for item in evaluations if item.get("correct_class"))

    errors = [
        item.get("absolute_error")
        for item in evaluations
        if item.get("absolute_error") is not None
    ]

    mean_absolute_error = (
        round(sum(errors) / len(errors), 2)
        if errors
        else None
    )

    return {
        "total_evaluated": total,
        "correct_class": correct,
        "class_accuracy": round(correct / total, 3),
        "mean_absolute_error": mean_absolute_error,
    }

def update_fire_weather_files() -> tuple[dict, dict]:
    forecast = fetch_fire_weather_forecast()
    actuals = fetch_fire_weather_actuals()

    save_json_to_both("fire_weather_forecast.json", forecast)
    save_json_to_both("fire_weather_actuals.json", actuals)

    station_county_map = load_json("station_county_map.json", {})

    county_fire_weather = build_county_fire_weather(
        forecast=forecast,
        station_county_map=station_county_map,
    )

    save_json_to_both("county_fire_weather.json", county_fire_weather)

    existing_evaluations = load_json("fire_weather_evaluations.json", [])

    evaluations = evaluate_fire_weather_forecast(
        forecast=forecast,
        actuals=actuals,
        existing_evaluations=existing_evaluations,
    )

    metrics = build_fire_weather_metrics(evaluations)

    save_json_to_both("fire_weather_evaluations.json", evaluations)
    save_json_to_both("fire_weather_metrics.json", metrics)

    return forecast, actuals


if __name__ == "__main__":
    ensure_fire_weather_files()
    forecast_data, actuals_data = update_fire_weather_files()

    print("Fire weather data updated.")
    print(f"Forecast date: {forecast_data.get('date')}")
    print(f"Forecast stations: {len(forecast_data.get('stations', {}))}")
    print(f"Actuals date: {actuals_data.get('date')}")
    print(f"Actuals stations: {len(actuals_data.get('stations', {}))}")