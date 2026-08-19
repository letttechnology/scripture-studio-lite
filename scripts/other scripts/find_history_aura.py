import os
import datetime

history_path = r"C:\Users\blue1\AppData\Roaming\Code\User\History"
print(f"Scanning History: {history_path}")

candidates = []
for root, dirs, files in os.walk(history_path):
    for file in files:
        if file.endswith(".json"):
            continue
        path = os.path.join(root, file)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if "AURA TRANSCRIBE" in content:
                size = len(content)
                mtime = os.path.getmtime(path)
                dt = datetime.datetime.fromtimestamp(mtime)
                candidates.append((path, size, mtime, dt))
        except Exception:
            pass

candidates.sort(key=lambda x: x[2])
print(f"Found {len(candidates)} candidates:")
for path, size, mtime, dt in candidates:
    print(f"{dt} | Size: {size} | Path: {path}")
