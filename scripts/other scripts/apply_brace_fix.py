with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

lines = code.split("\n")

# 1. Insert closing brace for settings Card
# Find the end of settings card.
# Line 841 has: }
# Line 843 has: Spacer(modifier = Modifier.height(16.dp))
# Let's find index where the lines contain these and insert a brace
target_idx = -1
for idx in range(len(lines) - 2):
    if lines[idx].strip() == "}" and "Spacer(modifier = Modifier.height(16.dp))" in lines[idx+2]:
        target_idx = idx + 1
        break

if target_idx != -1:
    lines.insert(target_idx, "                    }")
    print(f"Brace inserted at line {target_idx + 1}!")
else:
    print("Failed to find insert target for settings Card brace!")

# 2. Insert closing brace at end of App function
# Find where class TranscriptionJob starts
job_line = -1
for idx, line in enumerate(lines):
    if "class TranscriptionJob" in line:
        job_line = idx
        break

if job_line != -1:
    # insert a closing brace before it (separated by empty line)
    lines.insert(job_line, "}")
    print(f"Brace inserted before TranscriptionJob at line {job_line + 1}!")
else:
    print("Failed to find TranscriptionJob line!")

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("Brace fixes applied successfully!")
