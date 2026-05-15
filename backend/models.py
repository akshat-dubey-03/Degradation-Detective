from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ServiceName = Literal["login", "payment", "search"]
ChaosMode = Literal["healthy", "slow", "errors", "both"]


class ChaosRequest(BaseModel):
    service: ServiceName
    mode: ChaosMode = Field(
        description="healthy = normal, slow = high latency, errors = failures, both = slow plus failures"
    )


class ChaosConfig(BaseModel):
    chaos_state: Dict[ServiceName, ChaosMode]


class ServiceResponse(BaseModel):
    service: ServiceName
    status: str
    latency_hint_ms: int


class Metric(BaseModel):
    id: Optional[int] = None
    service_name: ServiceName
    endpoint: str
    status_code: int
    latency_ms: int
    timestamp: str
    is_error: bool


class MetricsHistory(BaseModel):
    service: ServiceName
    minutes: int
    count: int
    metrics: List[Metric]


class ServiceSummary(BaseModel):
    service_name: ServiceName
    status: str
    average_latency_ms: float
    error_rate_percent: float
    request_count: int
    latest_metric: Optional[Metric] = None


class MetricsSummary(BaseModel):
    window_minutes: int
    services: Dict[ServiceName, ServiceSummary]


class Alert(BaseModel):
    id: Optional[int] = None
    service_name: ServiceName
    alert_type: str
    severity: str
    message: str
    timestamp: str
    resolved: bool = False
    resolved_at: Optional[str] = None
    correlation_score: float = 0.0
    scope: str = "single_service"
    narrated: bool = False
    last_seen_at: Optional[str] = None
    occurrence_count: int = 1


class Anomaly(BaseModel):
    service_name: ServiceName
    anomaly_type: str
    severity: str
    message: str
    current_value: float
    baseline_value: float
    correlation_score: float = 0.0


class NarrationResult(BaseModel):
    alert_id: Optional[int] = None
    service_name: ServiceName
    severity: str
    summary: str
    root_cause: str
    next_action: str
    confidence: float = 0.0
    source: str = "fallback"
    details: Dict[str, Any] = {}


class Narration(BaseModel):
    id: Optional[int] = None
    alert_id: int
    service_name: ServiceName
    severity: str
    summary: str
    root_cause: str
    next_action: str
    confidence: float
    timestamp: str
    source: str
    details: Dict[str, Any] = {}
