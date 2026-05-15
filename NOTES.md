# Interview Notes: Degradation Detective

## Why this project?
I wanted to build something beyond a typical CRUD app that demonstrates a deep understanding of production systems. Degradation Detective tackles a real-world problem: alert fatigue and incident response. By building a fake microservice ecosystem, a metric watcher, an anomaly detection engine, and an AI-powered narrator from scratch, I gained hands-on experience with the full observability lifecycle—from raw telemetry to actionable SRE insights.

## Anomaly Detection Explanation
The detection engine calculates a rolling baseline over a 10-minute window for each service. It flags anomalies using standard deviations for latency and threshold percentages for error rates. Instead of just firing independent alerts, it uses a correlation engine to detect "cascade failures" by grouping simultaneous anomalies across services. This reduces noise and groups related symptoms into a single root-cause analysis event.

## Why not Datadog?
While Datadog is excellent for enterprise use, relying on it abstracts away the complex logic of metric aggregation and threshold evaluation. Building this from scratch allowed me to deeply understand *how* time-series data is stored, queried, and evaluated in real-time. Additionally, integrating an LLM directly into the alert stream to generate plain-English "thinking-out-loud" SRE summaries provides immediate context that raw dashboards often lack.

## Scale
If this needed to scale to millions of requests per minute, the current SQLite + Polling approach would bottleneck. To scale:
1. **Data Layer**: Replace SQLite with a time-series database like Prometheus or InfluxDB.
2. **Ingestion**: Move from active polling to passive metric emission via OpenTelemetry, pushing to a message queue (Kafka) for async processing.
3. **Detection**: Move the detector out of the watcher loop into a stream-processing framework like Apache Flink.

## Hardest Part
The hardest part was tuning the anomaly detection thresholds and implementing the correlation logic. Initially, the system was too noisy, creating separate alerts for `search` and `payment` when both broke. Writing the `classify_scope()` function to recognize that they share a dependency or are cascading was challenging but incredibly rewarding once it worked.

## Deployment Links
- Backend: (Local for now / Render deployment placeholder)
- Frontend: (Local for now / Vercel deployment placeholder)
- Demo Video: (Coming soon)
