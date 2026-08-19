"""
Read recent AI session summaries from ai_session_log.

Usage:
    python AI_Bahavior/recent_sessions.py          # last 10 sessions
    python AI_Bahavior/recent_sessions.py --days 7 # last 7 days
    python AI_Bahavior/recent_sessions.py --n 5    # last 5 rows

Output is intended to be pasted into session context at session start.
"""
import argparse
import os
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("psycopg2 not installed. Run: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

def get_conn():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("LOG_DB", "AI_database"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASS", "postgres"),
    )

def recent_sessions(days: int | None, n: int) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            if days:
                cur.execute(
                    """
                    SELECT id, session_date, agent, title, github_issues, session_issues, summary
                    FROM ai_session_log
                    WHERE session_date >= CURRENT_DATE - %s::int
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (days, n),
                )
            else:
                cur.execute(
                    """
                    SELECT id, session_date, agent, title, github_issues, session_issues, summary
                    FROM ai_session_log
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (n,),
                )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Show recent AI session summaries.")
    parser.add_argument("--days", type=int, default=None, help="Limit to last N days")
    parser.add_argument("--n",    type=int, default=10,   help="Max rows to return (default 10)")
    args = parser.parse_args()

    rows = recent_sessions(args.days, args.n)
    if not rows:
        print("No session logs found.")
        return

    print(f"# Recent AI Sessions ({len(rows)} entries)\n")
    for r in rows:
        print(f"## {r['session_date']} — {r['title']}  [{r['agent']}]")
        if r['github_issues']:
            print(f"  GitHub issues: {r['github_issues']}")
        if r['session_issues']:
            print(f"  Session work: {r['session_issues']}")
        print()
        print(r['summary'])
        print()
        print("---")
        print()

if __name__ == "__main__":
    main()
