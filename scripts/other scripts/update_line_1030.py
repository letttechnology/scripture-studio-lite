with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Set line 1030 (index 1029, 0-indexed) to close brace
lines[1029] = "                }\n"

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Line 1030 updated successfully!")
