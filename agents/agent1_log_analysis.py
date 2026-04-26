"""
Agent 1: Log Analysis Agent
============================
Responsibilities:
- Reads all three log files (nginx-access.log, nginx-error.log, app-error.log)
- Uses Gemini-2.5-flash to identify the most likely root cause
- Extracts strongest log evidence
- Returns a structured JSON handoff for Agent 2

LLM Usage: YES — Gemini-2.5-flash is used to reason over the raw log text.
Prompt is fully visible below.
"""

from __future__ import annotations

import json
import os
import pathlib
import textwrap
from typing import Dict

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

LOG_DIR = pathlib.Path(__file__).parent.parent / "logs"

SYSTEM_PROMPT = textwrap.dedent("""
    You are a senior Site Reliability Engineer performing incident triage.
    You will be given three production log files from a Linux-hosted API:
    1. nginx-access.log  — Nginx access log with response codes and upstream timing
    2. nginx-error.log   — Nginx error log with upstream connectivity errors
    3. app-error.log     — Application error log from a Python/Gunicorn/SQLAlchemy stack

    Your task:
    - Identify the single most likely root cause of the incident
    - Extract the strongest 5-8 log lines that support your conclusion
    - Assign a confidence level: HIGH, MEDIUM, or LOW
    - Build a short chronological timeline of key events
    - List 1-2 plausible alternate hypotheses that could be ruled out
    - Produce a structured handoff for the next agent

    Respond ONLY with valid JSON matching this schema (no markdown fences):
    {
      "suspected_root_cause": "<concise one-sentence description>",
      "detailed_analysis": "<3-5 sentence technical explanation>",
      "evidence": [
        {"log_file": "<file>", "line": "<exact log line>", "significance": "<why this matters>"}
      ],
      "confidence": "HIGH|MEDIUM|LOW",
      "confidence_reasoning": "<why you chose this confidence level>",
      "timeline": [
        {"timestamp": "<HH:MM:SS>", "event": "<what happened>"}
      ],
      "alternate_hypotheses": [
        {"hypothesis": "<description>", "why_less_likely": "<reason>"}
      ],
      "handoff": {
        "issue_type": "<e.g. db_connection_pool_exhaustion>",
        "affected_component": "<e.g. SQLAlchemy QueuePool / PostgreSQL>",
        "affected_endpoints": ["<list of endpoints>"],
        "trigger_event": "<what likely triggered the cascade>",
        "keywords": ["<search terms for solution research>"]
      }
    }
""").strip()


def _load_logs() -> Dict[str, str]:
    """Load all three log files and return as a dict keyed by filename."""
    files = ["nginx-access.log", "nginx-error.log", "app-error.log"]
    contents: Dict[str, str] = {}
    for fname in files:
        path = LOG_DIR / fname
        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {path}")
        contents[fname] = path.read_text(encoding="utf-8")
    return contents


def _build_user_message(logs: Dict[str, str]) -> str:
    parts = ["Here are the three log files:\n"]
    for fname, content in logs.items():
        parts.append(f"--- BEGIN {fname} ---\n{content}\n--- END {fname} ---\n")
    return "\n".join(parts)


def run() -> dict:
    """
    Run the Log Analysis Agent.
    Returns the parsed JSON result dict.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key)

    print("[Agent 1] Loading log files...")
    logs = _load_logs()
    user_message = _build_user_message(logs)

    print("[Agent 1] Sending logs to Gemini-2.5-flash for analysis...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        ),
    )
    raw_text = response.text.strip()

    # Strip markdown fences if the model adds them despite the prompt
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        raw_text = raw_text.rsplit("```", 1)[0].strip()

    result = json.loads(raw_text)
    print(f"[Agent 1] Root cause identified: {result.get('suspected_root_cause')}")
    print(f"[Agent 1] Confidence: {result.get('confidence')}")
    return result


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
