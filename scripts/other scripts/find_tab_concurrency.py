import json
import re

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            content = data.get("content", "")
            # We want to search for any code snippet containing "tab" or "tabs" or "TranscriptionTask"
            if "Showing lines" in content and "App.kt" in content:
                # Check for specific words: "maxTabs", "Tab", "ActiveTab", "Task" in code
                lines = content.split("\n")
                code_lines = [l.strip() for l in lines if re.search(r"\b(maxTabs|transcriptionTasks|activeTasks|tabCount|tabIndex|4)\b", l, re.I)]
                if code_lines and any("tab" in l.lower() or "task" in l.lower() for l in code_lines):
                    # Check if there is actual tab logic
                    has_tab_logic = any("tab" in l.lower() for l in code_lines)
                    if has_tab_logic:
                        print(f"Step {idx}: matched with code lines:")
                        for cl in code_lines[:10]:
                            print(f"   {cl}")
        except Exception:
            pass
