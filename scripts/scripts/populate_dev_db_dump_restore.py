#!/usr/bin/env python3
"""Populate the dev Kubernetes cluster's content/Lexis databases via dump/restore,
and merge the local ai_dev cache in too.

Usage:
    python scripts/populate_dev_db_dump_restore.py

Replaces the previous port-forward-and-run-the-Importer approach
(scripts/populate_dev_db.py) per the #202/DESIGN_IMPORTER.md dump/restore
decision, reaffirmed 2026-08-01: running the Importer directly against the
cluster could leave local and the cluster in different states (seen with
AI-generated content and morphology diverging between the two), and a
port-forward-based Importer run doesn't scale to a real (non-local) target.

Sequence:
  1. pg_dump the LOCAL content/Lexis databases (interlinear-bible-importer's
     scripts/dump.sh) -- these must already be populated locally via the
     Importer's normal local workflow before running this script.
  2. Port-forward to the cluster's postgres-service (reuses an existing
     forward on 5433 if one is already running -- port 5432 is permanently
     owned by the local Postgres Windows service, same rule as
     populate_dev_db.py).
  3. pg_restore each dump into the cluster's content/Lexis databases
     (scripts/restore.sh). Those databases must already exist and be EMPTY
     (true right after a fresh "K8s: Deploy (Dev)", since
     k8s/base/20-postgres.yaml's init.sql creates them empty on startup) --
     this script does not create or wipe them itself.
  4. Merge the local ai_dev cache (word_insight/word_breakdown/
     morph_suffix_explanation) into the cluster's ai_dev via
     scripts/harvest_ai_cache.py, reusing the same port-forward. Added
     2026-08-01 after a real miss: this step was originally left out
     entirely (matching dump.sh's own content/lexis-only scope) even
     though local ai_dev already held real, LLM-generated content that
     would otherwise have been silently left behind and unnecessarily
     regenerated (re-paying for LLM calls) by populate_ai_content.py.
     Additive only (ON CONFLICT DO NOTHING) -- never overwrites the
     cluster's own cache, just fills in whatever it's missing.

The user DB is never touched here -- Reader owns it via Flyway.
"""
import os
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harvest_ai_cache  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMPORTER_DIR = os.path.join(ROOT, "interlinear-bible-importer")
NAMESPACE = "interlinear-bible-dev"
LOCAL_PORT = 5433

# Local and cluster names happen to match for these two (unlike dump.sh's own
# stale CONTENT_DB default, "interlinear_bible_content_dev" -- the real local
# db is "interlinear_bible_reader_content_dev"; always passed explicitly below).
CONTENT_DB = "interlinear_bible_reader_content_dev"
LEXIS_DB = "interlinear_bible_lexis_dev"


def load_env_file():
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        return
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def db_creds():
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASS")
    if not password:
        print("Error: DB_PASS not found in .env or environment.", file=sys.stderr)
        sys.exit(1)
    return user, password


def port_open(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def wait_for_port(port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port):
            return True
        time.sleep(0.5)
    return False


def _bash_exe():
    """Plain 'bash' on PATH can resolve to the Windows WSL launcher stub
    (C:\\Windows\\System32\\bash.exe) instead of Git Bash in a subprocess,
    depending on PATH order -- that stub fails immediately if no WSL
    distro is set up. Prefer a real Git Bash install explicitly."""
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if os.path.isfile(candidate):
            return candidate
    return "bash"  # fall back to PATH resolution


def run_bash(script_rel_path, args, cwd, env):
    result = subprocess.run([_bash_exe(), script_rel_path, *args], cwd=cwd, env=env)
    if result.returncode != 0:
        print(f"Error: bash {script_rel_path} {' '.join(args)} failed (exit {result.returncode})", file=sys.stderr)
        sys.exit(result.returncode)


def latest(dist_dir, prefix):
    matches = sorted(f for f in os.listdir(dist_dir) if f.startswith(prefix) and f.endswith(".dump"))
    if not matches:
        print(f"Error: no {prefix}*.dump found in {dist_dir}", file=sys.stderr)
        sys.exit(1)
    return matches[-1]


def main():
    load_env_file()
    user, password = db_creds()

    dist_dir = os.path.join(IMPORTER_DIR, "dist")
    os.makedirs(dist_dir, exist_ok=True)

    print("[1/3] Dumping local content/Lexis databases...")
    dump_env = os.environ.copy()
    dump_env.update({
        "CONTENT_DB": CONTENT_DB,
        "LEXIS_DB": LEXIS_DB,
        "PGHOST": "localhost",
        "PGPORT": "5432",
        "PGUSER": user,
        "PGPASSWORD": password,
    })
    run_bash("scripts/dump.sh", ["dist"], IMPORTER_DIR, dump_env)

    content_dump = latest(dist_dir, "content_")
    lexis_dump = latest(dist_dir, "lexis_")

    port_forward = None
    if port_open(LOCAL_PORT):
        print(f"[2/3] Reusing existing port-forward already listening on {LOCAL_PORT}")
    else:
        print(f"[2/3] Starting port-forward: postgres-service -> localhost:{LOCAL_PORT}")
        port_forward = subprocess.Popen(
            ["kubectl", "port-forward", "svc/postgres-service",
             f"{LOCAL_PORT}:5432", "-n", NAMESPACE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not wait_for_port(LOCAL_PORT):
            port_forward.terminate()
            print(f"Error: port-forward never opened {LOCAL_PORT} -- check kubectl/cluster state.", file=sys.stderr)
            sys.exit(1)

    try:
        restore_env = os.environ.copy()
        restore_env.update({
            "PGHOST": "localhost",
            "PGPORT": str(LOCAL_PORT),
            "PGUSER": user,
            "PGPASSWORD": password,
        })
        print(f"[3/4] Restoring {content_dump} -> {CONTENT_DB} (cluster)")
        run_bash("scripts/restore.sh", [os.path.join("dist", content_dump), CONTENT_DB], IMPORTER_DIR, restore_env)
        print(f"[3/4] Restoring {lexis_dump} -> {LEXIS_DB} (cluster)")
        run_bash("scripts/restore.sh", [os.path.join("dist", lexis_dump), LEXIS_DB], IMPORTER_DIR, restore_env)

        print("[4/4] Merging local ai_dev cache into the cluster's ai_dev...")
        target_conn = harvest_ai_cache.connect("localhost", LOCAL_PORT, "interlinear_bible_ai_dev", user, password)
        target_cur = target_conn.cursor()
        source_conn = harvest_ai_cache.connect("localhost", 5432, "interlinear_bible_ai_dev", user, password)
        source_cur = source_conn.cursor()
        seen, added = harvest_ai_cache.merge_word_breakdown(source_cur, target_cur)
        print(f"  word_breakdown: {seen} in local, {added} new")
        seen, added = harvest_ai_cache.merge_morph_suffix(source_cur, target_cur)
        print(f"  morph_suffix_explanation: {seen} in local, {added} new")
        _, _, seen, added = harvest_ai_cache.merge_insight(source_cur, target_cur)
        print(f"  insight: {seen} in local, {added} new")
        target_conn.commit()
        source_cur.close(); source_conn.close()
        target_cur.close(); target_conn.close()
    finally:
        if port_forward is not None:
            port_forward.terminate()

    print("Done. Cluster content/Lexis/ai_dev populated via dump/restore + cache merge.")


if __name__ == "__main__":
    main()
