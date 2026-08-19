#!/usr/bin/env python3
"""Fail fast if the workspace-root .env has a key defined more than once.

kustomize's secretGenerator (k8s/overlays/*/kustomization.yaml) reads .env
directly and errors on a duplicate key ("configmap app-secrets illegally
repeats the key ..."). bash's `source` silently lets the last value win,
which hides the same problem until someone hits the k8s failure. Run this
before either path loads .env so the duplicate is caught with a clear
message instead.

ASCII-only output: this runs under cmd.exe (deploy.bat) as well as bash,
and cmd's default codepage mangles non-ASCII characters.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def _mask(value: str) -> str:
    value = value.strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}...{value[-3:]} ({len(value)} chars)"


def find_duplicates(env_path: Path) -> dict[str, list[tuple[int, str]]]:
    lines_by_key: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for lineno, line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = KEY_RE.match(line)
        if m:
            lines_by_key[m.group(1)].append((lineno, m.group(2)))
    return {k: v for k, v in lines_by_key.items() if len(v) > 1}


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    if not env_path.exists():
        return 0  # nothing to check — callers already warn separately if .env is missing

    dupes = find_duplicates(env_path)
    if not dupes:
        return 0

    print(f"ERROR: duplicate keys in {env_path}:", file=sys.stderr)
    for key, occurrences in sorted(dupes.items()):
        values = {v.strip() for _, v in occurrences}
        status = ("SAME value repeated" if len(values) == 1
                   else "DIFFERENT values -- likely stale/rotated credential, not a copy-paste")
        print(f"  {key} -- {status}", file=sys.stderr)
        for lineno, value in occurrences:
            print(f"    line {lineno}: {_mask(value)}", file=sys.stderr)
    print(
        "Fix: keep one line per key. A duplicate breaks k8s deploys "
        "(kustomize secretGenerator rejects it outright) and silently "
        "shadows a value in local dev (bash source keeps only the last one) -- "
        "when the values differ, that shadowing can mean the wrong credential "
        "is silently in effect.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
