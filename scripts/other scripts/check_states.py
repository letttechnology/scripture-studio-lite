with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

lines = code.split("\n")
for idx in range(70, 95):
    print(f"Line {idx+1}: {lines[idx]}")
