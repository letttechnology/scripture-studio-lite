import json
import re

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            content = data.get("content", "")
            if "Showing lines" in content and "App.kt" in content:
                # Let's search if this chunk contains the record button layout
                if "LOAD AUDIO" in content or "timer" in content or "Tap to Record" in content or "isRecording" in content:
                    # Let's print the step index and lines matching the record button row or layout
                    lines = content.split("\n")
                    # Let's see if there is a Row or Box for the record button
                    has_row = any("Row" in l for l in lines)
                    has_load = any("LOAD AUDIO" in l for l in lines)
                    # Print some lines around the record button
                    match_lines = [l.strip() for l in lines if "LOAD AUDIO" in l or "formatDuration" in l]
                    print(f"Step {idx}: has_row={has_row}, has_load={has_load}, matches={match_lines}")
        except Exception:
            pass
