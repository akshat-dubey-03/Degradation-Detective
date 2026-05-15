import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


DB_PATH = Path(__file__).resolve().with_name("metrics.db")
SERVICE_NAMES = ("login", "payment", "search")


def get_connection(db_path: Union[Path, str] = DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: Union[Path, str] = DB_PATH) -> None:
    """Create the metrics and alerts tables if they do not already exist."""
    with get_connection(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                latency_ms INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                is_error INTEGER NOT NULL CHECK (is_error IN (0, 1))
            );

            CREATE INDEX IF NOT EXISTS idx_metrics_service_timestamp
            ON metrics (service_name, timestamp);

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                resolved INTEGER NOT NULL DEFAULT 0 CHECK (resolved IN (0, 1)),
                resolved_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_service_resolved
            ON alerts (service_name, resolved);
            """
        )


def save_metric(
    metric: Dict[str, Any],
    db_path: Union[Path, str] = DB_PATH,
) -> int:
    """Persist one watcher metric and return its database row id."""
    required_fields = {
        "service_name",
        "endpoint",
        "status_code",
        "latency_ms",
        "timestamp",
        "is_error",
    }
    missing_fields = required_fields - metric.keys()

    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise ValueError(f"metric is missing required field(s): {missing}")

    init_db(db_path)

    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO metrics (
                service_name,
                endpoint,
                status_code,
                latency_ms,
                timestamp,
                is_error
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                metric["service_name"],
                metric["endpoint"],
                int(metric["status_code"]),
                int(metric["latency_ms"]),
                metric["timestamp"],
                1 if metric["is_error"] else 0,
            ),
        )
        return int(cursor.lastrowid)


def get_recent_metrics(
    service_name: str,
    minutes: int,
    db_path: Union[Path, str] = DB_PATH,
) -> List[Dict[str, Any]]:
    cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")

    init_db(db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                service_name,
                endpoint,
                status_code,
                latency_ms,
                timestamp,
                is_error
            FROM metrics
            WHERE service_name = ?
            AND timestamp >= ?
            ORDER BY timestamp ASC, id ASC
            """,
            (service_name, cutoff),
        ).fetchall()

    return [_metric_row_to_dict(row) for row in rows]


def get_latest_metric(
    service_name: str,
    db_path: Union[Path, str] = DB_PATH,
) -> Optional[Dict[str, Any]]:
    init_db(db_path)

    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                id,
                service_name,
                endpoint,
                status_code,
                latency_ms,
                timestamp,
                is_error
            FROM metrics
            WHERE service_name = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (service_name,),
        ).fetchone()

    if row is None:
        return None

    return _metric_row_to_dict(row)


def get_average_latency(
    service_name: str,
    minutes: int,
    db_path: Union[Path, str] = DB_PATH,
) -> float:
    cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")

    init_db(db_path)

    with get_connection(db_path) as connection:
        average_latency = connection.execute(
            """
            SELECT AVG(latency_ms)
            FROM metrics
            WHERE service_name = ?
            AND timestamp >= ?
            """,
            (service_name, cutoff),
        ).fetchone()[0]

    return float(average_latency or 0.0)


def get_error_rate(
    service_name: str,
    minutes: int,
    db_path: Union[Path, str] = DB_PATH,
) -> float:
    cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")

    init_db(db_path)

    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                SUM(is_error) AS error_count
            FROM metrics
            WHERE service_name = ?
            AND timestamp >= ?
            """,
            (service_name, cutoff),
        ).fetchone()

    total_count = int(row["total_count"] or 0)
    error_count = int(row["error_count"] or 0)

    if total_count == 0:
        return 0.0

    return (error_count / total_count) * 100


def get_metric_count(
    service_name: str,
    minutes: int,
    db_path: Union[Path, str] = DB_PATH,
) -> int:
    cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")

    init_db(db_path)

    with get_connection(db_path) as connection:
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM metrics
            WHERE service_name = ?
            AND timestamp >= ?
            """,
            (service_name, cutoff),
        ).fetchone()[0]

    return int(count or 0)


def get_service_summary(
    service_name: str,
    minutes: int = 10,
    db_path: Union[Path, str] = DB_PATH,
) -> Dict[str, Any]:
    average_latency = get_average_latency(service_name, minutes, db_path)
    error_rate = get_error_rate(service_name, minutes, db_path)
    request_count = get_metric_count(service_name, minutes, db_path)
    latest_metric = get_latest_metric(service_name, db_path)

    if latest_metric is None:
        status = "unknown"
    elif latest_metric["is_error"] or error_rate >= 25:
        status = "degraded"
    elif average_latency >= 1000:
        status = "slow"
    else:
        status = "healthy"

    return {
        "service_name": service_name,
        "status": status,
        "average_latency_ms": round(average_latency, 2),
        "error_rate_percent": round(error_rate, 2),
        "request_count": request_count,
        "latest_metric": latest_metric,
    }


def get_service_summaries(
    minutes: int = 10,
    db_path: Union[Path, str] = DB_PATH,
) -> Dict[str, Dict[str, Any]]:
    return {
        service_name: get_service_summary(service_name, minutes, db_path)
        for service_name in SERVICE_NAMES
    }


def _metric_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    metric = dict(row)
    metric["is_error"] = bool(metric["is_error"])
    return metric


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
