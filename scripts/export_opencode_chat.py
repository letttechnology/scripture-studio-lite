#!/usr/bin/env python3
"""
export_opencode_chat.py — Export opencode chat history to AI_Memory for version control.

Usage:
  python scripts/export_opencode_chat.py                    # export latest session
  python scripts/export_opencode_chat.py --session <id>     # export specific session
  python scripts/export_opencode_chat.py --list             # list all sessions
  python scripts/export_opencode_chat.py --all              # export all sessions

Output: ~/.local/share/opencode/chat/chat_<session_id>.md (local)
        and copies to AI_Memory/chat/ (if within interlinear-bible-api project)
"""

import sqlite3
import json
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────

OPCODE_DB = os.path.join(
    os.environ.get("USERPROFILE", os.environ.get("HOME", "")),
    ".local/share/opencode/opencode.db",
)

AI_MEMORY_CHAT = None
project_root = Path(__file__).resolve().parent.parent
ai_memory_candidate = project_root.parent / "AI_Memory" / "chat"
if ai_memory_candidate.exists():
    AI_MEMORY_CHAT = str(ai_memory_candidate)

LOCAL_CHAT_DIR = os.path.join(
    os.environ.get("USERPROFILE", os.environ.get("HOME", "")),
    ".local/share/opencode/chat",
)


# ── helpers ────────────────────────────────────────────────────────────────

def get_conn():
    if not os.path.exists(OPCODE_DB):
        print(f"ERROR: opencode DB not found at {OPCODE_DB}")
        sys.exit(1)
    return sqlite3.connect(OPCODE_DB)


def list_sessions(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT id, project_id, time_created, directory
        FROM session
        ORDER BY time_created DESC
    """)
    sessions = cur.fetchall()
    print(f"OpenCode sessions ({len(sessions)}):")
    for s in sessions:
        ts = datetime.fromtimestamp(s[2] / 1000).strftime("%Y-%m-%d %H:%M") if s[2] else "?"
        d = s[3] or "(none)"
        print(f"  {s[0]}  {ts}  {d}")
    return sessions


def export_session(conn, session_id, out_dir):
    cur = conn.cursor()

    # Get session info
    cur.execute("SELECT id, directory, time_created FROM session WHERE id = ?", (session_id,))
    row = cur.fetchone()
    if not row:
        print(f"  ERROR: session {session_id} not found")
        return

    ts = datetime.fromtimestamp(row[2] / 1000).strftime("%Y%m%d_%H%M%S") if row[2] else "unknown"
    name = f"chat_{session_id[:12]}_{ts}.md"
    out_path = os.path.join(out_dir, name)

    # Get messages
    cur.execute("""
        SELECT p.data, m.data, p.time_created
        FROM part p
        JOIN message m ON m.id = p.message_id
        WHERE p.session_id = ?
        ORDER BY p.time_created
    """, (session_id,))
    parts = cur.fetchall()

    lines = []
    msg_count = 0
    for p in parts:
        pdata = json.loads(p[0]) if p[0] else {}
        mdata = json.loads(p[1]) if p[1] else {}
        role = mdata.get("role", "system")
        text = pdata.get("text", "") or ""
        ts_msg = datetime.fromtimestamp(p[2] / 1000).strftime("%H:%M:%S") if p[2] else ""
        t = text.strip()
        if t:
            lines.append(f"## [{role}] ({ts_msg})")
            lines.append("")
            lines.append(t)
            lines.append("")
            msg_count += 1

    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Copy to AI_Memory if available
    if AI_MEMORY_CHAT:
        from shutil import copy2
        copy2(out_path, os.path.join(AI_MEMORY_CHAT, name))

    print(f"  {msg_count} messages -> {name}")
    return out_path


# ── main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Export opencode chat history")
    parser.add_argument("--session", type=str, default="", help="Export specific session ID")
    parser.add_argument("--list", action="store_true", help="List all sessions and exit")
    parser.add_argument("--all", action="store_true", help="Export all sessions")
    parser.add_argument("--latest", action="store_true", default=True, help="Export latest session (default)")
    args = parser.parse_args()

    conn = get_conn()

    if args.list:
        list_sessions(conn)
        conn.close()
        return

    session_id = args.session

    if not session_id and args.all:
        cur = conn.cursor()
        cur.execute("SELECT id FROM session ORDER BY time_created DESC")
        all_ids = [r[0] for r in cur.fetchall()]
        for sid in all_ids:
            export_session(conn, sid, LOCAL_CHAT_DIR)
        print(f"\nExported {len(all_ids)} sessions to {LOCAL_CHAT_DIR}")
        conn.close()
        return

    if not session_id:
        cur = conn.cursor()
        cur.execute("SELECT id FROM session ORDER BY time_created DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            print("ERROR: no sessions found")
            conn.close()
            return
        session_id = row[0]
        print(f"Latest session: {session_id}")

    export_session(conn, session_id, LOCAL_CHAT_DIR)
    if AI_MEMORY_CHAT:
        print(f"Also copied to AI_Memory/chat/")
    conn.close()


if __name__ == "__main__":
    main()
