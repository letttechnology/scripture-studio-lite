import os

brain_dir = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1"

print(f"Searching: {brain_dir}")

results = []
for root, dirs, files in os.walk(brain_dir):
    for file in files:
        path = os.path.join(root, file)
        try:
            size = os.path.getsize(path)
            # check files larger than 10KB
            if size > 10000:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if "AURA TRANSCRIBE" in content and "fun App(" in content:
                    mtime = os.path.getmtime(path)
                    results.append((path, size, mtime))
        except Exception:
            pass

print(f"Found {len(results)} files in brain:")
results.sort(key=lambda x: x[2], reverse=True)
for r in results:
    print(r)
