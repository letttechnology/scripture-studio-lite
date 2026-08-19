#!/usr/bin/env python3
"""agile-flow — board transitions for the interlinear-bible project.

One file on purpose. The previous version was 15 scripts that shelled out to each
other by absolute path; archiving the folder snapped every link at once and the
board sat untouched for a whole session while work shipped. Nothing in here calls
another script, so the only way to break it is to delete this file.

Sessions here die abruptly when the usage limit hits, and an abrupt death means no
end-of-session step ever runs. So the board is moved *as work finishes*, never
batched to the end. `reconcile` exists to catch the one story that was in flight
when a session was killed.

Commands:
    status [EPIC#]              Board status: In Progress, then Ready
    start <ID>                  Move card to In Progress, record checkpoint
    work-done <ID> ["msg"]      Build gates -> per-repo commit -> In Review & Testing
    review-done <ID>            Move card to Done
    reconcile                   Report drift; never mutates
"""
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[3]
STATE_FILE = REPO_ROOT / ".claude" / "state" / "active-story.json"

TRACKER = "letttechnology/interlinear-bible-tracker"
PROJECT_NUMBER = "6"
PROJECT_OWNER = "letttechnology"
PROJECT_ID = "PVT_kwHOEP4kSc4BcN3R"
STATUS_FIELD_ID = "PVTSSF_lAHOEP4kSc4BcN3RzhW4S_w"

STATUS_OPTIONS = {
    "Ready": "e18bf179",
    "In Progress": "47fc9ee4",
    "In Review & Testing": "aba860b9",
    "Done": "98236657",
}

# `gh project item-list` returns display names whose casing does not match the
# option labels above ("In progress" vs "In Progress"). Compare case-folded only.
IN_PROGRESS = "in progress"
READY = "ready"

# interlinear-bible-api is intentionally excluded: read-only, never commit or build
# unless explicitly instructed (workspace CLAUDE.md, AI_Bahavior #43).
REPOS = [
    "interlinear-bible-ai",
    "interlinear-bible-lexis",
    "interlinear-bible-importer",
    "interlinear-bible-reader",
    "interlinear-bible-studio",
    "interlinear-bible-ui",
]


def gh_env():
    """
    Environment for `gh`, with the project-scoped token from the repo-root .env.

    The keyring login carries `repo` but not `project`, so board reads and column moves fail
    against it while issue comments succeed — a split that is easy to misread as "the board is
    broken". The token that does have `project` scope is in .env.

    Read here rather than expected in the ambient environment, because the alternative is every
    caller prefixing `export GH_TOKEN=$(...)`, which is a command-injection shape the permission
    scanner cannot statically clear (`export a[$(cmd)]=x` arithmetic-evaluates the subscript). It
    prompted on every invocation, which is a reason to remove the need rather than to remember not
    to do it.
    """
    env = os.environ.copy()
    if env.get("GH_TOKEN"):
        return env
    envfile = Path(__file__).resolve().parents[1] / ".env"
    try:
        for line in envfile.read_text(encoding="utf-8").splitlines():
            if line.startswith("GH_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                if token:
                    env["GH_TOKEN"] = token
                break
    except OSError:
        pass  # no .env — fall back to the ambient login, which is enough for issue operations
    return env


def run(cmd, cwd=None):
    return subprocess.run(
        cmd, shell=True, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=gh_env(),
    )


def die(message):
    print(f"ERROR: {message}")
    sys.exit(1)


def board_items():
    result = run(
        f"gh project item-list {PROJECT_NUMBER} --owner {PROJECT_OWNER} "
        f"--format json --limit 1000"
    )
    if result.returncode != 0:
        die(f"could not fetch board\n{result.stderr.strip()}")
    try:
        return json.loads(result.stdout).get("items", [])
    except json.JSONDecodeError as e:
        die(f"could not parse board JSON — {e}")


def move_card(story_id, status):
    """Set a card's status column. Returns nothing; exits on failure."""
    option_id = STATUS_OPTIONS.get(status)
    if not option_id:
        die(f"unknown status '{status}'. Valid: {', '.join(STATUS_OPTIONS)}")

    item_id = None
    for item in board_items():
        if str(item.get("content", {}).get("number")) == str(story_id):
            item_id = item.get("id")
            break
    if not item_id:
        die(f"story #{story_id} is not on the board — add it first")

    result = run(
        f"gh project item-edit --id {item_id} --project-id {PROJECT_ID} "
        f"--field-id {STATUS_FIELD_ID} --single-select-option-id {option_id}"
    )
    if result.returncode != 0:
        die(f"could not move #{story_id} to {status}\n{result.stderr.strip()}")
    print(f"[OK] #{story_id} -> {status}")


def dirty_repos():
    found = []
    for name in REPOS:
        path = REPO_ROOT / name
        if not path.is_dir():
            continue
        if run("git status --short", cwd=path).stdout.strip():
            found.append((name, path))
    return found


def write_checkpoint(story_id, title):
    """Record the in-flight story so a limit-killed session leaves a trace."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "story_id": str(story_id),
        "title": title,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2), encoding="utf-8")


def read_checkpoint():
    if not STATE_FILE.is_file():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def clear_checkpoint():
    if STATE_FILE.is_file():
        STATE_FILE.unlink()


def cmd_status(epic=None):
    search = f' --search "parent:{epic}"' if epic else ""
    result = run(
        f"gh issue list --repo {TRACKER} --state open{search} "
        f"--json number,title,projectItems --limit 500"
    )
    if result.returncode != 0:
        die(f"could not fetch issues\n{result.stderr.strip()}")
    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        die(f"could not parse issues — {e}")

    in_progress, ready = [], []
    for issue in issues:
        num = issue.get("number")
        if not num:
            continue
        status = ""
        for item in issue.get("projectItems", []):
            status = (item.get("status") or {}).get("name") or ""
            if status:
                break
        entry = (num, issue.get("title", "(no title)"))
        if status.casefold() == IN_PROGRESS:
            in_progress.append(entry)
        elif status.casefold() == READY:
            ready.append(entry)

    print("BOARD STATUS\n")
    if in_progress:
        print(f"IN PROGRESS ({len(in_progress)}) - Pick first:")
        for num, title in in_progress:
            print(f"  #{num}: {title}")
        print()
    else:
        print("No In Progress stories.\n")

    if ready:
        print(f"READY ({len(ready)}) - Next after In Progress:")
        for num, title in ready[:5]:
            print(f"  #{num}: {title}")
        if len(ready) > 5:
            print(f"  ... and {len(ready) - 5} more")
        print()

    if in_progress:
        print(f"NEXT TO CONTINUE: #{in_progress[0][0]}: {in_progress[0][1]}")
    elif ready:
        print(f"NEXT TO START: #{ready[0][0]}: {ready[0][1]}")
    else:
        print("No In Progress or Ready stories.")


def cmd_start(story_id):
    result = run(f"gh issue view {story_id} --repo {TRACKER} --json title")
    title = "(unknown)"
    if result.returncode == 0:
        try:
            title = json.loads(result.stdout).get("title", title)
        except json.JSONDecodeError:
            pass

    move_card(story_id, "In Progress")
    write_checkpoint(story_id, title)
    print(f"Working on #{story_id}: {title}")


def cmd_work_done(story_id, message=None):
    message = message or f"Complete story #{story_id}"
    dirty = dirty_repos()
    if not dirty:
        # Work committed by hand — a story whose commits want individual messages, or one
        # finished before this script was reached. There is nothing to build and nothing to
        # commit, but the card still has to move, and refusing left it stranded in In Progress
        # with the work already shipped. Which is the exact drift `reconcile` exists to report.
        print(f"#{story_id}: no uncommitted changes — already committed by hand.")
        print("Skipping build gates and commit; moving the card only.\n")
        move_card(story_id, "In Review & Testing")
        clear_checkpoint()
        print(f"#{story_id} ready for review")
        return

    print(f"Completing #{story_id}")
    print(f"Repos with changes: {', '.join(n for n, _ in dirty)}\n")

    print("[1/3] Build gates...")
    for name, path in dirty:
        if (path / "pom.xml").is_file():
            gates = [("compile", "mvn compile"),
                     ("test-compile", "mvn test-compile"),
                     ("test", "mvn test")]
        elif (path / "package.json").is_file():
            gates = [("build", "npm run build")]
        else:
            print(f"  {name}: no pom.xml/package.json, skipping gates")
            continue
        for gate, cmd in gates:
            print(f"  {name}: {gate}")
            result = run(cmd, cwd=path)
            if result.returncode != 0:
                print(f"  [FAIL] {name}: {gate}")
                print(result.stdout[-1500:])
                print(result.stderr[-1500:])
                die("build gate failed — nothing committed, card not moved")
            print(f"  [PASS] {name}: {gate}")
    print()

    print("[2/3] Committing...")
    commit_msg = f"{message} (#{story_id})\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
    for name, path in dirty:
        run("git add -A", cwd=path)
        result = run(f'git commit -m "{commit_msg}"', cwd=path)
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr)
            die(f"commit failed in {name} — card not moved")
        print(f"  [COMMIT] {name}: {run('git log -1 --format=%h %s', cwd=path).stdout.strip()}")
    print()

    print("[3/3] Moving card...")
    move_card(story_id, "In Review & Testing")
    clear_checkpoint()
    print(f"#{story_id} ready for review")


def cmd_review_done(story_id):
    move_card(story_id, "Done")
    checkpoint = read_checkpoint()
    if checkpoint and checkpoint.get("story_id") == str(story_id):
        clear_checkpoint()


def cmd_reconcile():
    """Report board drift. Never moves a card — surfacing is the whole job."""
    print("RECONCILE\n")

    checkpoint = read_checkpoint()
    if checkpoint:
        print(f"In flight when the last session ended:")
        print(f"  #{checkpoint['story_id']}: {checkpoint.get('title', '(unknown)')}")
        print(f"  started {checkpoint.get('started_at', '?')}")
        print("  -> if that work shipped, run: work-done <ID>\n")
    else:
        print("No story was checkpointed as in flight.\n")

    dirty = dirty_repos()
    if dirty:
        print(f"Uncommitted changes in {len(dirty)} repo(s):")
        for name, path in dirty:
            count = len(run("git status --short", cwd=path).stdout.strip().splitlines())
            print(f"  {name}: {count} file(s)")
        print()
    else:
        print("All repos clean.\n")

    stale = []
    for item in board_items():
        content = item.get("content", {})
        num = content.get("number")
        if not num or (item.get("status") or "").casefold() != IN_PROGRESS:
            continue
        stale.append((num, content.get("title", "")))
    if stale:
        print(f"Sitting In Progress ({len(stale)}) — confirm each is really still active:")
        for num, title in stale:
            print(f"  #{num}: {title[:80]}")


COMMANDS = {
    "status": (cmd_status, 0, 1),
    "start": (cmd_start, 1, 1),
    "work-done": (cmd_work_done, 1, 2),
    "review-done": (cmd_review_done, 1, 1),
    "reconcile": (cmd_reconcile, 0, 0),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    handler, min_args, max_args = COMMANDS[sys.argv[1]]
    args = sys.argv[2:]
    if not min_args <= len(args) <= max_args:
        die(f"'{sys.argv[1]}' takes {min_args}-{max_args} argument(s), got {len(args)}")
    handler(*args)


if __name__ == "__main__":
    main()
