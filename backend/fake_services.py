from random import random, uniform
from time import sleep
from typing import Dict, List

from fastapi import FastAPI, HTTPException

try:
    from backend.database import (
        get_active_alerts,
        get_alert_history,
        get_recent_metrics,
        get_recent_narrations,
        get_service_summaries,
    )
    from backend.models import (
        Alert,
        ChaosMode,
        ChaosRequest,
        Metric,
        MetricsHistory,
        MetricsSummary,
        Narration,
        ServiceName,
        ServiceResponse,
    )
except ImportError:
    from database import (
        get_active_alerts,
        get_alert_history,
        get_recent_metrics,
        get_recent_narrations,
        get_service_summaries,
    )
    from models import (
        Alert,
        ChaosMode,
        ChaosRequest,
        Metric,
        MetricsHistory,
        MetricsSummary,
        Narration,
        ServiceName,
        ServiceResponse,
    )


app = FastAPI(
    title="Degradation Detective Fake Services",
    description="Three simulated APIs plus chaos controls for observability demos.",
)

CHAOS_STATE: Dict[str, ChaosMode] = {
    "login": "healthy",
    "payment": "healthy",
    "search": "healthy",
}


def simulate_service(service: ServiceName, base_latency_ms: int) -> ServiceResponse:
    """Apply the current chaos mode before returning a fake service response."""
    mode = CHAOS_STATE[service]
    latency_ms = base_latency_ms + int(uniform(5, 35))

    if mode in ("slow", "both"):
        latency_ms += int(uniform(1200, 2500))

    sleep(latency_ms / 1000)

    if mode in ("errors", "both") and random() < 0.75:
        raise HTTPException(
            status_code=503,
            detail=f"{service} service is degraded by chaos mode: {mode}",
        )

    return ServiceResponse(
        service=service,
        status="ok",
        latency_hint_ms=latency_ms,
    )


@app.get("/")
def root() -> dict:
    return {
        "message": "Degradation Detective fake services are running",
        "docs": "/docs",
        "services": ["/login", "/payment", "/search"],
    }


@app.get("/login", response_model=ServiceResponse)
def login() -> ServiceResponse:
    return simulate_service("login", base_latency_ms=45)


@app.get("/payment", response_model=ServiceResponse)
def payment() -> ServiceResponse:
    return simulate_service("payment", base_latency_ms=80)


@app.get("/search", response_model=ServiceResponse)
def search() -> ServiceResponse:
    return simulate_service("search", base_latency_ms=60)


@app.post("/admin/chaos")
def set_chaos(request: ChaosRequest) -> dict:
    CHAOS_STATE[request.service] = request.mode
    return {
        "message": f"{request.service} set to {request.mode}",
        "chaos_state": CHAOS_STATE,
    }


@app.post("/admin/chaos/reset")
def reset_chaos() -> dict:
    for service in CHAOS_STATE:
        CHAOS_STATE[service] = "healthy"
    return {
        "message": "All services restored to healthy mode",
        "chaos_state": CHAOS_STATE,
    }


@app.get("/admin/status")
def chaos_status() -> dict:
    return {"chaos_state": CHAOS_STATE}


@app.get("/metrics/history", response_model=MetricsHistory)
def metrics_history(service: ServiceName, minutes: int = 10) -> MetricsHistory:
    metrics = [Metric(**row) for row in get_recent_metrics(service, minutes)]
    return MetricsHistory(
        service=service,
        minutes=minutes,
        count=len(metrics),
        metrics=metrics,
    )


@app.get("/metrics/summary", response_model=MetricsSummary)
def metrics_summary(minutes: int = 10) -> MetricsSummary:
    return MetricsSummary(
        window_minutes=minutes,
        services=get_service_summaries(minutes),
    )


@app.get("/alerts/active", response_model=List[Alert])
def active_alerts() -> List[Alert]:
    return [Alert(**alert) for alert in get_active_alerts()]


@app.get("/alerts/history", response_model=List[Alert])
def alert_history(limit: int = 50) -> List[Alert]:
    return [Alert(**alert) for alert in get_alert_history(limit=limit)]


@app.get("/narrations/recent", response_model=List[Narration])
def narrations_recent(limit: int = 20) -> List[Narration]:
    return [Narration(**narration) for narration in get_recent_narrations(limit=limit)]
