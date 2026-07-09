from __future__ import annotations

from collections import Counter


LABELS = ["green", "yellow", "red"]


def weather_features(weather: dict) -> dict:
    return {
        "temperature_max_c": float(weather.get("temperature_max_c") or 0),
        "humidity_mean_percent": float(weather.get("humidity_mean_percent") or 0),
        "precipitation_mm": float(weather.get("precipitation_mm") or 0),
        "wind_max_kmh": float(weather.get("wind_max_kmh") or 0),
        "wind_gust_max_kmh": float(weather.get("wind_gust_max_kmh") or 0),
        "dry_streak_days": float(weather.get("dry_streak_days") or 0),
    }


def classify_fwi(fwi: float | None) -> str:
    if fwi is None:
        return "unknown"
    if fwi < 4:
        return "low"
    if fwi < 10:
        return "moderate"
    if fwi < 17:
        return "high"
    if fwi < 23:
        return "very_high"
    return "extreme"


def rule_based_predict(weather: dict) -> dict:
    temp = float(weather.get("temperature_max_c") or 0)
    humidity = float(weather.get("humidity_mean_percent") or 100)
    rain = float(weather.get("precipitation_mm") or 0)
    wind = float(weather.get("wind_max_kmh") or 0)
    gust = float(weather.get("wind_gust_max_kmh") or 0)
    dry_days = float(weather.get("dry_streak_days") or 0)

    score = 0
    reasons = []

    if temp >= 28:
        score += 2
        reasons.append("hot day")
    elif temp >= 23:
        score += 1
        reasons.append("warm day")

    if humidity <= 35:
        score += 2
        reasons.append("low humidity")
    elif humidity <= 45:
        score += 1
        reasons.append("moderately low humidity")

    if rain < 0.5:
        score += 1
        reasons.append("little or no rain")
    elif rain >= 3:
        score -= 2
        reasons.append("meaningful rain expected")

    if wind >= 30:
        score += 2
        reasons.append("strong wind")
    elif wind >= 20:
        score += 1
        reasons.append("moderate wind")

    if gust >= 45:
        score += 2
        reasons.append("high wind gusts")

    if dry_days >= 5:
        score += 2
        reasons.append("several dry days")
    elif dry_days >= 3:
        score += 1
        reasons.append("short dry spell")

    # Revised interpretation:
    # Green = clearly low-risk weather.
    # Yellow = controlled burning window under moderate fire-weather risk.
    # Red = high-risk conditions where burning should not be allowed.
    if score >= 7:
        level = "red"
        confidence = min(90, 58 + score * 4)
    elif score >= 1:
        level = "yellow"
        confidence = min(85, 58 + score * 5)
    else:
        level = "green"
        confidence = 62

    return {
        "level": level,
        "confidence": round(confidence),
        "model": "rule",
        "score": score,
        "reason": ", ".join(reasons) if reasons else "low fire-risk weather pattern",
    }


def official_fwi_refined_predict(weather: dict, fire_weather: dict) -> dict:
    base = rule_based_predict(weather)

    fwi = fire_weather.get("fwi")
    ffmc = fire_weather.get("ffmc")
    isi = fire_weather.get("isi")
    bui = fire_weather.get("bui")
    rh = fire_weather.get("rh_percent")
    wind = fire_weather.get("wind_speed_kph")
    rain = fire_weather.get("rain_24h_mm")

    fwi_class = classify_fwi(fwi)

    reasons = [
        f"official FWI category: {fwi_class}",
        f"FWI {fwi}" if fwi is not None else None,
        f"FFMC {ffmc}" if ffmc is not None else None,
        f"ISI {isi}" if isi is not None else None,
    ]
    reasons = [r for r in reasons if r]

    # Red only for clearly severe official fire-weather signals.
    if (
        fwi is not None
        and (
            fwi >= 23
            or (
                fwi >= 17
                and ffmc is not None and ffmc >= 92
                and rh is not None and rh <= 35
                and wind is not None and wind >= 20
            )
        )
    ):
        return {
            "level": "red",
            "confidence": 82,
            "model": "official_fwi_refined",
            "score": base["score"],
            "reason": ", ".join(reasons + ["severe official fire-weather conditions"]),
        }

    # Green requires genuinely low official fire-weather risk.
    if (
        fwi is not None and fwi < 4
        and ffmc is not None and ffmc < 85
        and (rh is None or rh >= 60)
        and (wind is None or wind < 15)
    ):
        return {
            "level": "green",
            "confidence": 78,
            "model": "official_fwi_refined",
            "score": base["score"],
            "reason": ", ".join(reasons + ["low official fire-weather conditions"]),
        }

    # Moderate/high FWI is best interpreted as restricted burning window.
    if fwi is not None and fwi < 23:
        return {
            "level": "yellow",
            "confidence": 76 if fwi >= 10 else 70,
            "model": "official_fwi_refined",
            "score": base["score"],
            "reason": ", ".join(reasons + ["restricted burning window is more appropriate"]),
        }

    return base


def distance(a: dict, b: dict) -> float:
    scales = {
        "temperature_max_c": 15,
        "humidity_mean_percent": 40,
        "precipitation_mm": 10,
        "wind_max_kmh": 30,
        "wind_gust_max_kmh": 50,
        "dry_streak_days": 7,
    }

    total = 0.0
    for key, scale in scales.items():
        total += ((float(a.get(key, 0)) - float(b.get(key, 0))) / scale) ** 2

    return total ** 0.5


def knn_predict(weather: dict, learning: list[dict]) -> dict | None:
    examples = [
        item for item in learning
        if item.get("actual") in LABELS and isinstance(item.get("weather"), dict)
    ]

    if len(examples) < 20:
        return None

    current = weather_features(weather)

    ranked = sorted(
        examples,
        key=lambda item: distance(current, weather_features(item["weather"]))
    )

    nearest = ranked[:7]
    votes = Counter(item["actual"] for item in nearest)
    level, count = votes.most_common(1)[0]

    confidence = round(50 + (count / len(nearest)) * 45)

    return {
        "level": level,
        "confidence": confidence,
        "model": "knn",
        "score": None,
        "reason": f"machine-learning prediction based on {len(examples)} past evaluated examples",
    }


def add_dry_streak(weather_records: list[dict]) -> list[dict]:
    dry_streak = 0
    output = []

    for item in weather_records:
        record = dict(item)
        rain = float(record.get("precipitation_mm") or 0)

        if rain < 0.5:
            dry_streak += 1
        else:
            dry_streak = 0

        record["dry_streak_days"] = dry_streak
        output.append(record)

    return output


def predict_many(
    weather_records: list[dict],
    learning: list[dict],
    official_fire_weather: dict | None = None,
) -> list[dict]:
    weather_records = add_dry_streak(weather_records)

    predictions = []

    for i, weather in enumerate(weather_records):
        if i == 0 and official_fire_weather:
            result = official_fwi_refined_predict(weather, official_fire_weather)
        else:
            ml = knn_predict(weather, learning)
            rule = rule_based_predict(weather)
            result = ml or rule

        predictions.append({
            "date": weather["date"],
            "horizon_days": i,
            "predicted_level": result["level"],
            "confidence": result["confidence"],
            "model": result["model"],
            "score": result["score"],
            "reason": result["reason"],
            "weather": weather,
            "official_fire_weather": official_fire_weather if i == 0 else None,
        })

    return predictions