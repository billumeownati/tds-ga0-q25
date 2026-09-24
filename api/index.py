# api/index.py
import json
import statistics
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List


def _percentile(data: list, pct: float) -> float:
    """Return the p-th percentile of data using linear interpolation (numpy-free)."""
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n == 1:
        return sorted_data[0]
    index = (pct / 100) * (n - 1)
    lower = int(index)
    upper = lower + 1
    frac = index - lower
    if upper >= n:
        return sorted_data[-1]
    return sorted_data[lower] + frac * (sorted_data[upper] - sorted_data[lower])


app = FastAPI()

# Enable CORS for POST requests from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load telemetry data from the JSON file (baked in at deploy time)
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "q-vercel-latency.json")
with open(DATA_PATH) as f:
    TELEMETRY = json.load(f)


class AnalyticsRequest(BaseModel):
    regions: List[str]
    threshold_ms: float


@app.post("/api")
def analytics(req: AnalyticsRequest):
    result = {}
    for region in req.regions:
        # Filter records for this region
        records = [r for r in TELEMETRY if r["region"] == region]

        if not records:
            result[region] = None
            continue

        latencies = [r["latency_ms"] for r in records]
        uptimes = [r["uptime_pct"] for r in records]

        avg_latency = round(statistics.mean(latencies), 2)
        # 95th percentile using linear interpolation (same as numpy default)
        p95_latency = round(_percentile(latencies, 95), 2)
        avg_uptime = round(statistics.mean(uptimes), 2)
        breaches = sum(1 for l in latencies if l > req.threshold_ms)

        result[region] = {
            "avg_latency": avg_latency,
            "p95_latency": p95_latency,
            "avg_uptime": avg_uptime,
            "breaches": breaches,
        }

    return result


@app.get("/")
def read_root():
    return {"message": "eShopCo Latency Analytics API. POST to /api"}
