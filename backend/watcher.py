from datetime import datetime
from time import perf_counter, sleep
from typing import Dict, List

import requests

try:
    from backend.detector import detect_all, sync_alerts_from_detection
    from backend.database import DB_PATH, get_active_alerts, init_db, save_metric
    from backend.narrator import narrator_loop_once
except ImportError:
    from detector import detect_all, sync_alerts_from_detection
    from database import DB_PATH, get_active_alerts, init_db, save_metric
    from narrator import narrator_loop_once


BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_SECONDS = 2
TIMEOUT_SECONDS = 4

SERVICES: List[Dict[str, str]] = [
    {"name": "login", "endpoint": "/login"},
    {"name": "payment", "endpoint": "/payment"},
    {"name": "search", "endpoint": "/search"},
]


def ping_service(service: Dict[str, str]) -> Dict[str, object]:
    """Call one fake service and return the metric fields needed by the watcher."""
    url = f"{BASE_URL}{service['endpoint']}"
    started_at = perf_counter()

    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
        latency_ms = int((perf_counter() - started_at) * 1000)

        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "service_name": service["name"],
            "endpoint": service["endpoint"],
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "is_error": response.status_code >= 400,
        }
    except requests.RequestException:
        latency_ms = int((perf_counter() - started_at) * 1000)

        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "service_name": service["name"],
            "endpoint": service["endpoint"],
            "status_code": 0,
            "latency_ms": latency_ms,
            "is_error": True,
        }


def format_metric(metric: Dict[str, object]) -> str:
    status_icon = "X" if metric["is_error"] else "OK"
    service_name = str(metric["service_name"]).upper()
    status_code = metric["status_code"]
    latency_ms = metric["latency_ms"]

    return f"{service_name:<8} | {status_code!s:<3} | {latency_ms!s:>5}ms | {status_icon}"


def format_detection(detection: Dict[str, object]) -> str:
    anomalies = detection["anomalies"]
    scope = detection["scope"]

    if not anomalies:
        return "Anomalies: none"

    lines = [
        "Anomalies: "
        f"{scope['scope']} "
        f"(correlation {scope['correlation_score']})"
    ]

    for anomaly in anomalies:
        lines.append(
            "  - "
            f"{anomaly['service_name']} "
            f"{anomaly['anomaly_type']} "
            f"{anomaly['severity']}: "
            f"{anomaly['message']}"
        )

    return "\n".join(lines)


def format_active_alerts() -> str:
    alerts = get_active_alerts()

    if not alerts:
        return "Active alerts: none"

    lines = [f"Active alerts: {len(alerts)}"]
    for alert in alerts:
        lines.append(
            "  - "
            f"#{alert['id']} {alert['service_name']} "
            f"{alert['alert_type']} {alert['severity']} "
            f"(seen {alert['occurrence_count']}x, narrated={alert['narrated']})"
        )
    return "\n".join(lines)


def run_watcher() -> None:
    init_db()
    print("Degradation Detective watcher started")
    print(f"Polling {BASE_URL} every {POLL_INTERVAL_SECONDS}s. Press Ctrl+C to stop.\n")
    print(f"Saving metrics to {DB_PATH}\n")

    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}]")

        for service in SERVICES:
            metric = ping_service(service)
            save_metric(metric)
            print(format_metric(metric))

        detection = detect_all()
        sync_alerts_from_detection(detection)
        new_narrations = narrator_loop_once()

        print(format_detection(detection))
        print(format_active_alerts())
        if new_narrations:
            print(f"Narrations created: {len(new_narrations)}")
        print()
        sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        run_watcher()
    except KeyboardInterrupt:
        print("\nWatcher stopped.")
