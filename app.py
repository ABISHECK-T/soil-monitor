from flask import Flask, render_template, request, jsonify
import csv
import os
from datetime import datetime

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

DATASETS = {
    "plant_vase1":   {"file": "plant_vase1.csv",   "label": "Plant Vase 1"},
    "plant_vase1_2": {"file": "plant_vase1_2.csv", "label": "Plant Vase 1 (Session 2)"},
    "plant_vase2":   {"file": "plant_vase2.csv",   "label": "Plant Vase 2"},
}

THRESHOLDS = {
    "critical_low": 0.15,
    "low":          0.30,
    "optimal_low":  0.50,
    "optimal_high": 0.80,
    "high":         0.90,
}

SENSOR_COLS = ["moisture0", "moisture1", "moisture2", "moisture3", "moisture4"]


def load_rows(key):
    """Read a dataset CSV into a list of dicts with lowercase, stripped keys."""
    path = os.path.join(DATA_DIR, DATASETS[key]["file"])
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for raw_row in reader:
            row = {k.strip().lower(): v for k, v in raw_row.items()}
            rows.append(row)
    return rows


def write_rows(key, rows, fieldnames):
    path = os.path.join(DATA_DIR, DATASETS[key]["file"])
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def get_status(value):
    v = float(value)
    if v < THRESHOLDS["critical_low"]:  return "critical_low"
    if v < THRESHOLDS["low"]:           return "low"
    if v < THRESHOLDS["optimal_low"]:   return "moderate"
    if v <= THRESHOLDS["optimal_high"]: return "optimal"
    if v <= THRESHOLDS["high"]:         return "high"
    return "saturated"


STATUS_LABELS = {
    "critical_low": "Critical – Water Immediately",
    "low":          "Low – Needs Water Soon",
    "moderate":     "Moderate – Monitor Closely",
    "optimal":      "Optimal – Good Moisture",
    "high":         "High – Moist Enough",
    "saturated":    "Saturated – No Watering Needed",
}


@app.route("/")
def index():
    return render_template("index.html", datasets=DATASETS)


@app.route("/api/summary/<dataset_key>")
def api_summary(dataset_key):
    if dataset_key not in DATASETS:
        return jsonify({"error": "Unknown dataset"}), 400

    rows = load_rows(dataset_key)
    if not rows:
        return jsonify({"error": "Dataset is empty"}), 400

    sensors = [c for c in SENSOR_COLS if c in rows[0]]
    first, last = rows[0], rows[-1]

    latest_reading = {}
    for s in sensors:
        v = float(last[s])
        status = get_status(v)
        latest_reading[s] = {
            "value": round(v, 3),
            "percent": round(v * 100, 1),
            "status": status,
            "label": STATUS_LABELS[status],
        }

    averages = {}
    for s in sensors:
        vals = [float(r[s]) for r in rows if r.get(s) not in (None, "")]
        averages[s] = round(sum(vals) / len(vals), 3) if vals else 0.0

    irrigation_events = sum(
        1 for r in rows
        if str(r.get("irrgation", "")).strip().lower() in ("true", "1")
    )

    data = {
        "dataset": DATASETS[dataset_key]["label"],
        "total_records": len(rows),
        "date_range": {
            "start": f"{int(float(first['year']))}-{int(float(first['month'])):02d}-{int(float(first['day'])):02d}",
            "end":   f"{int(float(last['year']))}-{int(float(last['month'])):02d}-{int(float(last['day'])):02d}",
        },
        "latest_reading": latest_reading,
        "averages": averages,
        "irrigation_events": irrigation_events,
    }
    return jsonify(data)


@app.route("/api/chart/<dataset_key>")
def api_chart(dataset_key):
    if dataset_key not in DATASETS:
        return jsonify({"error": "Unknown dataset"}), 400

    rows = load_rows(dataset_key)
    if not rows:
        return jsonify({"error": "Dataset is empty"}), 400

    sample = rows[-200:]
    sensors = [c for c in SENSOR_COLS if c in rows[0]]

    labels = [
        f"{int(float(r['hour'])):02d}:{int(float(r['minute'])):02d}"
        for r in sample
    ]
    sensors_data = {
        s: [round(float(r[s]) * 100, 1) for r in sample]
        for s in sensors
    }
    return jsonify({"labels": labels, "sensors": sensors_data})


@app.route("/api/feed", methods=["POST"])
def api_feed():
    body = request.get_json()
    dataset_key = body.get("dataset")
    if dataset_key not in DATASETS:
        return jsonify({"error": "Unknown dataset"}), 400

    now = datetime.now()
    try:
        values = {s: float(body.get(s, 0)) for s in SENSOR_COLS}
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid moisture values"}), 400

    for k, v in values.items():
        if not (0.0 <= v <= 1.0):
            return jsonify({"error": f"{k} must be between 0.00 and 1.00"}), 400

    rows = load_rows(dataset_key)
    fieldnames = list(rows[0].keys()) if rows else (
        ["year", "month", "day", "hour", "minute", "second"] + SENSOR_COLS + ["irrgation"]
    )

    new_row = {fn: "" for fn in fieldnames}
    new_row.update({
        "year": now.year, "month": now.month, "day": now.day,
        "hour": now.hour, "minute": now.minute, "second": now.second,
        **values,
        "irrgation": False,
    })
    rows.append(new_row)
    write_rows(dataset_key, rows, fieldnames)

    statuses = {
        k: {"value": v, "percent": round(v * 100, 1),
            "status": get_status(v), "label": STATUS_LABELS[get_status(v)]}
        for k, v in values.items()
    }
    return jsonify({"success": True, "statuses": statuses, "total_records": len(rows)})


@app.route("/api/irrigate", methods=["POST"])
def api_irrigate():
    body = request.get_json()
    dataset_key = body.get("dataset")
    if dataset_key not in DATASETS:
        return jsonify({"error": "Unknown dataset"}), 400

    rows = load_rows(dataset_key)
    if not rows:
        return jsonify({"error": "Dataset is empty"}), 400

    fieldnames = list(rows[0].keys())
    rows[-1]["irrgation"] = True
    write_rows(dataset_key, rows, fieldnames)
    return jsonify({"success": True, "message": "Irrigation event recorded"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print(f"Soil Moisture Monitor running at http://localhost:{port}")
    app.run(debug=debug, host="0.0.0.0", port=port)
