from random import random, uniform
from time import sleep
from typing import Dict, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


ServiceName = Literal["login", "payment", "search"]
ChaosMode = Literal["healthy", "slow", "errors", "both"]


class ChaosRequest(BaseModel):
    service: ServiceName
    mode: ChaosMode = Field(
        description="healthy = normal, slow = high latency, errors = failures, both = slow plus failures"
    )


class ServiceResponse(BaseModel):
    service: ServiceName
    status: str
    latency_hint_ms: int


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
