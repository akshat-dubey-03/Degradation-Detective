import sqlite3
from datetime import datetime, timedelta
import json
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
                resolved_at TEXT,
                correlation_score REAL NOT NULL DEFAULT 0,
                scope TEXT NOT NULL DEFAULT 'single_service',
                narrated INTEGER NOT NULL DEFAULT 0 CHECK (narrated IN (0, 1)),
                last_seen_at TEXT,
                occurrence_count INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_service_resolved
            ON alerts (service_name, resolved);

            CREATE TABLE IF NOT EXISTS narrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id INTEGER NOT NULL,
                service_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                summary TEXT NOT NULL,
                root_cause TEXT NOT NULL,
                next_action TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY (alert_id) REFERENCES alerts(id)
            );

            CREATE INDEX IF NOT EXISTS idx_narrations_timestamp
            ON narrations (timestamp);
            """
        )
        _ensure_alert_columns(connection)
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_alerts_narrated_resolved
            ON alerts (narrated, resolved)
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


def create_alert(
    anomaly: Dict[str, Any],
    cooldown_seconds: int = 30,
    db_path: Union[Path, str] = DB_PATH,
) -> Dict[str, Any]:
    """Create or update an active alert for an anomaly, with lightweight deduping."""
    init_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    service_name = str(anomaly["service_name"])
    alert_type = str(anomaly["anomaly_type"])

    with get_connection(db_path) as connection:
        existing = connection.execute(
            """
            SELECT *
            FROM alerts
            WHERE service_name = ?
            AND alert_type = ?
            AND resolved = 0
            ORDER BY id DESC
            LIMIT 1
            """,
            (service_name, alert_type),
        ).fetchone()

        if existing is not None:
            alert = _alert_row_to_dict(existing)
            last_seen_at = alert.get("last_seen_at") or alert["timestamp"]
            elapsed = datetime.fromisoformat(now) - datetime.fromisoformat(last_seen_at)
            should_refresh = elapsed.total_seconds() >= cooldown_seconds

            connection.execute(
                """
                UPDATE alerts
                SET severity = ?,
                    message = ?,
                    correlation_score = ?,
                    scope = ?,
                    last_seen_at = ?,
                    occurrence_count = occurrence_count + ?
                WHERE id = ?
                """,
                (
                    anomaly["severity"],
                    anomaly["message"],
                    float(anomaly.get("correlation_score", 0.0)),
                    anomaly.get("scope", "single_service"),
                    now,
                    1 if should_refresh else 0,
                    alert["id"],
                ),
            )
            return get_alert_by_id(int(alert["id"]), db_path) or alert

        cursor = connection.execute(
            """
            INSERT INTO alerts (
                service_name,
                alert_type,
                severity,
                message,
                timestamp,
                correlation_score,
                scope,
                last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service_name,
                alert_type,
                anomaly["severity"],
                anomaly["message"],
                anomaly.get("timestamp", now),
                float(anomaly.get("correlation_score", 0.0)),
                anomaly.get("scope", "single_service"),
                now,
            ),
        )

    alert = get_alert_by_id(int(cursor.lastrowid), db_path)
    if alert is None:
        raise RuntimeError("alert insert succeeded but could not be read back")
    return alert


def get_alert_by_id(
    alert_id: int,
    db_path: Union[Path, str] = DB_PATH,
) -> Optional[Dict[str, Any]]:
    init_db(db_path)

    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM alerts WHERE id = ?",
            (alert_id,),
        ).fetchone()

    if row is None:
        return None
    return _alert_row_to_dict(row)


def get_active_alerts(db_path: Union[Path, str] = DB_PATH) -> List[Dict[str, Any]]:
    init_db(db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM alerts
            WHERE resolved = 0
            ORDER BY timestamp DESC, id DESC
            """
        ).fetchall()

    return [_alert_row_to_dict(row) for row in rows]


def get_alert_history(
    limit: int = 50,
    db_path: Union[Path, str] = DB_PATH,
) -> List[Dict[str, Any]]:
    init_db(db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM alerts
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_alert_row_to_dict(row) for row in rows]


def resolve_alert(
    service_name: str,
    db_path: Union[Path, str] = DB_PATH,
) -> int:
    init_db(db_path)
    resolved_at = datetime.now().isoformat(timespec="seconds")

    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE alerts
            SET resolved = 1,
                resolved_at = ?
            WHERE service_name = ?
            AND resolved = 0
            """,
            (resolved_at, service_name),
        )
        return int(cursor.rowcount)


def resolve_alerts_not_in(
    active_service_names: List[str],
    db_path: Union[Path, str] = DB_PATH,
) -> int:
    init_db(db_path)
    active = set(active_service_names)
    resolved_count = 0

    for service_name in SERVICE_NAMES:
        if service_name not in active:
            resolved_count += resolve_alert(service_name, db_path)

    return resolved_count


def get_unresolved_alerts_without_narrations(
    limit: int = 10,
    db_path: Union[Path, str] = DB_PATH,
) -> List[Dict[str, Any]]:
    init_db(db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM alerts
            WHERE resolved = 0
            AND narrated = 0
            ORDER BY severity DESC, timestamp ASC, id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_alert_row_to_dict(row) for row in rows]


def mark_alert_narrated(
    alert_id: int,
    db_path: Union[Path, str] = DB_PATH,
) -> None:
    init_db(db_path)

    with get_connection(db_path) as connection:
        connection.execute(
            "UPDATE alerts SET narrated = 1 WHERE id = ?",
            (alert_id,),
        )


def save_narration(
    narration: Dict[str, Any],
    db_path: Union[Path, str] = DB_PATH,
) -> int:
    init_db(db_path)
    timestamp = narration.get("timestamp") or datetime.now().isoformat(timespec="seconds")

    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO narrations (
                alert_id,
                service_name,
                severity,
                summary,
                root_cause,
                next_action,
                confidence,
                timestamp,
                source,
                details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(narration["alert_id"]),
                narration["service_name"],
                narration["severity"],
                narration["summary"],
                narration["root_cause"],
                narration["next_action"],
                float(narration.get("confidence", 0.0)),
                timestamp,
                narration.get("source", "fallback"),
                json.dumps(narration.get("details", {})),
            ),
        )

    return int(cursor.lastrowid)


def get_recent_narrations(
    limit: int = 20,
    db_path: Union[Path, str] = DB_PATH,
) -> List[Dict[str, Any]]:
    init_db(db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM narrations
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [_narration_row_to_dict(row) for row in rows]


def _metric_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    metric = dict(row)
    metric["is_error"] = bool(metric["is_error"])
    return metric


def _alert_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    alert = dict(row)
    alert["resolved"] = bool(alert["resolved"])
    alert["narrated"] = bool(alert["narrated"])
    return alert


def _narration_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    narration = dict(row)
    narration["details"] = json.loads(narration.pop("details_json") or "{}")
    return narration


def _ensure_alert_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(alerts)").fetchall()
    }
    desired_columns = {
        "correlation_score": "REAL NOT NULL DEFAULT 0",
        "scope": "TEXT NOT NULL DEFAULT 'single_service'",
        "narrated": "INTEGER NOT NULL DEFAULT 0 CHECK (narrated IN (0, 1))",
        "last_seen_at": "TEXT",
        "occurrence_count": "INTEGER NOT NULL DEFAULT 1",
    }

    for column_name, column_sql in desired_columns.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE alerts ADD COLUMN {column_name} {column_sql}"
            )


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
