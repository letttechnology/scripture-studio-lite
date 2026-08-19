import os
import json

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx == 637:
            data = json.loads(line)
            print("Step 637 content length:", len(data.get("content", "")))
            print("Step 637 content snippet:", data.get("content", "")[:300])
            print("Keys:", data.keys())
            # Let's inspect the first tool call response
            tool_calls = data.get("tool_calls", [])
            print("Tool calls count:", len(tool_calls))
            for tc in tool_calls:
                print("TC name:", tc.get("name"))
                print("TC response length:", len(str(tc.get("response", ""))))
