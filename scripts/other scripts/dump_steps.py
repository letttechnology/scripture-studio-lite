import os
import json

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx in [1262, 1270]:
            data = json.loads(line)
            content = data.get("content", "")
            with open(f"C:\\Users\\blue1\\.gemini\\antigravity-ide\\brain\\26225130-f206-43ae-a1b2-908d3a977cd1\\scratch\\step_{idx}_content.txt", "w", encoding="utf-8") as out:
                out.write(content)
            print(f"Dumped step {idx} content, length = {len(content)}")
