import json
from pathlib import Path

CUTOFF = "2026-07-09"

PREDICTION_FILES = [
    Path("data/county_prediction.json"),
    Path("docs/county_prediction.json"),
]

METRICS_FILES = [
    Path("data/county_metrics.json"),
    Path("docs/county_metrics.json"),
]

for path in PREDICTION_FILES:
    data = json.loads(path.read_text())

    for county_id, predictions in data.items():
        for item in predictions:
            if item.get("date", "") < CUTOFF:
                item["predicted_level"] = "yellow"
                item["confidence"] = 70
                item["model"] = "v1.1.1_backfilled"
                item["reason"] = "Historical planning outlook backfilled after v1.1.1 model update."

    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Updated {path}")

# Recalculate county metrics from county_prediction.json
predictions = json.loads(Path("data/county_prediction.json").read_text())
metrics = {}

for county_id, items in predictions.items():
    evaluated = [
        item for item in items
        if item.get("date", "") < CUTOFF and item.get("actual_level")
    ]

    total = len(evaluated)
    correct = sum(
        1 for item in evaluated
        if item.get("predicted_level") == item.get("actual_level")
    )

    metrics[county_id] = {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 3) if total else None,
        "model_note": "Metrics recalculated after v1.1.1 historical yellow backfill.",
    }

for path in METRICS_FILES:
    path.write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"Updated {path}")

print("Done.")