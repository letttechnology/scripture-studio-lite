import os
import json
import re

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"
dest = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\assembled_clean_old_app.kt"

# We want to extract Step 1262 and Step 1270 contents
contents = {}
with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx in [1262, 1270]:
            data = json.loads(line)
            contents[idx] = data.get("content", "")

# Clean line numbers from each chunk
def clean_chunk_to_lines(content):
    lines = content.split("\n")
    clean = []
    for line in lines:
        m = re.match(r"^\s*(\d+):\s?(.*)", line)
        if m:
            line_num = int(m.group(1))
            code_line = m.group(2)
            clean.append((line_num, code_line))
    return clean

lines_1262 = clean_chunk_to_lines(contents.get(1262, ""))
lines_1270 = clean_chunk_to_lines(contents.get(1270, ""))

# Combine all lines and sort by line number to guarantee perfect order
all_lines = {}
for ln, code in lines_1262:
    all_lines[ln] = code
for ln, code in lines_1270:
    all_lines[ln] = code

# Write the final assembled code
with open(dest, "w", encoding="utf-8") as out:
    for ln in sorted(all_lines.keys()):
        out.write(all_lines[ln] + "\n")

print(f"Perfect assembled final App.kt saved to {dest}! Total lines: {len(all_lines)}")
