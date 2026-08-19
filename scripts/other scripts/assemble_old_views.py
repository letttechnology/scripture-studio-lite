import os
import json

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"
dest = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\assembled_old_app.kt"

# We want to find the last set of view_file calls that covered the entire App.kt file.
# Let's search from the end of the transcript backwards for view_file calls.
view_calls = []
with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            # Check if this is a SYSTEM message containing tool output or a model step
            # Actually, the tool output is stored in the SYSTEM message or in the tool response of the step.
            # Let's check both tc and system content.
            content = data.get("content", "")
            if "Showing lines" in content and "App.kt" in content:
                print(f"Step {idx} has view_file output! Length: {len(content)}")
                view_calls.append((idx, content))
        except Exception:
            pass

# Let's write the system contents to inspect them or assemble them
# We can find the group of views that happened around the same time.
# Let's sort them by step index.
view_calls.sort(key=lambda x: x[0])
for idx, content in view_calls:
    print(f"Step {idx}: Starts with {content[:100].replace(chr(10), ' ')}")

# The last views in the transcript should be the ones from the end of the previous session!
# Let's assemble the views from the end.
# Usually they are view_file for lines 1-800, 801-1600, etc.
# Let's write them all to a text file for inspection.
with open(r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\all_views.txt", "w", encoding="utf-8") as out:
    for idx, content in view_calls:
        out.write(f"=== STEP {idx} ===\n{content}\n\n")
print("All view contents saved to all_views.txt!")
