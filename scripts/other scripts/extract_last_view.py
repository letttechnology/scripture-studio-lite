import os
import json
import re

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"
dest = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\assembled_final_old_app.kt"

# We want to extract Step 1262 and Step 1270 contents
contents = {}
with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx in [1262, 1270]:
            data = json.loads(line)
            contents[idx] = data.get("content", "")

# Clean line numbers from each chunk
def clean_chunk(content):
    lines = content.split("\n")
    clean_lines = []
    for line in lines:
        m = re.match(r"^\s*\d+:\s?(.*)", line)
        if m:
            clean_lines.append(m.group(1))
        else:
            if "Showing lines" in line or "Total Lines" in line or "Total Bytes" in line or "Created At" in line or "Completed At" in line or "File Path" in line:
                continue
            clean_lines.append(line)
    return "\n".join(clean_lines)

chunk1 = clean_chunk(contents.get(1262, ""))
chunk2 = clean_chunk(contents.get(1270, ""))

# Join them
full_code = chunk1 + "\n" + chunk2

with open(dest, "w", encoding="utf-8") as out:
    out.write(full_code)

print(f"Assembled final App.kt saved to {dest}!")
