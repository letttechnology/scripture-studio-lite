import json
import re

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"
steps = [270, 272, 407, 511, 640, 855, 1034, 1060, 1076]

for step in steps:
    with open(old_transcript, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx == step:
                data = json.loads(line)
                content = data.get("content", "")
                # Let's search for any data class or class or task list in content
                matches = re.findall(r"(data class \w+|class \w+|interface \w+|val \w+ = remember \{ mutableStateListOf)", content)
                if matches:
                    print(f"Step {step}: {matches}")
                    # Let's print some lines containing 'class' or list
                    for l in content.split("\n"):
                        if "class " in l or "mutableStateListOf" in l or "tab" in l.lower() or "task" in l.lower():
                            if any(w in l for w in ["Active", "Progress", "Queue", "Max", "List", "class"]):
                                print(f"   {l.strip()}")
