import json
import re

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            content = data.get("content", "")
            
            # Look for "4" and "tab" in the same block of content
            if "tab" in content.lower() and "4" in content:
                # Let's print the step index and matching snippet
                print(f"Step {idx}:")
                # Print some matching lines from the content
                lines = content.split("\n")
                for l in lines:
                    if "tab" in l.lower() or "4" in l:
                        print(f"   {l.strip()[:120]}")
        except Exception:
            pass
