import os

workspace = r"d:\workspace-vscode-antigravity"

print(f"Searching workspace: {workspace}")

results = []
for root, dirs, files in os.walk(workspace):
    # skip .git and build dirs to go faster
    if ".git" in root or "build" in root or ".gradle" in root:
        continue
    for file in files:
        if "App.kt" in file:
            path = os.path.join(root, file)
            size = os.path.getsize(path)
            mtime = os.path.getmtime(path)
            results.append((path, size, mtime))

print(f"Found {len(results)} files:")
for r in results:
    print(r)
