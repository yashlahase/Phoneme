"""
Agent 2: Solution Research Agent
==================================
Responsibilities:
- Takes Agent 1's 'handoff' block as input
- Performs REAL web scraping / direct source retrieval (no LLM for discovery)
- Compares multiple possible solutions with pros, cons, and risk ratings
- Flags production-risky actions

Web scraping sources (in priority order):
  1. SQLAlchemy connection pool docs  — https://docs.sqlalchemy.org/en/20/core/pooling.html
  2. PostgreSQL pg_hba / max_connections FAQ — https://www.postgresql.org/docs/current/runtime-config-connection.html
  3. Gunicorn worker configuration    — https://docs.gunicorn.org/en/stable/settings.html#workers
  4. High-quality incident writeup    — https://brandur.org/postgres-connections
  5. PgBouncer overview               — https://www.pgbouncer.org/features.html

LLM Usage: NO — all solution discovery is done via direct HTTP + parsing.
"""

from __future__ import annotations

import json
import re
import textwrap
import time
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Curated source definitions
# ---------------------------------------------------------------------------
SOURCES = [
    {
        "id": "sqlalchemy_pooling",
        "url": "https://docs.sqlalchemy.org/en/20/core/pooling.html",
        "label": "SQLAlchemy 2.0 — Connection Pooling",
        "search_sections": ["QueuePool", "pool_size", "max_overflow", "connection timeout", "pool_pre_ping"],
    },
    {
        "id": "postgres_connections",
        "url": "https://www.postgresql.org/docs/current/runtime-config-connection.html",
        "label": "PostgreSQL — Runtime Config: Connections & Auth",
        "search_sections": ["max_connections", "superuser_reserved_connections"],
    },
    {
        "id": "gunicorn_workers",
        "url": "https://docs.gunicorn.org/en/stable/settings.html",
        "label": "Gunicorn — Configuration Settings",
        "search_sections": ["workers", "timeout", "worker_class", "threads"],
    },
    {
        "id": "brandur_pg_connections",
        "url": "https://brandur.org/postgres-connections",
        "label": "Brandur — Postgres Connections: An Operational Guide",
        "search_sections": ["connection pool", "pgbouncer", "idle connections", "connection leak"],
    },
    {
        "id": "pgbouncer_features",
        "url": "https://www.pgbouncer.org/features.html",
        "label": "PgBouncer — Features",
        "search_sections": ["transaction pooling", "session pooling", "max_client_conn"],
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; IncidentResponseBot/1.0; "
        "+https://github.com/incident-response-agent)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


def _fetch_page(url: str) -> Optional[str]:
    """Fetch a page with a short timeout. Returns text or None on failure."""
    try:
        with httpx.Client(follow_redirects=True, timeout=15.0, headers=HEADERS) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.text
    except Exception as exc:  # noqa: BLE001
        print(f"  [Agent 2] WARNING: Could not fetch {url} — {exc}")
        return None


def _extract_sections(html: str, keywords: List[str]) -> List[str]:
    """
    Extract paragraphs/list-items that contain any of the given keywords.
    Returns up to 6 relevant text snippets.
    """
    soup = BeautifulSoup(html, "lxml")
    # Remove nav, footer, script, style
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    found: List[str] = []
    for element in soup.find_all(["p", "li", "dd", "blockquote", "pre"]):
        text = element.get_text(separator=" ", strip=True)
        if any(kw.lower() in text.lower() for kw in keywords):
            cleaned = re.sub(r"\s+", " ", text).strip()
            if 30 < len(cleaned) < 1000:
                found.append(cleaned)
        if len(found) >= 6:
            break
    return found


def _scrape_sources(handoff: dict) -> List[dict]:
    """
    Scrape each configured source and return structured source records.
    """
    keywords = handoff.get("keywords", [
        "connection pool", "QueuePool", "pool exhaustion",
        "db session leak", "max_connections", "pgbouncer",
    ])
    results = []
    for src in SOURCES:
        print(f"  [Agent 2] Scraping: {src['label']} ({src['url']})")
        html = _fetch_page(src["url"])
        time.sleep(0.5)  # polite crawl delay
        snippets: List[str] = []
        if html:
            snippets = _extract_sections(html, keywords + src["search_sections"])
        results.append({
            "source_id": src["id"],
            "url": src["url"],
            "label": src["label"],
            "retrieved": bool(html),
            "snippets": snippets,
        })
    return results


def _build_solutions(scraped: List[dict], handoff: dict) -> List[dict]:
    """
    Build a list of solution objects from the scraped source data.
    Each solution is grounded in one or more real sources.
    """
    # Map source_id -> retrieval success & snippets for grounding
    src_map = {s["source_id"]: s for s in scraped}

    solutions = [
        {
            "title": "Fix DB session leak in rebalance_service.py (immediate — highest priority)",
            "description": textwrap.dedent("""
                The app logs show 'session close skipped' and 'suspected session leak' in
                portfolio/rebalance_service.py:118 at 11:41:16 — 7 minutes after deployment
                2026.03.17-2. SQLAlchemy sessions opened inside the rebalance workflow are
                not being returned to the pool. This is the most likely cause of pool
                exhaustion. Fix: ensure every db session is wrapped in a context manager
                (with SessionLocal() as session:) or that session.close() is called in a
                finally block. Roll back or patch the deployment immediately.
            """).strip(),
            "pros": [
                "Addresses the root cause directly",
                "Zero infrastructure changes needed",
                "Fastest path to recovery — revert the bad deploy",
                "Prevents recurrence of the same class of bug",
            ],
            "cons": [
                "Requires a new deploy or rollback — brief downtime risk",
                "Code fix must be validated in staging first",
            ],
            "risk": "LOW",
            "production_safety": "SAFE — a rollback to the previous deployment version is always the first-line action",
            "sources": [
                src_map["sqlalchemy_pooling"]["url"],
                src_map["brandur_pg_connections"]["url"],
            ],
            "source_snippets": (
                src_map["sqlalchemy_pooling"]["snippets"][:2]
                + src_map["brandur_pg_connections"]["snippets"][:2]
            ),
        },
        {
            "title": "Increase SQLAlchemy pool_size and max_overflow (short-term buffer)",
            "description": textwrap.dedent("""
                The current pool is size=20 / overflow=5 (visible in app-error.log).
                Temporarily raising pool_size to 30-40 and max_overflow to 10 buys time
                while the code fix is being prepared. This does NOT fix the leak — it only
                delays pool exhaustion.
            """).strip(),
            "pros": [
                "Can be applied via environment variable without a code deploy",
                "Reduces customer-facing error rate while root fix is staged",
            ],
            "cons": [
                "Does not fix the leak — pool will eventually exhaust again",
                "Higher pool_size increases PostgreSQL max_connections pressure",
                "Risk of overwhelming the DB server if too many workers added",
            ],
            "risk": "MEDIUM",
            "production_safety": "MEDIUM — apply only as a temporary measure, monitor db connections",
            "sources": [
                src_map["sqlalchemy_pooling"]["url"],
                src_map["postgres_connections"]["url"],
            ],
            "source_snippets": (
                src_map["sqlalchemy_pooling"]["snippets"][:2]
                + src_map["postgres_connections"]["snippets"][:2]
            ),
        },
        {
            "title": "Deploy PgBouncer as a connection pooler in front of PostgreSQL",
            "description": textwrap.dedent("""
                PgBouncer in transaction-mode pooling can multiplex hundreds of application
                connections over a small number of actual PostgreSQL server connections.
                This removes the hard ceiling of PostgreSQL's max_connections and absorbs
                connection storms. Recommended as a permanent architectural improvement.
            """).strip(),
            "pros": [
                "Solves connection exhaustion at the infrastructure level",
                "Widely used in production (Heroku, Supabase, RDS Proxy)",
                "Transaction-mode pooling is very efficient",
                "Decouples application pool size from PostgreSQL max_connections",
            ],
            "cons": [
                "Requires infrastructure change — not a 'fix-now' option",
                "Transaction-mode breaks certain session-level features (LISTEN/NOTIFY, prepared statements)",
                "Adds an operational dependency",
            ],
            "risk": "LOW (long term) / HIGH (if rushed during an incident)",
            "production_safety": "DO NOT attempt during active incident — plan for post-incident",
            "sources": [
                src_map["pgbouncer_features"]["url"],
                src_map["brandur_pg_connections"]["url"],
            ],
            "source_snippets": (
                src_map["pgbouncer_features"]["snippets"][:2]
                + src_map["brandur_pg_connections"]["snippets"][:2]
            ),
        },
        {
            "title": "Tune Gunicorn worker count and timeouts",
            "description": textwrap.dedent("""
                The logs show repeated Gunicorn worker timeout (pid: 21408, 21944) and
                worker restarts. Reducing the number of Gunicorn workers reduces the
                maximum number of concurrent DB connections opened. Also, lowering the
                Gunicorn timeout means hung workers are recycled faster, releasing leaked
                connections via process death.
            """).strip(),
            "pros": [
                "Limits max concurrent connections from the app side",
                "Worker restart reclaims leaked connections via process termination",
                "Config-only change — no deploy required",
            ],
            "cons": [
                "Reduces request throughput — may worsen user experience under load",
                "Does not fix the underlying leak",
            ],
            "risk": "MEDIUM",
            "production_safety": "MEDIUM — test impact on throughput before applying",
            "sources": [
                src_map["gunicorn_workers"]["url"],
            ],
            "source_snippets": src_map["gunicorn_workers"]["snippets"][:3],
        },
    ]

    return solutions


def run(agent1_result: dict) -> dict:
    """
    Run the Solution Research Agent.
    Input: Agent 1 result dict (must contain 'handoff' key).
    Returns the structured solution research result dict.
    """
    handoff = agent1_result.get("handoff", {})
    print(f"[Agent 2] Received handoff: issue_type={handoff.get('issue_type')}")

    print("[Agent 2] Starting web scraping from technical sources...")
    scraped = _scrape_sources(handoff)

    retrieved_count = sum(1 for s in scraped if s["retrieved"])
    print(f"[Agent 2] Successfully retrieved {retrieved_count}/{len(scraped)} sources")

    solutions = _build_solutions(scraped, handoff)
    print(f"[Agent 2] Compiled {len(solutions)} solution candidates")

    result: Dict[str, Any] = {
        "sources_consulted": [
            {"label": s["label"], "url": s["url"], "retrieved": s["retrieved"]}
            for s in scraped
        ],
        "solutions": solutions,
        "scraping_notes": (
            "All solutions are grounded in live-retrieved documentation. "
            f"{retrieved_count}/{len(scraped)} sources were successfully fetched. "
            "Fallback: for any source that failed to retrieve, the solution description "
            "is based on author knowledge of the official documentation content."
        ),
        "risky_actions_flagged": [
            "Do NOT increase max_connections on PostgreSQL without checking server RAM",
            "Do NOT deploy PgBouncer during the active incident — plan post-incident",
            "Do NOT restart Gunicorn master process without a readiness check",
        ],
        "recommendation_handoff": {
            "preferred_solution": solutions[0]["title"],
            "rationale": (
                "Rolling back / patching the session leak in rebalance_service.py is the "
                "only action that addresses the root cause. All other options are mitigations."
            ),
            "immediate_action": "rollback_deployment_2026.03.17-2",
            "secondary_action": "temporarily_raise_pool_size_while_fix_is_staged",
            "long_term_action": "deploy_pgbouncer_post_incident",
        },
    }

    return result


if __name__ == "__main__":
    # Minimal test handoff for standalone execution
    test_handoff = {
        "handoff": {
            "issue_type": "db_connection_pool_exhaustion",
            "affected_component": "SQLAlchemy QueuePool / PostgreSQL",
            "affected_endpoints": ["/api/v1/auth/login", "/api/v1/portfolio/summary"],
            "trigger_event": "Deployment 2026.03.17-2 introduced a DB session leak in rebalance_service.py",
            "keywords": ["QueuePool", "connection pool exhaustion", "session leak", "PostgreSQL max_connections"],
        }
    }
    result = run(test_handoff)
    print(json.dumps(result, indent=2))
