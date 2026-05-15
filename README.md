# Degradation Detective

Real-time API health monitor with anomaly detection and AI narration. Built as a 34-day observability project.

## Architecture

Degradation Detective starts with three fake services: `login`, `payment`, and `search`. They run in FastAPI and can be switched into healthy, slow, error, or combined chaos modes.

The watcher polls those services every two seconds, records status codes and latency, and saves every ping to SQLite. The same FastAPI app exposes historical and summary metrics so later dashboard work can read from a stable JSON API.

The detector layer reads recent metrics from SQLite, calculates a rolling baseline, flags latency and error anomalies, and classifies whether an incident is isolated to one service or correlated across multiple services.

## Backend Commands

Install dependencies:

```bash
python -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

Run the fake services and metrics API:

```bash
uvicorn backend.fake_services:app --reload
```

Run the watcher in a second terminal:

```bash
python backend/watcher.py
```

Print detector baselines and current anomalies:

```bash
python backend/detector.py
```

## API Endpoints

- `GET /login`, `GET /payment`, `GET /search`
- `POST /admin/chaos`
- `POST /admin/chaos/reset`
- `GET /admin/status`
- `GET /metrics/history?service=login&minutes=10`
- `GET /metrics/summary?minutes=10`
