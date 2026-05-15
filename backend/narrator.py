import json
import os
from datetime import datetime
from typing import Any, Dict, List

import requests

try:
    from backend.database import (
        get_recent_metrics,
        get_recent_narrations,
        get_unresolved_alerts_without_narrations,
        mark_alert_narrated,
        save_narration,
    )
    from backend.models import NarrationResult
    from backend.prompts import build_narration_prompt
except ImportError:
    from database import (
        get_recent_metrics,
        get_recent_narrations,
        get_unresolved_alerts_without_narrations,
        mark_alert_narrated,
        save_narration,
    )
    from models import NarrationResult
    from prompts import build_narration_prompt


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
REQUEST_TIMEOUT_SECONDS = 15


def call_openrouter(prompt: str) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "Degradation Detective",
        },
        json={
            "model": os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL),
            "messages": [
                {
                    "role": "system",
                    "content": "You explain API incidents as concise JSON for an SRE dashboard.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["choices"][0]["message"]["content"])


def parse_llm_json(response_text: str) -> Dict[str, Any]:
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()

    parsed = json.loads(cleaned)
    required_fields = {"summary", "root_cause", "next_action", "confidence"}
    missing_fields = required_fields - parsed.keys()
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise ValueError(f"LLM response missing required field(s): {missing}")
    return parsed


def build_fallback_narration(
    alert: Dict[str, Any],
    metrics: List[Dict[str, Any]],
    reason: str = "LLM unavailable",
) -> Dict[str, Any]:
    latest = metrics[-1] if metrics else {}
    latency = latest.get("latency_ms", "unknown")
    status_code = latest.get("status_code", "unknown")
    service_name = alert["service_name"]
    alert_type = alert["alert_type"]

    templates = {
        "latency": {
            "summary": f"{service_name} is slower than expected at {latency}ms.",
            "root_cause": "The recent latency sample is above the rolling threshold.",
            "next_action": f"Check {service_name} dependencies and recent deploys first.",
        },
        "errors": {
            "summary": f"{service_name} is returning errors with status {status_code}.",
            "root_cause": "The watcher saw failing responses in the recent window.",
            "next_action": f"Inspect {service_name} logs around the latest failing request.",
        },
        "degrading": {
            "summary": f"{service_name} latency is trending upward.",
            "root_cause": "Recent samples show a worsening latency pattern.",
            "next_action": f"Watch {service_name} capacity and dependency latency next.",
        },
    }
    result = templates.get(alert_type, templates["latency"])
    result.update(
        {
            "confidence": 0.55,
            "source": "fallback",
            "details": {
                "fallback_reason": reason,
                "alert_type": alert_type,
                "correlation_score": alert.get("correlation_score", 0.0),
                "scope": alert.get("scope", "single_service"),
            },
        }
    )
    return result


def narrate_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    metrics = get_recent_metrics(alert["service_name"], minutes=10)
    prompt = build_narration_prompt(metrics_list=metrics[-20:], alert_list=[alert])
    source = "openrouter"

    try:
        parsed = parse_llm_json(call_openrouter(prompt))
    except (RuntimeError, requests.RequestException, KeyError, ValueError, json.JSONDecodeError) as exc:
        parsed = build_fallback_narration(alert, metrics, reason=str(exc))
        source = "fallback"

    result = NarrationResult(
        alert_id=alert["id"],
        service_name=alert["service_name"],
        severity=alert["severity"],
        summary=parsed["summary"],
        root_cause=parsed["root_cause"],
        next_action=parsed["next_action"],
        confidence=float(parsed.get("confidence", 0.0)),
        source=parsed.get("source", source),
        details=parsed.get("details", {}),
    )
    narration = result.dict()
    narration["timestamp"] = datetime.now().isoformat(timespec="seconds")
    narration_id = save_narration(narration)
    mark_alert_narrated(int(alert["id"]))
    narration["id"] = narration_id
    return narration


def narrator_loop_once(limit: int = 5) -> List[Dict[str, Any]]:
    alerts = get_unresolved_alerts_without_narrations(limit=limit)
    return [narrate_alert(alert) for alert in alerts]


def speak_narration(text: str) -> bool:
    if os.getenv("ENABLE_TTS") != "1":
        return False

    try:
        import pyttsx3
    except ImportError:
        return False

    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()
    return True


def recent_narrations(limit: int = 20) -> List[Dict[str, Any]]:
    return get_recent_narrations(limit=limit)


if __name__ == "__main__":
    narrations = narrator_loop_once()
    if not narrations:
        print("No unresolved alerts need narration.")
    for narration in narrations:
        print(json.dumps(narration, indent=2))
