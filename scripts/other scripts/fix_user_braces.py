with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

lines = code.split("\n")

# Let's locate the double closing braces around line 841-844
target_idx = -1
for idx in range(len(lines) - 2):
    if lines[idx].strip() == "}" and lines[idx+1].strip() == "}" and "Spacer(modifier = Modifier.height(16.dp))" in lines[idx+3]:
        target_idx = idx + 1
        break

if target_idx != -1:
    print(f"Removing extra brace at line {target_idx + 2}!")
    # Delete the second brace (at target_idx + 1)
    lines = lines[:target_idx+1] + lines[target_idx+2:]
    
    with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Extra brace removed successfully!")
else:
    print("Error: Target double brace not found!")
