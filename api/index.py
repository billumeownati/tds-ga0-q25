# api/index.py
import json
import statistics
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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

# ── CORS ─────────────────────────────────────────────────────────────────────
# Raw middleware forces Access-Control-Allow-Origin: * on EVERY response,
# including OPTIONS preflight. This is more reliable than CORSMiddleware on
# Vercel's serverless Python runtime.

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Expose-Headers": "Access-Control-Allow-Origin",
    "Access-Control-Max-Age": "86400",
}


@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    # Handle browser preflight immediately — never reaches route handlers
    if request.method == "OPTIONS":
        return JSONResponse(content={}, status_code=200, headers=CORS_HEADERS)
    response = await call_next(request)
    for key, value in CORS_HEADERS.items():
        response.headers[key] = value
    return response


# ── Data ──────────────────────────────────────────────────────────────────────
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "q-vercel-latency.json")
with open(DATA_PATH) as f:
    TELEMETRY = json.load(f)


# ── Schema ────────────────────────────────────────────────────────────────────
class AnalyticsRequest(BaseModel):
    regions: List[str]
    threshold_ms: float


# ── Logic ─────────────────────────────────────────────────────────────────────
def _compute(regions, threshold_ms):
    result = {}
    for region in regions:
        records = [r for r in TELEMETRY if r["region"] == region]
        if not records:
            result[region] = None
            continue
        latencies = [r["latency_ms"] for r in records]
        uptimes = [r["uptime_pct"] for r in records]
        result[region] = {
            "avg_latency": round(statistics.mean(latencies), 2),
            "p95_latency": round(_percentile(latencies, 95), 2),
            "avg_uptime": round(statistics.mean(uptimes), 2),
            "breaches": sum(1 for l in latencies if l > threshold_ms),
        }
    return result


# ── Routes ────────────────────────────────────────────────────────────────────
# Accept POST at /, /api, and /api/latency to match any portal URL format
@app.post("/")
@app.post("/api")
@app.post("/api/latency")
def analytics(req: AnalyticsRequest):
    return _compute(req.regions, req.threshold_ms)


@app.get("/")
@app.get("/api")
@app.get("/api/latency")
def read_root():
    return {"message": "eShopCo Latency Analytics API — POST with {regions, threshold_ms}"}
