import os
import datetime

appdata = os.environ.get("APPDATA")
history_path = os.path.join(appdata, "Code", "User", "History")

print(f"Searching in: {history_path}")

results = []
if os.path.exists(history_path):
    for root, dirs, files in os.walk(history_path):
        for file in files:
            path = os.path.join(root, file)
            try:
                size = os.path.getsize(path)
                if size > 50000 and not file.endswith(".json"):
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if "AURA TRANSCRIBE" in content and "fun App(" in content:
                        mtime = os.path.getmtime(path)
                        dt = datetime.datetime.fromtimestamp(mtime)
                        # Determine some layout indicators
                        has_compact_load = "// LOAD Button (compact)" in content or "LOAD Button (compact)" in content
                        has_merged = "val isMobile = maxWidth < 600.dp" in content
                        layout_desc = "Compact" if has_compact_load else ("Merged" if has_merged else "Original?")
                        results.append((path, size, mtime, dt, layout_desc))
            except Exception:
                pass

# Sort by modification time descending
results.sort(key=lambda x: x[2], reverse=True)

print(f"Found {len(results)} candidate files:")
for idx, (path, size, mtime, dt, layout) in enumerate(results):
    print(f"[{idx}] {dt} | Size: {size} bytes | Layout: {layout} | Path: {path}")
