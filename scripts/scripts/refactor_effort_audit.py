#!/usr/bin/env python3
"""Audit refactoring effort issues against DESIGN.md ownership boundaries.

What it does in one run:
1) Fetches a seed set of GitHub issues by URL.
2) Expands linked sub-issues found in issue bodies.
3) Classifies each issue by concern (Studio/Reader/Lexis/Importer/UI/User/Cross-cutting).
4) Reports done/open by concern and calls out architectural misalignment.

Usage:
  python AI_Bahavior/refactor_effort_audit.py
  python AI_Bahavior/refactor_effort_audit.py --issues <url1> <url2> ...
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

DEFAULT_ISSUES = [
    "https://github.com/letttechnology/interlinear-bible-tracker/issues/166",
    "https://github.com/letttechnology/interlinear-bible-tracker/issues/209",
    "https://github.com/letttechnology/interlinear-bible-tracker/issues/94",
    "https://github.com/letttechnology/interlinear-bible-tracker/issues/93",
    "https://github.com/letttechnology/interlinear-bible-tracker/issues/92",
]

ISSUE_URL_RE = re.compile(r"https://github\.com/([^/]+)/([^/]+)/issues/(\d+)", re.IGNORECASE)

SUB_ISSUE_LINK_RE = re.compile(
    r"https://github\.com/[^\s)\]]+/issues/\d+|#(\d+)",
    re.IGNORECASE,
)

CONCERN_RULES = {
    "Studio": [
        "studio",
        "handler",
        "cluster",
        "morph_key",
        "gloss",
        "pipeline",
        "staging",
    ],
    "Reader": [
        "reader",
        "passage",
        "auth",
        "translation",
        "annotations",
        "user db",
    ],
    "Lexis": [
        "lexis",
        "lexicon",
        "word detail",
        "insight",
        "morphology",
    ],
    "Importer": [
        "importer",
        "flyway",
        "schema",
        "dump",
        "restore",
        "load",
        "content db",
    ],
    "UI": [
        "ui",
        "frontend",
        "react",
        "apps/reader",
        "apps/studio",
    ],
    "User": [
        "user",
        "oauth",
        "jwt",
        "pro",
        "role",
        "account",
    ],
}


@dataclass
class Issue:
    url: str
    owner: str
    repo: str
    number: int
    title: str = ""
    state: str = "UNKNOWN"
    body: str = ""
    labels: list[str] = field(default_factory=list)
    fetch_error: str | None = None
    concern: str = "Cross-cutting"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit refactoring issues against DESIGN boundaries")
    parser.add_argument("--issues", nargs="*", default=DEFAULT_ISSUES, help="Issue URLs to seed the audit")
    parser.add_argument(
        "--gh-path",
        default="/c/Program Files/GitHub CLI/gh.exe",
        help="Path to GitHub CLI executable",
    )
    return parser.parse_args()


def parse_issue_url(url: str) -> tuple[str, str, int] | None:
    match = ISSUE_URL_RE.match(url.strip())
    if not match:
        return None
    owner, repo, number = match.group(1), match.group(2), int(match.group(3))
    return owner, repo, number


def _load_gh_token() -> str | None:
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("GH_TOKEN=") or line.startswith("GH_TOKEN_per="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def run_gh(gh_path: str, args: list[str]) -> tuple[int, str, str]:
    cmd = [gh_path, *args]
    env = dict(subprocess.os.environ)
    if "GH_TOKEN" not in env and "GITHUB_TOKEN" not in env:
        token = _load_gh_token()
        if token:
            env["GH_TOKEN"] = token
            env["GITHUB_TOKEN"] = token
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def resolve_gh_path(preferred: str) -> str:
    if preferred and Path(preferred).exists():
        return preferred

    path_gh = shutil.which("gh")
    if path_gh:
        return path_gh

    candidates = [
        r"C:\Program Files\GitHub CLI\gh.exe",
        r"/c/Program Files/GitHub CLI/gh.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate

    # Return preferred for a clear downstream error message.
    return preferred


def fetch_issue(gh_path: str, url: str) -> Issue:
    parsed = parse_issue_url(url)
    if not parsed:
        return Issue(url=url, owner="", repo="", number=-1, fetch_error=f"Invalid issue URL: {url}")

    owner, repo, number = parsed
    item = Issue(url=url, owner=owner, repo=repo, number=number)

    code, out, err = run_gh(
        gh_path,
        [
            "issue",
            "view",
            url,
            "--json",
            "number,title,state,body,labels,url",
        ],
    )

    if code != 0:
        item.fetch_error = (err or out).strip() or "Unknown gh error"
        return item

    data = json.loads(out)
    item.title = data.get("title", "")
    item.state = (data.get("state", "UNKNOWN") or "UNKNOWN").upper()
    item.body = data.get("body", "") or ""
    item.url = data.get("url", url)
    item.labels = [lbl.get("name", "") for lbl in (data.get("labels") or []) if lbl.get("name")]
    item.concern = classify_concern(item.title, item.body, item.labels)
    return item


def classify_concern(title: str, body: str, labels: Iterable[str]) -> str:
    text = f"{title}\n{body}\n{' '.join(labels)}".lower()
    concern_hits: dict[str, int] = {}

    for concern, keywords in CONCERN_RULES.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits:
            concern_hits[concern] = hits

    if not concern_hits:
        return "Cross-cutting"

    return max(concern_hits.items(), key=lambda kv: kv[1])[0]


def extract_sub_issue_urls(issue: Issue) -> set[str]:
    urls: set[str] = set()
    if not issue.body:
        return urls

    for match in SUB_ISSUE_LINK_RE.finditer(issue.body):
        token = match.group(0)
        if token.startswith("http"):
            parsed = parse_issue_url(token)
            if parsed:
                urls.add(token)
            continue

        # Handle shorthand #123 by assuming same repo.
        shorthand = match.group(1)
        if shorthand and issue.owner and issue.repo:
            urls.add(f"https://github.com/{issue.owner}/{issue.repo}/issues/{shorthand}")

    return urls


def print_report(seed_items: list[Issue], all_items: list[Issue]) -> None:
    print("=== Refactor Effort Audit (DESIGN-aligned) ===")
    print()

    errors = [i for i in all_items if i.fetch_error]
    if errors:
        print("[callout] Some issues could not be fetched:")
        for item in errors:
            print(f"- {item.url} -> {item.fetch_error}")
        print()

    valid_items = [i for i in all_items if not i.fetch_error]
    if not valid_items:
        print("No issue data available to classify. Resolve fetch errors above and re-run.")
        return

    done = [i for i in valid_items if i.state == "CLOSED"]
    open_items = [i for i in valid_items if i.state != "CLOSED"]

    print(f"Seed issues: {len(seed_items)}")
    print(f"Expanded issues (including sub-issues): {len(valid_items)}")
    print(f"Done: {len(done)} | Open: {len(open_items)}")
    print()

    by_concern: dict[str, list[Issue]] = {}
    for item in valid_items:
        by_concern.setdefault(item.concern, []).append(item)

    print("By concern:")
    for concern in ["Studio", "Reader", "Lexis", "Importer", "UI", "User", "Cross-cutting"]:
        group = by_concern.get(concern, [])
        if not group:
            continue
        done_count = sum(1 for i in group if i.state == "CLOSED")
        open_count = len(group) - done_count
        print(f"- {concern}: total={len(group)}, done={done_count}, open={open_count}")
    print()

    print("Open items to move into concern-specific epics:")
    for item in open_items:
        print(f"- [{item.concern}] {item.url} :: {item.title}")
    print()

    # Misalignment callout: seed issue mixes multiple concerns.
    seed_concerns = {i.concern for i in seed_items if not i.fetch_error}
    if len(seed_concerns) > 1:
        print("[callout] Seed set spans multiple concerns and is not single-epic clean:")
        print("- concerns detected: " + ", ".join(sorted(seed_concerns)))
        print("- recommendation: split remaining open items by concern epic (Studio/Reader/Lexis/User/Importer/UI)")
    else:
        print("Seed set is concern-consistent.")


def main() -> int:
    args = parse_args()
    args.gh_path = resolve_gh_path(args.gh_path)

    seed_urls = []
    for url in args.issues:
        parsed = parse_issue_url(url)
        if parsed:
            seed_urls.append(url)
        else:
            print(f"Skipping invalid issue URL: {url}")

    if not seed_urls:
        print("No valid issue URLs provided.")
        return 1

    seen: set[str] = set()
    seed_items: list[Issue] = []
    all_items: list[Issue] = []

    # Fetch seeds.
    for url in seed_urls:
        if url in seen:
            continue
        seen.add(url)
        item = fetch_issue(args.gh_path, url)
        seed_items.append(item)
        all_items.append(item)

    # Expand sub-issues once.
    sub_urls: set[str] = set()
    for item in seed_items:
        if not item.fetch_error:
            sub_urls.update(extract_sub_issue_urls(item))

    for url in sorted(sub_urls):
        if url in seen:
            continue
        seen.add(url)
        all_items.append(fetch_issue(args.gh_path, url))

    print_report(seed_items, all_items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
