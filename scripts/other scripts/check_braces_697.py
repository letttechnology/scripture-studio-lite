# Tracing brackets in App.kt
with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    lines = f.readlines()

depth = 0
for idx, line in enumerate(lines):
    stripped = line.strip()
    # Simple brace counting
    opens = stripped.count("{")
    closes = stripped.count("}")
    net = opens - closes
    if net != 0:
        print(f"Line {idx+1:4d}: {stripped[:50]} (net={net:2d}, depth={depth} -> {depth+net})")
        depth += net
