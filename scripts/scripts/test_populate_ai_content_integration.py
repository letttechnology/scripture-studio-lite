#!/usr/bin/env python3
"""Integration test that populates missing AI content via the real round-robin API.

This is deliberately NOT a unit test with mocked HTTP calls. It does exactly what
populate_ai_content.py does — find lexemes/tokens missing breakdown, morph-suffix, or
insight content, and POST them to the AI service's real /breakdown, /morph-suffix, /insight
endpoints so ResilientAiRouter's round-robin pool actually generates and persists them.

Two things happen from one run:
  1. It proves the round-robin API is live, reachable, and correctly wired end-to-end
     (HTTP -> controller -> service -> round-robin provider -> Postgres) — a real call, not
     a mock, so a passing test is proof the pool actually answers requests.
  2. As a side effect, the database ends up populated — nobody needs to separately run
     populate_ai_content.py by hand afterward.

Opt-in only: running the full corpus is slow and makes real (rate-limited, sometimes
billable) calls to upstream providers, so this must never fire as a side effect of a bare
`pytest` sweep. Requires AI_POPULATE_LIVE=1. Skips cleanly (not a failure) if that's unset,
or if the AI service isn't reachable — same "manual, out-of-gate, explicit" posture as
interlinear-bible-ai's LiveApiConnectivityCheck.

Usage (after port-forwarding the k8s cluster, or against a local dev stack):
    kubectl port-forward svc/ai-service 8083:8083 -n interlinear-bible-dev &
    kubectl port-forward svc/postgres 5432:5432 -n interlinear-bible-dev &
    AI_POPULATE_LIVE=1 pytest scripts/test_populate_ai_content_integration.py -v -s

Config (env vars, same defaults/semantics as populate_ai_content.py's CLI flags):
    AI_URL              default http://localhost:8083/ai
    DB_PORT              default 5432   (Lexis + content DBs)
    AI_DB_PORT           default = DB_PORT   (AI service's own DB)
    AI_POPULATE_LIMIT    default 100000 (effectively "all")
    AI_POPULATE_DELAY_MS default 1200
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import populate_ai_content as pop

import psycopg2
import urllib.request
import urllib.error

AI_URL = os.environ.get("AI_URL", "http://localhost:8083/ai")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
AI_DB_PORT = int(os.environ.get("AI_DB_PORT", DB_PORT))
LIMIT = int(os.environ.get("AI_POPULATE_LIMIT", 100000))
DELAY_MS = int(os.environ.get("AI_POPULATE_DELAY_MS", 1200))


def _ai_service_reachable():
    try:
        with urllib.request.urlopen(f"{AI_URL}/actuator/health", timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    os.environ.get("AI_POPULATE_LIVE") != "1",
    reason="Live population run — makes real calls to the round-robin AI providers and "
           "writes to real databases. Opt in with AI_POPULATE_LIVE=1 (see module docstring).",
)


@pytest.fixture(scope="module")
def db_connections():
    if not _ai_service_reachable():
        pytest.skip(f"AI service not reachable at {AI_URL} — port-forward it first "
                    f"(or pass AI_URL) then rerun.")

    pop.load_env_file()
    user, password = pop.db_creds()

    lexis_conn = psycopg2.connect(host="localhost", port=DB_PORT, dbname="interlinear_bible_lexis_dev",
                                   user=user, password=password, connect_timeout=10)
    lexis_conn.autocommit = True
    content_conn = psycopg2.connect(host="localhost", port=DB_PORT, dbname="interlinear_bible_reader_content_dev",
                                     user=user, password=password, connect_timeout=10)
    content_conn.autocommit = True
    ai_conn = psycopg2.connect(host="localhost", port=AI_DB_PORT, dbname="interlinear_bible_ai_dev",
                                user=user, password=password, connect_timeout=10)
    ai_conn.autocommit = True

    yield lexis_conn, content_conn, ai_conn

    lexis_conn.close()
    content_conn.close()
    ai_conn.close()


def test_populates_missing_morph_suffix_content(db_connections):
    lexis_conn, content_conn, ai_conn = db_connections
    cur, content_cur, ai_cur = lexis_conn.cursor(), content_conn.cursor(), ai_conn.cursor()

    before = pop.fetch_morph_suffix_targets(cur, ai_cur, LIMIT)
    pop.run_morph_suffix(cur, ai_cur, content_cur, AI_URL, LIMIT, DELAY_MS)
    after = pop.fetch_morph_suffix_targets(cur, ai_cur, LIMIT)

    assert len(after) < len(before) or len(before) == 0, (
        f"round-robin call made no progress: {len(before)} missing before, {len(after)} after")
    assert after == [], f"{len(after)} morph-suffix codes still missing after population run"


def test_populates_missing_breakdown_content(db_connections):
    lexis_conn, content_conn, ai_conn = db_connections
    cur, content_cur, ai_cur = lexis_conn.cursor(), content_conn.cursor(), ai_conn.cursor()

    before = pop.fetch_breakdown_targets(cur, ai_cur, LIMIT)
    pop.run_breakdown(cur, ai_cur, content_cur, AI_URL, LIMIT, DELAY_MS)
    after = pop.fetch_breakdown_targets(cur, ai_cur, LIMIT)

    assert len(after) < len(before) or len(before) == 0, (
        f"round-robin call made no progress: {len(before)} missing before, {len(after)} after")
    assert after == [], f"{len(after)} breakdown keys still missing after population run"


def test_populates_missing_insight_content(db_connections):
    lexis_conn, content_conn, ai_conn = db_connections
    cur, ai_cur = lexis_conn.cursor(), ai_conn.cursor()

    before = pop.fetch_insight_targets(cur, ai_cur, LIMIT)
    pop.run_insight(cur, ai_cur, AI_URL, LIMIT, DELAY_MS)
    after = pop.fetch_insight_targets(cur, ai_cur, LIMIT)

    assert len(after) < len(before) or len(before) == 0, (
        f"round-robin call made no progress: {len(before)} missing before, {len(after)} after")
    assert after == [], f"{len(after)} insight lexemes still missing after population run"
