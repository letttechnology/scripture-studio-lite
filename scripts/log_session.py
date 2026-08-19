"""
Log a session summary to the ai_session_log table.

Usage:
    python AI_Bahavior/log_session.py \
      --title "What was done" \
      --summary "Details..." \
      [--github-issues "#188, #201"]  # GitHub issues worked in this session
      [--session-issues "(infrastructure)"]  # Work context/category (no GitHub issues)
      [--agent copilot]

Examples:
    --github-issues "#188, #201"  # Worked on specific GitHub issues
    --session-issues "(infrastructure)"  # Infrastructure/tooling (not GitHub issues)
    --session-issues "(documentation)"  # Documentation work
    (omit both for null)

Environment:
    DB_USER, DB_PASS, DB_HOST, DB_PORT (PostgreSQL)
    LOG_DB (default: AI_database)
"""
import argparse
import os
import sys

try:
    import psycopg2
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

def log_session(title: str, summary: str, github_issues: str | None, session_issues: str | None, agent: str) -> tuple[int, str]:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_session_log (title, summary, github_issues, session_issues, agent)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, session_date
                """,
                (title, summary, github_issues or None, session_issues or None, agent),
            )
            row = cur.fetchone()
            return row[0], row[1]
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Log an AI session summary to the database.")
    parser.add_argument("--title",          required=True, help="Short session title")
    parser.add_argument("--summary",        required=True, help="What was accomplished, sections/topics, etc.")
    parser.add_argument("--github-issues",  default=None,  help="GitHub issue numbers (e.g., '#188, #201')")
    parser.add_argument("--session-issues", default=None,  help="Session work context/category (e.g., '(infrastructure)', '(documentation)')")
    parser.add_argument("--agent",          default="copilot", choices=["copilot", "claude"], help="AI agent")
    args = parser.parse_args()

    row_id, date = log_session(args.title, args.summary, args.github_issues, args.session_issues, args.agent)
    github_str = f"GitHub issues: {args.github_issues}" if args.github_issues else "GitHub issues: (none)"
    session_str = f"Session work: {args.session_issues}" if args.session_issues else "Session work: (none)"
    print(f"[{date}] Session #{row_id} logged: {args.title}")
    print(f"  {github_str}")
    print(f"  {session_str}")

if __name__ == "__main__":
    main()

