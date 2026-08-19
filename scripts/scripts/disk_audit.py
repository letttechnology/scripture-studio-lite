#!/usr/bin/env python3
"""Disk-space audit: where did the space go?

Reports, in order:
  1. Free/used space per drive
  2. Windows system files that silently eat the system drive (pagefile, hiberfil)
  3. Known dev-tooling hogs (Docker vhdx, WSL distros, Maven repo, npm/pip caches,
     Claude Code data, IDE caches, recycle bin)
  4. The largest immediate subdirectories of a target directory (default: the user
     profile), so the "unknown" bulk always has a name

Usage:
    python scripts/disk_audit.py                 # audit with defaults
    python scripts/disk_audit.py --top C:/some/dir --limit 25
    python scripts/disk_audit.py --no-scan       # skip the (slow) subdirectory scan

Read-only: measures only, deletes nothing.
"""
import argparse
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOME = os.path.expanduser("~")
LOCAL = os.path.join(HOME, "AppData", "Local")
ROAMING = os.path.join(HOME, "AppData", "Roaming")

KNOWN_PATHS = [
    ("Windows pagefile",        r"C:\pagefile.sys"),
    ("Windows hibernation",     r"C:\hiberfil.sys"),
    ("Windows swapfile",        r"C:\swapfile.sys"),
    ("Docker virtual disk",     os.path.join(LOCAL, "Docker", "wsl", "disk", "docker_data.vhdx")),
    ("Docker (all)",            os.path.join(LOCAL, "Docker")),
    ("WSL distro disks",        os.path.join(LOCAL, "Packages")),  # vhdx files live under per-distro packages
    ("Maven repo (~/.m2)",      os.path.join(HOME, ".m2")),
    ("npm cache",               os.path.join(LOCAL, "npm-cache")),
    ("pip cache",               os.path.join(LOCAL, "pip", "cache")),
    ("Claude Code data",        os.path.join(HOME, ".claude")),
    ("Claude temp scratchpads", os.path.join(LOCAL, "Temp", "claude")),
    ("Temp (all)",              os.path.join(LOCAL, "Temp")),
    ("Downloads",               os.path.join(HOME, "Downloads")),
    ("Recycle bin (C:)",        r"C:\$Recycle.Bin"),
    ("VS Code (Roaming)",       os.path.join(ROAMING, "Code")),
    ("JetBrains caches",        os.path.join(LOCAL, "JetBrains")),
]


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"


def du(path: str) -> int:
    """Recursive size of a file or directory; unreadable entries count as 0."""
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    total = 0
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def section(title: str):
    print(f"\n=== {title} " + "=" * max(0, 60 - len(title)))


def main():
    ap = argparse.ArgumentParser(description="Read-only disk-space audit")
    ap.add_argument("--top", default=HOME,
                    help="Directory whose immediate subdirectories get sized (default: user profile)")
    ap.add_argument("--limit", type=int, default=20, help="How many largest subdirectories to show")
    ap.add_argument("--no-scan", action="store_true", help="Skip the slow subdirectory scan")
    args = ap.parse_args()

    section("Drives")
    for drive in ("C:\\", "D:\\", "E:\\"):
        if os.path.exists(drive):
            u = shutil.disk_usage(drive)
            pct = u.used / u.total * 100
            flag = "  << CRITICAL" if u.free < 5 * 2**30 else ""
            print(f"  {drive}  total {human(u.total):>9}  used {human(u.used):>9} ({pct:.0f}%)  free {human(u.free):>9}{flag}")

    section("Known space consumers")
    rows = []
    for label, path in KNOWN_PATHS:
        if os.path.exists(path):
            rows.append((du(path), label, path))
    for size, label, path in sorted(rows, reverse=True):
        print(f"  {human(size):>9}  {label:<24} {path}")

    if not args.no_scan:
        section(f"Largest subdirectories of {args.top}")
        subs = []
        try:
            with os.scandir(args.top) as it:
                for e in it:
                    if e.is_dir(follow_symlinks=False):
                        subs.append((du(e.path), e.path))
                    elif e.is_file(follow_symlinks=False):
                        try:
                            subs.append((e.stat().st_size, e.path))
                        except OSError:
                            pass
        except OSError as ex:
            print(f"  cannot scan: {ex}")
        for size, path in sorted(subs, reverse=True)[: args.limit]:
            if size > 100 * 2**20:  # only entries above 100 MB matter for an audit
                print(f"  {human(size):>9}  {path}")

    print("\nDone. Nothing was modified or deleted.")


if __name__ == "__main__":
    main()
