with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if "showSettings" in line:
            print(f"Line {idx+1}: {line.strip()}")
