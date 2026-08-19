import re

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# Search for declarations: val Box, var Box, fun Box, class Box, etc.
declarations = re.findall(r'\b(val|var|fun|class)\s+Box\b', code)
print("Declarations of Box:", declarations)

# Print all occurrences of "Box" with context
lines = code.split("\n")
for idx, line in enumerate(lines):
    if "Box" in line:
        print(f"Line {idx+1:4d}: {line.strip()}")
