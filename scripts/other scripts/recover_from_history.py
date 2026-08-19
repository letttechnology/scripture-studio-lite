import os
import glob

appdata = os.environ.get("APPDATA")
history_path = os.path.join(appdata, "Code", "User", "History")

print(f"Searching in: {history_path}")

# VS Code history folders contain randomly named subdirectories, and files inside them keep their content but have random names.
# Each folder contains a "entries.json" that lists the original filenames, or we can just search files containing "AURA TRANSCRIBE".
# Let's search recursively for all files in the history directory containing "AURA TRANSCRIBE".

results = []
if os.path.exists(history_path):
    for root, dirs, files in os.walk(history_path):
        for file in files:
            path = os.path.join(root, file)
            try:
                # Check file size (usually App.kt was > 100KB)
                size = os.path.getsize(path)
                if size > 50000:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if "AURA TRANSCRIBE" in content and "fun App(" in content:
                        mtime = os.path.getmtime(path)
                        results.append((path, size, mtime, content))
            except Exception:
                pass

print(f"Found {len(results)} candidate files in VS Code history!")

# Sort by modification time descending to get the most recent save
results.sort(key=lambda x: x[2], reverse=True)

if results:
    latest_path, latest_size, latest_mtime, latest_content = results[0]
    print(f"Latest candidate file: {latest_path} (Size: {latest_size} bytes, Modified: {latest_mtime})")
    
    # Let's write the recovered content back to shared/src/commonMain/kotlin/App.kt!
    dest_path = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(latest_content)
    print(f"Successfully recovered App.kt to {dest_path}!")
else:
    print("No candidate files found in local history!")
