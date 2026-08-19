import os
import datetime

user_dir = r"C:\Users\blue1"
print(f"Scanning User Profile: {user_dir}")

candidates = []
for root, dirs, files in os.walk(user_dir):
    # Exclude AppData\Local\Microsoft or large directories to avoid slow search
    if "AppData\\Local\\Microsoft" in root or "AppData\\Local\\Google" in root or "node_modules" in root or ".git" in root:
        continue
    for file in files:
        if file.endswith(".kt") or file.endswith(".txt") or file.endswith(".kt.bak") or "App" in file:
            path = os.path.join(root, file)
            try:
                # Only check if size is reasonable
                size = os.path.getsize(path)
                if 10000 < size < 300000:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(2000)
                    if "AURA TRANSCRIBE" in content:
                        mtime = os.path.getmtime(path)
                        dt = datetime.datetime.fromtimestamp(mtime)
                        candidates.append((path, size, mtime, dt))
            except Exception:
                pass

candidates.sort(key=lambda x: x[2])
print(f"Found {len(candidates)} candidates:")
for path, size, mtime, dt in candidates:
    print(f"{dt} | Size: {size} | Path: {path}")
