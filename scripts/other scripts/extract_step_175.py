import os
import json

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"
dest = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\step_175_app.kt"

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx == 175:
            data = json.loads(line)
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                args = tc.get("args") or tc.get("params") or {}
                content = args.get("CodeContent") or args.get("ReplacementContent") or ""
                with open(dest, "w", encoding="utf-8") as out:
                    out.write(content)
                print(f"Successfully extracted step 175 to {dest}!")
                break
