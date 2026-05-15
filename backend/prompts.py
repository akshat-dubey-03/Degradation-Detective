from pathlib import Path
from typing import Any, Dict, List


PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "sre_v1.txt"


def build_narration_prompt(
    metrics_list: List[Dict[str, Any]],
    alert_list: List[Dict[str, Any]],
) -> str:
    """Build the JSON-only SRE narration prompt sent to the LLM."""
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        metrics=metrics_list,
        alerts=alert_list,
    )
