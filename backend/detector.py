from datetime import datetime
from typing import Any, Dict, List

try:
    from backend.database import (
        SERVICE_NAMES,
        create_alert,
        get_average_latency,
        get_error_rate,
        get_latest_metric,
        get_metric_count,
        get_recent_metrics,
        resolve_alerts_not_in,
    )
except ImportError:
    from database import (
        SERVICE_NAMES,
        create_alert,
        get_average_latency,
        get_error_rate,
        get_latest_metric,
        get_metric_count,
        get_recent_metrics,
        resolve_alerts_not_in,
    )


BASELINE_WINDOW_MINUTES = 10
LATENCY_MULTIPLIER = 2.0
LATENCY_ABSOLUTE_MS = 1000
ERROR_RATE_THRESHOLD_PERCENT = 35


def calculate_baseline(
    service_name: str,
    window_minutes: int = BASELINE_WINDOW_MINUTES,
) -> Dict[str, Any]:
    """Return recent baseline stats for one service."""
    return {
        "service_name": service_name,
        "window_minutes": window_minutes,
        "average_latency_ms": round(
            get_average_latency(service_name, window_minutes),
            2,
        ),
        "error_rate_percent": round(get_error_rate(service_name, window_minutes), 2),
        "sample_count": get_metric_count(service_name, window_minutes),
    }


def get_current_status(service_name: str) -> Dict[str, Any]:
    latest_metric = get_latest_metric(service_name)
    baseline = calculate_baseline(service_name)

    status = "unknown"
    if latest_metric is not None:
        status = "degraded" if latest_metric["is_error"] else "healthy"

    return {
        "service_name": service_name,
        "status": status,
        "latest_metric": latest_metric,
        "baseline": baseline,
    }


def check_latency_anomaly(service_name: str) -> Dict[str, Any]:
    latest_metric = get_latest_metric(service_name)
    baseline = calculate_baseline(service_name)

    if latest_metric is None:
        return {}

    current_latency = float(latest_metric["latency_ms"])
    baseline_latency = float(baseline["average_latency_ms"])
    dynamic_threshold = baseline_latency * LATENCY_MULTIPLIER
    threshold = max(dynamic_threshold, LATENCY_ABSOLUTE_MS)

    if current_latency < threshold:
        return {}

    severity = classify_severity(
        anomaly_type="latency",
        current_value=current_latency,
        threshold=threshold,
    )
    return {
        "service_name": service_name,
        "anomaly_type": "latency",
        "severity": severity,
        "message": (
            f"{service_name} latency is {int(current_latency)}ms, "
            f"above the {int(threshold)}ms anomaly threshold"
        ),
        "current_value": current_latency,
        "baseline_value": baseline_latency,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "correlation_score": 0.0,
    }


def check_error_anomaly(service_name: str) -> Dict[str, Any]:
    latest_metric = get_latest_metric(service_name)
    baseline = calculate_baseline(service_name)

    if latest_metric is None:
        return {}

    current_error_rate = float(baseline["error_rate_percent"])
    latest_is_error = bool(latest_metric["is_error"])

    if not latest_is_error and current_error_rate < ERROR_RATE_THRESHOLD_PERCENT:
        return {}

    severity = classify_severity(
        anomaly_type="errors",
        current_value=current_error_rate,
        threshold=ERROR_RATE_THRESHOLD_PERCENT,
    )
    return {
        "service_name": service_name,
        "anomaly_type": "errors",
        "severity": severity,
        "message": (
            f"{service_name} is returning errors "
            f"({round(current_error_rate, 2)}% in the recent window)"
        ),
        "current_value": current_error_rate,
        "baseline_value": 0.0,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "correlation_score": 0.0,
    }


def check_degrading_pattern(service_name: str) -> Dict[str, Any]:
    metrics = get_recent_metrics(service_name, minutes=5)

    if len(metrics) < 5:
        return {}

    recent = metrics[-5:]
    latencies = [int(metric["latency_ms"]) for metric in recent]
    increases = sum(
        1 for index in range(1, len(latencies)) if latencies[index] > latencies[index - 1]
    )
    baseline = calculate_baseline(service_name)
    baseline_latency = float(baseline["average_latency_ms"])
    current_latency = float(latencies[-1])

    if increases < 3 or current_latency < max(400, baseline_latency * 1.4):
        return {}

    severity = classify_severity(
        anomaly_type="degrading",
        current_value=current_latency,
        threshold=max(400, baseline_latency * 1.4),
    )
    return {
        "service_name": service_name,
        "anomaly_type": "degrading",
        "severity": severity,
        "message": (
            f"{service_name} latency is trending upward "
            f"across the last {len(recent)} samples"
        ),
        "current_value": current_latency,
        "baseline_value": baseline_latency,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "correlation_score": 0.0,
    }


def classify_severity(anomaly_type: str, current_value: float, threshold: float) -> str:
    if anomaly_type == "errors":
        if current_value >= 75:
            return "critical"
        if current_value >= threshold:
            return "warning"
        return "info"

    if current_value >= threshold * 1.8:
        return "critical"
    if current_value >= threshold:
        return "warning"
    return "info"


def check_cascade_failure(anomalies: List[Dict[str, Any]]) -> Dict[str, Any]:
    affected_services = sorted(
        {anomaly["service_name"] for anomaly in anomalies if anomaly}
    )

    if len(affected_services) < 2:
        return {
            "is_cascade": False,
            "affected_services": affected_services,
            "correlation_score": 0.0,
        }

    correlation_score = min(1.0, len(affected_services) / len(SERVICE_NAMES))
    return {
        "is_cascade": True,
        "affected_services": affected_services,
        "correlation_score": round(correlation_score, 2),
        "message": (
            "Multiple services are degraded together: "
            + ", ".join(affected_services)
        ),
    }


def classify_scope(anomalies: List[Dict[str, Any]]) -> Dict[str, Any]:
    cascade = check_cascade_failure(anomalies)

    if not anomalies:
        return {
            "scope": "healthy",
            "correlation_score": 0.0,
            "affected_services": [],
        }

    if cascade["is_cascade"]:
        scope = "cascade"
        correlation_score = cascade["correlation_score"]
    else:
        scope = "single_service"
        correlation_score = 0.33

    for anomaly in anomalies:
        anomaly["correlation_score"] = correlation_score
        anomaly["scope"] = scope

    return {
        "scope": scope,
        "correlation_score": correlation_score,
        "affected_services": cascade["affected_services"],
    }


def detect_all() -> Dict[str, Any]:
    anomalies: List[Dict[str, Any]] = []

    for service_name in SERVICE_NAMES:
        latency_anomaly = check_latency_anomaly(service_name)
        if latency_anomaly:
            anomalies.append(latency_anomaly)

        error_anomaly = check_error_anomaly(service_name)
        if error_anomaly:
            anomalies.append(error_anomaly)

        degrading_anomaly = check_degrading_pattern(service_name)
        if degrading_anomaly:
            anomalies.append(degrading_anomaly)

    scope = classify_scope(anomalies)
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "scope": scope,
        "anomalies": anomalies,
    }


def sync_alerts_from_detection(detection: Dict[str, Any]) -> Dict[str, Any]:
    anomalies = detection["anomalies"]
    active_service_names = sorted({anomaly["service_name"] for anomaly in anomalies})
    created_or_updated = [create_alert(anomaly) for anomaly in anomalies]
    resolved_count = resolve_alerts_not_in(active_service_names)

    return {
        "created_or_updated": created_or_updated,
        "resolved_count": resolved_count,
    }


if __name__ == "__main__":
    for service in SERVICE_NAMES:
        print(calculate_baseline(service))
    print(detect_all())
