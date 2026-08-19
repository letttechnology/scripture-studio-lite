with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

opens = code.count("{")
closes = code.count("}")

print(f"Raw opens: {opens}")
print(f"Raw closes: {closes}")
print(f"Raw difference: {opens - closes}")
