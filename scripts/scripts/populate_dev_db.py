#!/usr/bin/env python3
"""Run the Importer against the dev Kubernetes cluster's Postgres.

Usage:
    python scripts/populate_dev_db.py

Port 5432 is permanently owned by the local Postgres Windows service, so a
port-forward to 5432 silently loses and the Importer ends up writing to the
wrong (local) database instead of the cluster's. This script always uses
5433, reuses an existing forward on that port if one is already running
(e.g. for pgAdmin), and only tears down the forward it started itself.
"""
import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMPORTER_DIR = os.path.join(ROOT, "interlinear-bible-importer")
NAMESPACE = "interlinear-bible-dev"
LOCAL_PORT = 5433


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
    user = os.environ.get("POSTGRES_USER") or os.environ.get("DB_USER")
    password = (os.environ.get("POSTGRES_PASSWORD")
                or os.environ.get("DB_PASSWORD")
                or os.environ.get("DB_PASS"))
    if not user or not password:
        print("Error: DB_USER/DB_PASS not found in .env or environment.", file=sys.stderr)
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


def main():
    load_env_file()
    user, password = db_creds()

    port_forward = None
    if port_open(LOCAL_PORT):
        print(f"Reusing existing port-forward already listening on {LOCAL_PORT}")
    else:
        print(f"Starting port-forward: postgres-service -> localhost:{LOCAL_PORT}")
        port_forward = subprocess.Popen(
            ["kubectl", "port-forward", "svc/postgres-service",
             f"{LOCAL_PORT}:5432", "-n", NAMESPACE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not wait_for_port(LOCAL_PORT):
            port_forward.terminate()
            print(f"Error: port-forward never opened {LOCAL_PORT} — check kubectl/cluster state.", file=sys.stderr)
            sys.exit(1)

    env = os.environ.copy()
    env["CONTENT_DB_URL"] = f"jdbc:postgresql://localhost:{LOCAL_PORT}/interlinear_bible_reader_content_dev"
    env["LEXIS_DB_URL"] = f"jdbc:postgresql://localhost:{LOCAL_PORT}/interlinear_bible_lexis_dev"
    env["DB_USER"] = user
    env["DB_PASS"] = password

    try:
        result = subprocess.run("mvn spring-boot:run", shell=True, cwd=IMPORTER_DIR, env=env)
        return result.returncode
    finally:
        if port_forward is not None:
            port_forward.terminate()


if __name__ == "__main__":
    sys.exit(main())
