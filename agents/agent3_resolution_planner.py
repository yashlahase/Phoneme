"""
Agent 3: Resolution Planner Agent
===================================
Responsibilities:
- Receives Agent 1 findings AND Agent 2 solution options
- Uses Gemini-2.5-flash to evaluate, select the safest solution, and generate
  step-by-step operator instructions
- Produces pre-checks, ordered remediation steps, validation steps, and rollback notes

LLM Usage: YES — Gemini-2.5-flash is used to synthesize the best plan.
Prompt is fully visible below.
"""

from __future__ import annotations

import json
import os
import textwrap

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = textwrap.dedent("""
    You are a senior Site Reliability Engineer writing an incident response runbook.
    You will receive:
    1. Agent 1's incident diagnosis (root cause, evidence, confidence, timeline)
    2. Agent 2's researched solutions (multiple options with pros, cons, risk ratings, sources)

    Your task is to:
    - Select the single safest and most practical solution for the ACTIVE incident
    - Write a precise, ordered list of operator actions
    - Include pre-checks (things to verify BEFORE acting)
    - Include post-fix validation checks (how to confirm the fix worked)
    - Include rollback / safety notes (what to do if the fix makes things worse)
    - Write a short executive summary of the incident

    Rules:
    - Prioritise rollback of bad deployments over configuration changes
    - Never recommend actions that could worsen a live outage (e.g. restarting the DB)
    - Be specific: include exact commands, file paths, config keys, and expected outputs
    - Keep each step atomic — one action per step

    Respond ONLY with valid JSON matching this schema (no markdown fences):
    {
      "executive_summary": "<2-3 sentence summary for a non-technical stakeholder>",
      "best_solution": "<title of chosen solution>",
      "selection_rationale": "<why this solution was chosen over alternatives>",
      "pre_checks": [
        {"step": 1, "action": "<what to verify>", "command": "<exact command if applicable>", "expected": "<what you should see>"}
      ],
      "remediation_steps": [
        {"step": 1, "action": "<what to do>", "command": "<exact command if applicable>", "note": "<any caveats>"}
      ],
      "validation_steps": [
        {"step": 1, "action": "<what to check>", "command": "<exact command if applicable>", "expected": "<expected healthy state>"}
      ],
      "rollback_notes": [
        "<what to do if this step fails or worsens the situation>"
      ],
      "secondary_actions": [
        "<recommended follow-up actions after immediate incident is resolved>"
      ],
      "incident_classification": {
        "severity": "P1|P2|P3",
        "category": "<e.g. Database Connectivity>",
        "likely_trigger": "<deployment or config change that caused this>"
      }
    }
""").strip()


def _build_user_message(agent1_result: dict, agent2_result: dict) -> str:
    return textwrap.dedent(f"""
        ## Agent 1 — Incident Diagnosis

        {json.dumps(agent1_result, indent=2)}

        ## Agent 2 — Researched Solutions

        {json.dumps(agent2_result, indent=2)}

        Please produce the resolution plan now.
    """).strip()


def run(agent1_result: dict, agent2_result: dict) -> dict:
    """
    Run the Resolution Planner Agent.
    Returns the parsed JSON resolution plan dict.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key)

    print("[Agent 3] Sending Agent 1 + Agent 2 outputs to Gemini-2.5-flash for planning...")
    user_message = _build_user_message(agent1_result, agent2_result)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        ),
    )
    raw_text = response.text.strip()

    # Strip markdown fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        raw_text = raw_text.rsplit("```", 1)[0].strip()

    result = json.loads(raw_text)
    print(f"[Agent 3] Best solution selected: {result.get('best_solution')}")
    print(f"[Agent 3] Severity: {result.get('incident_classification', {}).get('severity')}")
    return result


if __name__ == "__main__":
    import sys
    import pathlib
    print("[Agent 3] Running standalone — requires agent1.json and agent2.json as CLI args")
    if len(sys.argv) == 3:
        a1 = json.loads(pathlib.Path(sys.argv[1]).read_text())
        a2 = json.loads(pathlib.Path(sys.argv[2]).read_text())
        result = run(a1, a2)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python3 agent3_resolution_planner.py agent1.json agent2.json")
