import os
import json

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"
print(f"Reading from: {old_transcript}")

if not os.path.exists(old_transcript):
    print("Old transcript does not exist!")
    sys.exit(1)

with open(old_transcript, "r", encoding="utf-8") as f:
    for line in f:
        try:
            data = json.loads(line)
            content = data.get("content", "")
            if "AURA TRANSCRIBE" in content and "fun App(" in content and len(content) > 10000:
                print(f"Found candidate! Size: {len(content)}")
                # save it
                with open(r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\recovered_old_app.txt", "w", encoding="utf-8") as out:
                    out.write(content)
                print("Saved to recovered_old_app.txt!")
        except Exception:
            pass
