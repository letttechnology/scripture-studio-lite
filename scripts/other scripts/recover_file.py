import os
import json

log_dir = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\.system_generated\logs"
trans_path = os.path.join(log_dir, "transcript_full.jsonl")

# Let's search for recent write_to_file or replace_file_content calls, or view_file outputs that had the file content.
# Wait, can we read the lines of transcript_full.jsonl?
if not os.path.exists(trans_path):
    print("Transcript full not found, trying transcript.jsonl")
    trans_path = os.path.join(log_dir, "transcript.jsonl")

if not os.path.exists(trans_path):
    print("No transcript files found!")
    sys.exit(1)

print(f"Reading from: {trans_path}")

# Let's read the lines backwards to find the last complete content or parts
with open(trans_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Total steps in transcript: {len(lines)}")

# We can search for the last tool call output or arguments that contain a large block of Kotlin code (e.g. "@Composable\nfun App")
# Let's search backwards
for idx in range(len(lines) - 1, -1, -1):
    line = lines[idx]
    if "App.kt" in line and "fun App(" in line:
        print(f"Found match at step index {idx}!")
        # Let's try to parse the JSON and print some info
        try:
            data = json.loads(line)
            # Check what's inside
            print("Keys:", data.keys())
            print("Type:", data.get("type"))
            # If it's a tool response or request, let's extract it
            content = data.get("content", "")
            if len(content) > 10000:
                print(f"Content length: {len(content)}")
                # Let's write it to a recovery file
                recovery_path = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\recovery.txt"
                with open(recovery_path, "w", encoding="utf-8") as rf:
                    rf.write(content)
                print(f"Saved large content to {recovery_path}")
        except Exception as e:
            print("Error parsing line:", e)
