with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

lines = code.split("\n")
for idx, line in enumerate(lines):
    if "isTranscribing" in line:
        print(f"Line {idx+1:4d}: {line.strip()}")
