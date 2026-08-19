import json

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx == 1036:
            data = json.loads(line)
            content = data.get("content", "")
            lines = content.split("\n")
            # Print lines 220 to 400 of the chunk (which has lines 151-950)
            # This corresponds to lines 371-551 of the file!
            for l in lines[200:300]:
                print(l)
            break
