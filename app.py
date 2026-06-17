from flask import Flask, render_template, request, jsonify
import pandas as pd
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

def load_dataset(key):
    path = os.path.join(DATA_DIR, DATASETS[key]["file"])
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    return df

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
    df = load_dataset(dataset_key)
    sensors = [c for c in df.columns if c.startswith("moisture")]
    latest = df.iloc[-1]
    data = {
        "dataset": DATASETS[dataset_key]["label"],
        "total_records": len(df),
        "date_range": {
            "start": f"{int(df.iloc[0]['year'])}-{int(df.iloc[0]['month']):02d}-{int(df.iloc[0]['day']):02d}",
            "end":   f"{int(df.iloc[-1]['year'])}-{int(df.iloc[-1]['month']):02d}-{int(df.iloc[-1]['day']):02d}",
        },
        "latest_reading": {
            s: {
                "value": round(float(latest[s]), 3),
                "percent": round(float(latest[s]) * 100, 1),
                "status": get_status(latest[s]),
                "label": STATUS_LABELS[get_status(latest[s])],
            } for s in sensors
        },
        "averages": {s: round(float(df[s].mean()), 3) for s in sensors},
        "irrigation_events": int(df["irrgation"].sum()) if "irrgation" in df.columns else 0,
    }
    return jsonify(data)

@app.route("/api/chart/<dataset_key>")
def api_chart(dataset_key):
    if dataset_key not in DATASETS:
        return jsonify({"error": "Unknown dataset"}), 400
    df = load_dataset(dataset_key)
    sample = df.tail(200).copy()
    sensors = [c for c in df.columns if c.startswith("moisture")]
    result = {
        "labels": [
            f"{int(r['hour']):02d}:{int(r['minute']):02d}"
            for _, r in sample.iterrows()
        ],
        "sensors": {
            s: [round(float(v) * 100, 1) for v in sample[s]]
            for s in sensors
        }
    }
    return jsonify(result)

@app.route("/api/feed", methods=["POST"])
def api_feed():
    body = request.get_json()
    dataset_key = body.get("dataset")
    if dataset_key not in DATASETS:
        return jsonify({"error": "Unknown dataset"}), 400
    now = datetime.now()
    try:
        values = {
            "moisture0": float(body.get("moisture0", 0)),
            "moisture1": float(body.get("moisture1", 0)),
            "moisture2": float(body.get("moisture2", 0)),
            "moisture3": float(body.get("moisture3", 0)),
            "moisture4": float(body.get("moisture4", 0)),
        }
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid moisture values"}), 400
    for k, v in values.items():
        if not (0.0 <= v <= 1.0):
            return jsonify({"error": f"{k} must be between 0.00 and 1.00"}), 400
    path = os.path.join(DATA_DIR, DATASETS[dataset_key]["file"])
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    new_row = {
        "year": now.year, "month": now.month, "day": now.day,
        "hour": now.hour, "minute": now.minute, "second": now.second,
        **values, "irrgation": False,
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(path, index=False)
    statuses = {k: {"value": v, "percent": round(v*100,1),
                    "status": get_status(v), "label": STATUS_LABELS[get_status(v)]}
                for k, v in values.items()}
    return jsonify({"success": True, "statuses": statuses, "total_records": len(df)})

@app.route("/api/irrigate", methods=["POST"])
def api_irrigate():
    body = request.get_json()
    dataset_key = body.get("dataset")
    if dataset_key not in DATASETS:
        return jsonify({"error": "Unknown dataset"}), 400
    path = os.path.join(DATA_DIR, DATASETS[dataset_key]["file"])
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip().str.lower()
    df.loc[df.index[-1], "irrgation"] = True
    df.to_csv(path, index=False)
    return jsonify({"success": True, "message": "Irrigation event recorded"})

if __name__ == "__main__":
    print("Soil Moisture Monitor running at http://localhost:5000")
    app.run(debug=True, port=5000)
