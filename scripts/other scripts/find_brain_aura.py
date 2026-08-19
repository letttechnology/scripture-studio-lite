import os

brain_path = r"C:\Users\blue1\.gemini\antigravity-ide\brain"
print(f"Scanning Brain: {brain_path}")

candidates = []
for root, dirs, files in os.walk(brain_path):
    for file in files:
        path = os.path.join(root, file)
        try:
            # check files larger than 1KB and smaller than 5MB
            size = os.path.getsize(path)
            if 1000 < size < 5000000:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if "LOAD" in content or "formatDuration" in content:
                    # Let's count occurrences of "AURA TRANSCRIBE"
                    if "AURA TRANSCRIBE" in content:
                        candidates.append((path, size, os.path.getmtime(path)))
        except Exception:
            pass

print(f"Found {len(candidates)} files:")
for path, size, mtime in candidates:
    print(f"Size: {size} | MTime: {mtime} | Path: {path}")
