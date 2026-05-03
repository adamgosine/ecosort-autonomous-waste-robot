"""
EcoSort - Flask analytics dashboard.

Reads classification events from classifications.json and renders a
real-time dashboard showing total items collected, daily averages,
classification accuracy, waste-type breakdown, and a live event feed.

Runs on the Raspberry Pi 4 alongside main.py. Open http://<pi-ip>:5000
in any browser on the same network to view.

Author: Adam Gosine
NYU Tandon EG-UY 1004 - Spring 2026
"""

import json
import os
from collections import Counter
from datetime import datetime

from flask import Flask, jsonify, render_template_string


app = Flask(__name__)
LOG_FILE = "classifications.json"


def load_classifications():
    """Load classification events from disk."""
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def compute_metrics(data):
    """Compute aggregate metrics from raw classification events."""
    total = len(data)
    breakdown = Counter(entry["type"] for entry in data)

    if total > 0:
        avg_conf = sum(e["confidence"] for e in data) / total
        accuracy_pct = round(avg_conf * 100, 1)
    else:
        accuracy_pct = 0.0

    breakdown_pct = {
        cls: (round(count / total * 100, 1) if total > 0 else 0)
        for cls, count in breakdown.items()
    }

    return {
        "total": total,
        "accuracy": accuracy_pct,
        "breakdown": dict(breakdown),
        "breakdown_pct": breakdown_pct,
        "recent": list(reversed(data[-10:])),
    }


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>EcoSort Dashboard</title>
  <meta http-equiv="refresh" content="2">
  <style>
    body {
      font-family: -apple-system, Arial, sans-serif;
      background: #f0f5f0;
      color: #1a3a1a;
      margin: 0;
      padding: 20px;
    }
    h1 { color: #1a3a1a; margin-bottom: 4px; }
    .subtitle { color: #5a7a5a; margin-bottom: 24px; font-size: 14px; }
    .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
    .card {
      background: white;
      padding: 20px;
      border-radius: 8px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .card-label { font-size: 12px; color: #5a7a5a; text-transform: uppercase; font-weight: 600; }
    .card-value { font-size: 32px; font-weight: 700; color: #1a3a1a; margin-top: 4px; }
    .panel {
      background: white;
      padding: 20px;
      border-radius: 8px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
      margin-bottom: 16px;
    }
    .panel h2 { color: #1a3a1a; margin: 0 0 16px 0; font-size: 18px; }
    table { width: 100%; border-collapse: collapse; }
    th { text-align: left; padding: 8px; border-bottom: 2px solid #e0eae0; font-size: 12px; color: #5a7a5a; }
    td { padding: 8px; border-bottom: 1px solid #f0f5f0; font-size: 14px; }
    .breakdown-row { display: flex; align-items: center; padding: 8px 0; }
    .breakdown-label { width: 100px; font-weight: 600; }
    .breakdown-bar {
      flex: 1;
      height: 24px;
      background: #e0eae0;
      border-radius: 4px;
      overflow: hidden;
      margin: 0 12px;
    }
    .breakdown-fill { height: 100%; background: #2d5a2d; }
    .breakdown-value { width: 60px; text-align: right; font-weight: 600; }
  </style>
</head>
<body>
  <h1>EcoSort Dashboard</h1>
  <div class="subtitle">Live classification feed - updated every 2 seconds</div>

  <div class="cards">
    <div class="card">
      <div class="card-label">Total Collected</div>
      <div class="card-value">{{ metrics.total }}</div>
    </div>
    <div class="card">
      <div class="card-label">Avg Confidence</div>
      <div class="card-value">{{ metrics.accuracy }}%</div>
    </div>
    <div class="card">
      <div class="card-label">Plastic</div>
      <div class="card-value">{{ metrics.breakdown.get('plastic', 0) }}</div>
    </div>
    <div class="card">
      <div class="card-label">Paper / Organic</div>
      <div class="card-value">{{ metrics.breakdown.get('paper', 0) }} / {{ metrics.breakdown.get('organic', 0) }}</div>
    </div>
  </div>

  <div class="panel">
    <h2>Waste Breakdown</h2>
    {% for cls, pct in metrics.breakdown_pct.items() %}
    <div class="breakdown-row">
      <div class="breakdown-label">{{ cls.title() }}</div>
      <div class="breakdown-bar"><div class="breakdown-fill" style="width: {{ pct }}%"></div></div>
      <div class="breakdown-value">{{ pct }}%</div>
    </div>
    {% endfor %}
  </div>

  <div class="panel">
    <h2>Recent Events</h2>
    <table>
      <tr>
        <th>Type</th>
        <th>Confidence</th>
        <th>Zone</th>
        <th>Timestamp</th>
      </tr>
      {% for event in metrics.recent %}
      <tr>
        <td>{{ event.type.title() }}</td>
        <td>{{ "%.1f"|format(event.confidence * 100) }}%</td>
        <td>{{ event.zone }}</td>
        <td>{{ event.timestamp.split("T")[1].split(".")[0] }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
</body>
</html>
"""


@app.route("/")
def index():
    data = load_classifications()
    metrics = compute_metrics(data)
    return render_template_string(HTML_TEMPLATE, metrics=metrics)


@app.route("/api/data")
def api_data():
    data = load_classifications()
    return jsonify(compute_metrics(data))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
