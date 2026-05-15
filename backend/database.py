import sqlite3
from pathlib import Path
from typing import Any, Dict, Union


DB_PATH = Path(__file__).resolve().with_name("metrics.db")


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


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
