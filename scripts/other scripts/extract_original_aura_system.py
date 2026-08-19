import os
import json
import re

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"
dest = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\assembled_original_aura_real.kt"

all_lines = {}

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            content = data.get("content", "")
            # We want to check if this is a tool response for App.kt viewing
            if "Showing lines" in content and "App.kt" in content:
                print(f"Step {idx} contains tool output of App.kt!")
                # Extract line numbers and code lines
                lines = content.split("\n")
                for l in lines:
                    m = re.match(r"^\s*(\d+):\s?(.*)", l)
                    if m:
                        ln = int(m.group(1))
                        code = m.group(2)
                        all_lines[ln] = code
        except Exception:
            pass

# Write the final assembled code
if all_lines:
    with open(dest, "w", encoding="utf-8") as out:
        for ln in sorted(all_lines.keys()):
            out.write(all_lines[ln] + "\n")
    print(f"Original visual App.kt saved to {dest}! Total lines: {len(all_lines)}")
else:
    print("No lines found!")
