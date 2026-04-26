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


