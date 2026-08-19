import os
import json
import re

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"
dest = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\assembled_original_aura.kt"

target_steps = [637, 639, 641, 690, 692, 696, 698]
contents = {}

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx in target_steps:
            data = json.loads(line)
            contents[idx] = data.get("content", "")

# Extract all code lines with their line numbers
all_lines = {}
for step_idx in target_steps:
    content = contents.get(step_idx, "")
    lines = content.split("\n")
    for line in lines:
        m = re.match(r"^\s*(\d+):\s?(.*)", line)
        if m:
            ln = int(m.group(1))
            code = m.group(2)
            all_lines[ln] = code

# Write the final assembled code
with open(dest, "w", encoding="utf-8") as out:
    for ln in sorted(all_lines.keys()):
        out.write(all_lines[ln] + "\n")

print(f"Original visual App.kt saved to {dest}! Total lines: {len(all_lines)}")
