import os
import json

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            # check content or tool calls
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                args = tc.get("args") or tc.get("params") or {}
                target = args.get("TargetFile") or args.get("AbsolutePath") or ""
                if "App.kt" in target:
                    content = args.get("CodeContent") or args.get("ReplacementContent") or ""
                    print(f"Step {idx}: Method={tc.get('name')}, Size={len(content)}")
        except Exception:
            pass
