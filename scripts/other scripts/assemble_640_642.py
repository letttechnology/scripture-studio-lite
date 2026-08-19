import os
import json
import re

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"
dest = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"

contents = {}
with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx in [640, 642]:
            data = json.loads(line)
            contents[idx] = data.get("content", "")

# Extract line numbers and code lines
all_lines = {}
for step_idx in [640, 642]:
    content = contents.get(step_idx, "")
    lines = content.split("\n")
    for l in lines:
        m = re.match(r"^\s*(\d+):\s?(.*)", l)
        if m:
            ln = int(m.group(1))
            code = m.group(2)
            all_lines[ln] = code

# Append the startPlatformOAuth expected platform function
expect_declarations = """

expect fun startPlatformOAuth(
    provider: String,
    clientId: String,
    clientSecret: String,
    onSuccess: (String) -> Unit,
    onError: (String) -> Unit
)
"""

with open(dest, "w", encoding="utf-8") as out:
    for ln in sorted(all_lines.keys()):
        out.write(all_lines[ln] + "\n")
    out.write(expect_declarations)

print(f"Restored perfectly from Step 640 and 642! Total lines: {len(all_lines)}")
