import json
import re

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx == 1036:
            data = json.loads(line)
            content = data.get("content", "")
            lines = content.split("\n")
            # Print lines 250 to 320 of this chunk (which has lines 151-950)
            # So lines 250 to 320 in the chunk correspond to lines 400 to 470 of the file!
            for l in lines[100:180]:
                print(l)
            break
