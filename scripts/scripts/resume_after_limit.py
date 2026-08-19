#!/usr/bin/env python3
"""
resume_after_limit.py - schedule a session restart for when the usage limit resets.

THE PROBLEM

When the usage limit is hit the session dies immediately. No hook fires - the Stop
hook only runs when the assistant *chooses* to stop, and this is not that. So
`block_stop_until_done.py` cannot help here, and work stops until someone notices.

The limit message carries the reset time, e.g.

    "Your limit will reset at 3pm"
    "resets at 2026-08-14 15:00"

That string is the only place the time exists - it is not written to disk anywhere
under ~/.claude. So it has to be passed in.

WHAT THIS DOES

Registers a one-shot Windows Scheduled Task that runs `claude --continue -p ...`
at the reset time, resuming this project's session with an instruction to pick the
board back up.

    python scripts/resume_after_limit.py 3pm
    python scripts/resume_after_limit.py 15:00
    python scripts/resume_after_limit.py "2026-08-14 15:00"
    python scripts/resume_after_limit.py 3pm --dry-run
    python scripts/resume_after_limit.py --cancel

A bare time means today, or tomorrow if that time has already passed - which is the
common case, since a limit that resets at 3pm is usually hit before 3pm but
sometimes after midnight.

WHAT IT CANNOT DO

It cannot detect the limit itself. Nothing observable happens in this process when
the session is killed, so the reset time must be read off the message and passed in.

An interactive session is not resumed in place - the task starts a NEW headless run.
Its output goes to .claude/logs/resume-<timestamp>.log.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / ".claude" / "logs"
TASK_NAME = "ClaudeResumeInterlinear"

RESUME_PROMPT = (
    "The usage limit reset. Resume work on the interlinear-bible board without "
    "asking. Run `python scripts/agile_flow.py status`, take the first In Progress "
    "item, and continue. Record progress in CHANGELOG.md, not in a summary message."
)


def parse_when(text: str) -> datetime:
    """
    Accept '3pm', '15:00', '2026-08-14 15:00'.

    A bare time means the next occurrence - today if still ahead, tomorrow if past.
    A limit that resets at 3pm is usually hit before 3pm, but not always.
    """
    text = text.strip().lower()
    now = datetime.now()

    full = re.match(r"^(\d{4})-(\d{2})-(\d{2})[ t](\d{1,2}):(\d{2})$", text)
    if full:
        y, mo, d, h, mi = (int(g) for g in full.groups())
        return datetime(y, mo, d, h, mi)

    ampm = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", text)
    if ampm:
        h = int(ampm.group(1)) % 12
        mi = int(ampm.group(2) or 0)
        if ampm.group(3) == "pm":
            h += 12
    else:
        hhmm = re.match(r"^(\d{1,2}):(\d{2})$", text)
        if not hhmm:
            raise ValueError(f"Could not read a time from {text!r}")
        h, mi = int(hhmm.group(1)), int(hhmm.group(2))

    when = now.replace(hour=h, minute=mi, second=0, microsecond=0)
    if when <= now:
        when += timedelta(days=1)
    return when


def schtasks(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(["schtasks", *args], capture_output=True)
    out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
    return r.returncode, out


def cancel() -> int:
    code, out = schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    print(out or ("Cancelled." if code == 0 else "Nothing scheduled."))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("when", nargs="?", help="reset time: 3pm, 15:00, or 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--prompt", default=RESUME_PROMPT, help="what to tell the resumed session")
    ap.add_argument("--dry-run", action="store_true", help="print the command, register nothing")
    ap.add_argument("--cancel", action="store_true", help="remove a scheduled resume")
    args = ap.parse_args()

    if args.cancel:
        return cancel()
    if not args.when:
        ap.error("a reset time is required (or --cancel)")

    try:
        when = parse_when(args.when)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / f"resume-{when:%Y%m%d-%H%M}.log"

    # --continue resumes the most recent conversation in this directory, so the
    # resumed run keeps the context rather than starting cold.
    inner = (
        f'cd /d "{PROJECT_ROOT}" && '
        f'claude --continue -p "{args.prompt}" >> "{log}" 2>&1'
    )
    command = f'cmd /c {inner}'

    delta = when - datetime.now()
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    print(f"Reset time : {when:%Y-%m-%d %H:%M}  (in {hours}h {rem // 60}m)")
    print(f"Log        : {log}")

    if args.dry_run:
        print(f"\nWould register task {TASK_NAME!r}:\n  {command}")
        return 0

    schtasks(["/Delete", "/TN", TASK_NAME, "/F"])  # replace any previous one
    code, out = schtasks([
        "/Create", "/TN", TASK_NAME, "/SC", "ONCE",
        "/SD", f"{when:%d/%m/%Y}", "/ST", f"{when:%H:%M}",
        "/TR", command, "/F",
    ])
    if code != 0:
        print(f"\nCould not register the task:\n{out}", file=sys.stderr)
        print("\nIf this is a date-format rejection, try the explicit form:\n"
              f"  python scripts/resume_after_limit.py \"{when:%Y-%m-%d %H:%M}\"",
              file=sys.stderr)
        return 3

    print(f"\nScheduled. Cancel with:  python scripts/resume_after_limit.py --cancel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
