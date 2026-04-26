"""
main.py — Orchestrator for the 3-Agent Incident Response System
================================================================
Runs Agent 1 → Agent 2 → Agent 3 in sequence.
Passes structured JSON outputs as handoffs between agents.
Writes the final incident report to sample_output/incident_report.json.
"""

import json
import pathlib
import sys
import time
from datetime import datetime

# Ensure agents/ is importable
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from agents import agent1_log_analysis, agent2_solution_research, agent3_resolution_planner

OUTPUT_DIR = pathlib.Path(__file__).parent / "sample_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def banner(text: str) -> None:
    width = 70
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def main() -> None:
    start_time = time.time()
    print(f"\n🚨  Incident Response System — started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── Agent 1 ──────────────────────────────────────────────────────────────
    banner("AGENT 1: Log Analysis Agent")
    agent1_result = agent1_log_analysis.run()

    # Save intermediate output
    (OUTPUT_DIR / "agent1_output.json").write_text(
        json.dumps(agent1_result, indent=2), encoding="utf-8"
    )
    print("[Orchestrator] Agent 1 output saved → sample_output/agent1_output.json")

    # ── Agent 2 ──────────────────────────────────────────────────────────────
    banner("AGENT 2: Solution Research Agent")
    agent2_result = agent2_solution_research.run(agent1_result)

    (OUTPUT_DIR / "agent2_output.json").write_text(
        json.dumps(agent2_result, indent=2), encoding="utf-8"
    )
    print("[Orchestrator] Agent 2 output saved → sample_output/agent2_output.json")

    # ── Agent 3 ──────────────────────────────────────────────────────────────
    banner("AGENT 3: Resolution Planner Agent")
    agent3_result = agent3_resolution_planner.run(agent1_result, agent2_result)

    (OUTPUT_DIR / "agent3_output.json").write_text(
        json.dumps(agent3_result, indent=2), encoding="utf-8"
    )
    print("[Orchestrator] Agent 3 output saved → sample_output/agent3_output.json")

    # ── Final combined report ─────────────────────────────────────────────────
    elapsed = round(time.time() - start_time, 1)
    final_report = {
        "meta": {
            "system": "3-Agent Incident Response System",
            "run_timestamp": datetime.now().isoformat(),
            "duration_seconds": elapsed,
        },
        "agent1_log_analysis": agent1_result,
        "agent2_solution_research": {
            "sources_consulted": agent2_result.get("sources_consulted"),
            "solutions": agent2_result.get("solutions"),
            "risky_actions_flagged": agent2_result.get("risky_actions_flagged"),
            "recommendation_handoff": agent2_result.get("recommendation_handoff"),
            "scraping_notes": agent2_result.get("scraping_notes"),
        },
        "agent3_resolution_plan": agent3_result,
    }

    report_path = OUTPUT_DIR / "incident_report.json"
    report_path.write_text(json.dumps(final_report, indent=2), encoding="utf-8")

    # ── Print final summary to stdout ─────────────────────────────────────────
    banner("INCIDENT RESPONSE — FINAL REPORT SUMMARY")

    print(f"\n📋  Executive Summary:\n    {agent3_result.get('executive_summary', 'N/A')}")
    print(f"\n🔍  Root Cause:  {agent1_result.get('suspected_root_cause', 'N/A')}")
    print(f"    Confidence:  {agent1_result.get('confidence', 'N/A')}")
    print(f"\n✅  Best Solution: {agent3_result.get('best_solution', 'N/A')}")
    print(f"    Rationale:    {agent3_result.get('selection_rationale', 'N/A')}")

    severity = agent3_result.get("incident_classification", {}).get("severity", "N/A")
    category = agent3_result.get("incident_classification", {}).get("category", "N/A")
    print(f"\n🚦  Severity: {severity}  |  Category: {category}")

    print("\n📌  Remediation Steps:")
    for step in agent3_result.get("remediation_steps", []):
        cmd = f"  → {step.get('command', '')}" if step.get("command") else ""
        print(f"  Step {step.get('step')}: {step.get('action')}{cmd}")

    print("\n⚠️   Risky Actions to Avoid:")
    for item in agent2_result.get("risky_actions_flagged", []):
        print(f"  • {item}")

    print(f"\n💾  Full report written to: {report_path}")
    print(f"⏱   Total runtime: {elapsed}s\n")


if __name__ == "__main__":
    main()
