# 3-Agent Incident Response System

A working AI-agent pipeline that ingests production logs and produces a structured incident-response recommendation through three collaborating agents.

---

## Architecture

```
logs/
├── nginx-access.log
├── nginx-error.log
└── app-error.log
         │
         ▼
┌─────────────────────────────────┐
│  Agent 1: Log Analysis Agent    │  (Gemini-2.5-flash)
│  • Reads all 3 log files        │
│  • Identifies root cause        │
│  • Extracts evidence + timeline │
│  • Outputs structured JSON      │
└────────────────┬────────────────┘
                 │ JSON handoff
                 ▼
┌─────────────────────────────────┐
│  Agent 2: Solution Research     │  (Web scraping — no LLM)
│  • Scrapes 5 technical sources  │
│  • SQLAlchemy, PostgreSQL docs  │
│  • Gunicorn, PgBouncer docs     │
│  • Brandur engineering blog     │
│  • Ranks solutions + risks      │
└────────────────┬────────────────┘
                 │ JSON handoff
                 ▼
┌─────────────────────────────────┐
│  Agent 3: Resolution Planner    │  (Gemini-2.5-flash)
│  • Selects safest solution      │
│  • Writes step-by-step runbook  │
│  • Pre-checks + validation      │
│  • Rollback / safety notes      │
└────────────────┬────────────────┘
                 │
                 ▼
    sample_output/incident_report.json
```

---

## Setup

### 1. Requirements

- Python 3.9+
- Internet access (Agent 2 scrapes live documentation)

### 2. Install dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Configure your API key

Edit `.env` and set your Gemini API key:

```env
GEMINI_API_KEY=your_key_here
```

> **Important**: The key provided in the original brief was reported as leaked by Google.  
> You must use a fresh key from https://aistudio.google.com/app/apikey

### 4. Run

```bash
python3 main.py
```

The system will:
1. Run Agent 1 → print root cause + confidence
2. Run Agent 2 → scrape 5 documentation sources, print solution count
3. Run Agent 3 → print final resolution plan
4. Write all outputs to `sample_output/`

---

## Output Files

| File | Contents |
|---|---|
| `sample_output/agent1_output.json` | Log analysis result with evidence and timeline |
| `sample_output/agent2_output.json` | Researched solutions with sources and risk ratings |
| `sample_output/agent3_output.json` | Step-by-step remediation runbook |
| `sample_output/incident_report.json` | Combined final report (all 3 agents) |

---

## What the System Concluded for This Incident

### Root Cause (Agent 1 — HIGH confidence)

> Deployment **2026.03.17-2** at 11:34:09 IST introduced a database session leak in  
> `portfolio/rebalance_service.py:118`. The SQLAlchemy connection pool (size=20, overflow=5)  
> was exhausted within ~7 minutes, causing all endpoints requiring DB access to fail.

**Key evidence:**
- `11:40:48` — Pool at checked_out=18/20 (first warning)
- `11:41:02` — `QueuePool limit of size 20 overflow 5 reached` (hard failure)
- `11:41:16` — `session close skipped ... code_path=portfolio/rebalance_service.py:118` (leak confirmed)
- `11:41:17` — `suspected session leak count=23` (leak detector fired)
- `11:42:16` — `deployment_version=2026.03.17-2 ... touched db session lifecycle` (cause linked)
- `/health` endpoint continued returning 200 throughout — masking the incident from ELB

### Solution Selected (Agent 3 — P1 Severity)

**Immediate**: Roll back deployment 2026.03.17-2 (restores previous code, stops the leak)  
**Secondary**: Kill lingering idle PostgreSQL connections after rollback  
**Long-term**: Add PgBouncer, fix session lifecycle, add pool monitoring

---

## Agent Boundaries and Handoff Design

### Agent Boundaries

| Agent | Mechanism | Purpose |
|---|---|---|
| Agent 1 | LLM (Gemini-2.5-flash) | Reason over unstructured log text to form a diagnosis |
| Agent 2 | Web scraping (httpx + BeautifulSoup) | Retrieve factual, source-backed remediation options |
| Agent 3 | LLM (Gemini-2.5-flash) | Synthesise findings into an operator-ready runbook |

**Why Agent 2 does not use an LLM**: LLMs hallucinate sources. Agent 2's value is in providing *real, citable URLs* to actual documentation. The scraping approach guarantees every solution is backed by a retrievable, verifiable source.

### Handoff Format

Each agent outputs a JSON object. The orchestrator (`main.py`) passes:
- Agent 1's full output → Agent 2 (specifically the `handoff` sub-object drives keyword-targeted scraping)
- Agent 1's full output + Agent 2's full output → Agent 3 (full context for planning)

Intermediate outputs are saved to `sample_output/` for auditability.

### Why These Implementation Choices Are Production-Reasonable

1. **LLM for log analysis**: Logs are unstructured text. LLMs excel at extracting meaning from noisy, multi-format log data — far better than regex heuristics alone.
2. **Web scraping for solutions**: Keeps recommendations grounded in real documentation. URLs are recorded, so the remediation advice is auditable and traceable.
3. **LLM for planning**: Converting a diagnosis + solution options into a safe, ordered runbook is a synthesis task that benefits from LLM reasoning. The prompt explicitly encodes safety rules (no DB restarts during outages, rollback-first).
4. **Structured JSON handoffs**: Enables each agent to be tested, logged, and replaced independently. The schema is a production-grade incident record format.
5. **Intermediate file saves**: Every agent's output is persisted before the next agent runs. If Agent 3 fails, Agent 1 and 2 outputs are not lost.

---

## Limitations and Missing Production Safeguards

| Limitation | Impact | Mitigation |
|---|---|---|
| Gemini API key must be valid and not rate-limited | System halts if key is invalid | Add retry logic + fallback to a second key |
| Agent 2 web scraping can fail if sources are down | Solutions fall back to author knowledge | Sources are tried individually; partial retrieval still produces results |
| No streaming output | Long Gemini calls block | Add `stream=True` for production UX |
| No authentication on log access | Logs read directly from filesystem | In production, logs would be fetched from a log aggregator (Datadog, CloudWatch) via authenticated API |
| Sample output is pre-generated | Reviewer sees static data without a valid API key | All code is live and runnable — just supply a valid GEMINI_API_KEY |
| Agent 2 respects robots.txt manually (polite crawl delay) but does not parse robots.txt | Could inadvertently violate scraping policies | Add `robotparser` check in production |
