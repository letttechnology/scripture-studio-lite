import os
import json

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"
print(f"Reading from: {old_transcript}")

with open(old_transcript, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            # We want to check tool_calls
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                method = tc.get("name") or tc.get("method")
                args = tc.get("args") or tc.get("params") or {}
                if "write_to_file" in str(method) or "replace_file_content" in str(method):
                    content = args.get("CodeContent") or args.get("ReplacementContent") or ""
                    if "AURA TRANSCRIBE" in content and "fun App(" in content and len(content) > 100000:
                        print(f"Found COMPLETE file write! Size: {len(content)}")
                        with open(r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\recovered_full_app.txt", "w", encoding="utf-8") as out:
                            out.write(content)
                        print("Saved to recovered_full_app.txt!")
        except Exception:
            pass
