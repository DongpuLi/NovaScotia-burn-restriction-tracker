"""
Nova Scotia Burn Tracker updater v4.0

Generates:
- latest.json
- counties.json
- weather.json
- county_weather.json
- prediction.json
- county_prediction.json
- history.json
- county_history.json
- metrics.json
- county_metrics.json
- learning.json
- county_learning.json
- predictions_archive.json
- county_predictions_archive.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from burnsafe import fetch_all_counties, fetch_status
from predictor import predict_many
from weather import fetch_all_county_weather, fetch_weather_forecast

from fire_weather import ensure_fire_weather_files


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"

DATA_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(exist_ok=True)

TIMEZONE = ZoneInfo("America/Halifax")
POSTING_HOUR = 14
DEFAULT_COUNTY_ID = "Halifax-County"

BURN_SEASON_START = (3, 15)
BURN_SEASON_END = (10, 15)


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


def normalize_level(level: str | None) -> str:
    value = (level or "unknown").lower()
    if value in {"green", "yellow", "red"}:
        return value
    return "unknown"


def is_burn_season(now: datetime) -> bool:
    current = (now.month, now.day)
    return BURN_SEASON_START <= current <= BURN_SEASON_END


def update_county_history(
    county_history: dict,
    counties: list[dict],
    today: str,
    now: datetime,
) -> dict:
    for county in counties:
        county_id = county["id"]

        record = {
            "date": today,
            "updated_at": now.isoformat(timespec="seconds"),
            "timezone": "America/Halifax",
            "county_id": county_id,
            "county": county.get("name", county_id),
            "level": normalize_level(county.get("level")),
            "status": county.get("status", ""),
            "source": county.get("source", "https://novascotia.ca/burnsafe/"),
        }

        history = county_history.get(county_id, [])
        history = [item for item in history if item.get("date") != today]
        history.append(record)
        history.sort(key=lambda x: x.get("date", ""))

        county_history[county_id] = history

    return county_history


def latest_halifax_record(county_history: dict, previous_latest: dict | None):
    halifax_history = county_history.get(DEFAULT_COUNTY_ID, [])

    if halifax_history:
        return sorted(halifax_history, key=lambda x: x.get("date", ""))[-1]

    return previous_latest


def evaluate_county_predictions(
    today: str,
    counties: list[dict],
    county_archive: dict,
    county_learning: dict,
) -> tuple[dict, dict]:
    actual_by_county = {
        county["id"]: normalize_level(county.get("level"))
        for county in counties
    }

    for county_id, actual in actual_by_county.items():
        archive = county_archive.get(county_id, [])
        learning = county_learning.get(county_id, [])

        existing_keys = {
            item.get("evaluation_key")
            for item in learning
            if item.get("evaluation_key")
        }

        for item in archive:
            if item.get("target_date") != today:
                continue

            if item.get("actual_level"):
                continue

            predicted = normalize_level(item.get("predicted_level"))
            horizon_days = item.get("horizon_days")

            item["actual_level"] = actual
            item["correct"] = predicted == actual
            item["evaluated_at"] = datetime.now(TIMEZONE).isoformat(timespec="seconds")

            evaluation_key = (
                f"{county_id}:"
                f"{item.get('issued_date')}->{item.get('target_date')}"
                f":h{horizon_days}"
            )

            if evaluation_key not in existing_keys:
                learning.append({
                    "evaluation_key": evaluation_key,
                    "county_id": county_id,
                    "issued_date": item.get("issued_date"),
                    "target_date": item.get("target_date"),
                    "horizon_days": horizon_days,
                    "predicted": predicted,
                    "actual": actual,
                    "correct": predicted == actual,
                    "confidence": item.get("confidence"),
                    "model": item.get("model"),
                    "reason": item.get("reason"),
                    "weather": item.get("weather"),
                })

        county_archive[county_id] = archive
        county_learning[county_id] = learning

    return county_archive, county_learning


def accuracy_block(items: list[dict]) -> dict:
    total = len(items)
    correct = sum(1 for item in items if item.get("correct"))

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else None,
    }


def build_one_metrics(learning: list[dict]) -> dict:
    labels = ["green", "yellow", "red", "unknown"]

    evaluated = [
        item for item in learning
        if item.get("actual") and item.get("predicted")
    ]

    headline = [
        item for item in evaluated
        if item.get("horizon_days") == 1
    ]

    confusion_matrix = {
        actual: {predicted: 0 for predicted in labels}
        for actual in labels
    }

    for item in evaluated:
        actual = normalize_level(item.get("actual"))
        predicted = normalize_level(item.get("predicted"))
        confusion_matrix[actual][predicted] += 1

    by_horizon = {}
    for horizon in range(1, 8):
        items = [
            item for item in evaluated
            if item.get("horizon_days") == horizon
        ]
        by_horizon[str(horizon)] = accuracy_block(items)

    by_actual_level = {}
    for level in labels:
        items = [
            item for item in evaluated
            if normalize_level(item.get("actual")) == level
        ]
        by_actual_level[level] = accuracy_block(items)

    by_predicted_level = {}
    for level in labels:
        items = [
            item for item in evaluated
            if normalize_level(item.get("predicted")) == level
        ]
        by_predicted_level[level] = accuracy_block(items)

    headline_metrics = accuracy_block(headline)
    all_metrics = accuracy_block(evaluated)

    return {
        "version": "4.0",
        "primary_metric": "one_day_ahead",
        "total_evaluated": headline_metrics["total"],
        "correct": headline_metrics["correct"],
        "accuracy": headline_metrics["accuracy"],
        "all_evaluated": all_metrics,
        "by_horizon": by_horizon,
        "by_actual_level": by_actual_level,
        "by_predicted_level": by_predicted_level,
        "confusion_matrix": confusion_matrix,
        "updated_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
    }


def build_county_metrics(county_learning: dict, counties: list[dict]) -> dict:
    return {
        county["id"]: build_one_metrics(county_learning.get(county["id"], []))
        for county in counties
    }


def archive_county_predictions(
    today: str,
    now: datetime,
    counties: list[dict],
    predictions_by_county: dict,
    county_archive: dict,
) -> dict:
    for county in counties:
        county_id = county["id"]
        archive = county_archive.get(county_id, [])

        existing_keys = {
            f"{item.get('issued_date')}->{item.get('target_date')}"
            for item in archive
        }

        for item in predictions_by_county.get(county_id, []):
            key = f"{today}->{item['date']}"

            if key in existing_keys:
                continue

            archive.append({
                "issued_date": today,
                "issued_at": now.isoformat(timespec="seconds"),
                "county_id": county_id,
                "target_date": item["date"],
                "horizon_days": item["horizon_days"],
                "predicted_level": item["predicted_level"],
                "confidence": item["confidence"],
                "model": item["model"],
                "score": item["score"],
                "reason": item["reason"],
                "weather": item["weather"],
                "actual_level": None,
                "correct": None,
            })

        county_archive[county_id] = archive

    return county_archive


def main() -> None:
    ensure_fire_weather_files()

    now = datetime.now(TIMEZONE)
    today = now.date().isoformat()
    in_burn_season = is_burn_season(now)

    previous_latest = load_json("latest.json", None)

    county_history = load_json("county_history.json", {})
    county_archive = load_json("county_predictions_archive.json", {})
    county_learning = load_json("county_learning.json", {})

    if not in_burn_season:
        latest = previous_latest or {
            "date": today,
            "updated_at": now.isoformat(timespec="seconds"),
            "timezone": "America/Halifax",
            "county_id": DEFAULT_COUNTY_ID,
            "county": "Halifax County",
            "level": "offseason",
            "status": (
                "Static archive mode. BurnSafe wildfire risk season runs "
                "from March 15 to October 15. Verify local municipal and "
                "provincial rules before burning."
            ),
            "source": "https://novascotia.ca/burnsafe/",
        }

        latest["site_mode"] = "offseason"
        latest["level"] = "offseason"
        latest["status"] = (
            "Static archive mode. BurnSafe wildfire risk season runs "
            "from March 15 to October 15. Verify local municipal and "
            "provincial rules before burning."
        )
        latest["updated_at"] = now.isoformat(timespec="seconds")
        latest["site_mode"] = "offseason"
        latest["archive_season"] = str(now.year)

        save_json_to_both("latest.json", latest)

        print("Outside burn season.")
        print("Static archive mode enabled.")
        print("No BurnSafe/weather fetch performed.")
        return

    today_already_recorded = any(
        item.get("date") == today
        for item in county_history.get(DEFAULT_COUNTY_ID, [])
    )

    should_write_official = (
        now.hour >= POSTING_HOUR
        and not today_already_recorded
    )

    counties_data = fetch_all_counties()
    counties = counties_data.get("counties", [])

    counties_data["fetched_at"] = now.isoformat(timespec="seconds")
    counties_data["timezone"] = "America/Halifax"

    county_weather = fetch_all_county_weather()

    halifax_weather = county_weather.get(DEFAULT_COUNTY_ID, {})
    weather_forecast = halifax_weather.get("forecast")

    if not weather_forecast:
        weather_forecast = fetch_weather_forecast(DEFAULT_COUNTY_ID)

    predictions_by_county = {}

    for county in counties:
        county_id = county["id"]
        weather_records = county_weather.get(county_id, {}).get("forecast", weather_forecast)

        predictions_by_county[county_id] = predict_many(
            weather_records,
            county_learning.get(county_id, []),
        )

    if should_write_official:
        county_history = update_county_history(
            county_history=county_history,
            counties=counties,
            today=today,
            now=now,
        )

        county_archive, county_learning = evaluate_county_predictions(
            today=today,
            counties=counties,
            county_archive=county_archive,
            county_learning=county_learning,
        )

        county_archive = archive_county_predictions(
            today=today,
            now=now,
            counties=counties,
            predictions_by_county=predictions_by_county,
            county_archive=county_archive,
        )

        halifax = next(
            (county for county in counties if county.get("id") == DEFAULT_COUNTY_ID),
            {},
        )

        latest = {
            "date": today,
            "updated_at": now.isoformat(timespec="seconds"),
            "timezone": "America/Halifax",
            "site_mode": "active",
            "county_id": halifax.get("id", DEFAULT_COUNTY_ID),
            "county": halifax.get("name", "Halifax County"),
            "level": normalize_level(halifax.get("level")),
            "status": halifax.get("status", ""),
            "source": halifax.get("source", "https://novascotia.ca/burnsafe/"),
            "official_updated_text": counties_data.get("updated_text", ""),
        }

    else:
        latest = latest_halifax_record(county_history, previous_latest) or {
            "date": today,
            "updated_at": now.isoformat(timespec="seconds"),
            "timezone": "America/Halifax",
            "site_mode": "active",
            "county_id": DEFAULT_COUNTY_ID,
            "county": "Halifax County",
            "level": "red",
            "status": "Burning is not allowed.",
            "source": "https://novascotia.ca/burnsafe/",
            "pre_2pm_display": True,
        }

        latest["site_mode"] = "active"

    county_metrics = build_county_metrics(county_learning, counties)

    save_json_to_both("latest.json", latest)
    save_json_to_both("history.json", county_history.get(DEFAULT_COUNTY_ID, []))
    save_json_to_both("weather.json", weather_forecast)
    save_json_to_both("prediction.json", predictions_by_county.get(DEFAULT_COUNTY_ID, []))
    save_json_to_both("predictions_archive.json", county_archive.get(DEFAULT_COUNTY_ID, []))
    save_json_to_both("learning.json", county_learning.get(DEFAULT_COUNTY_ID, []))
    save_json_to_both("metrics.json", county_metrics.get(DEFAULT_COUNTY_ID, build_one_metrics([])))

    save_json_to_both("counties.json", counties_data)
    save_json_to_both("county_weather.json", county_weather)
    save_json_to_both("county_history.json", county_history)
    save_json_to_both("county_prediction.json", predictions_by_county)
    save_json_to_both("county_predictions_archive.json", county_archive)
    save_json_to_both("county_learning.json", county_learning)
    save_json_to_both("county_metrics.json", county_metrics)

    print("Updated.")
    print(f"Halifax time: {now.isoformat(timespec='seconds')}")
    print(f"Burn season active: {in_burn_season}")
    print(f"After 2 p.m. posting time: {now.hour >= POSTING_HOUR}")
    print(f"Should write official data: {should_write_official}")
    print(f"Parsed {len(counties)} counties.")
    print(f"Generated county weather for {len(county_weather)} counties.")
    print(f"Generated county predictions for {len(predictions_by_county)} counties.")
if __name__ == "__main__":
    main()