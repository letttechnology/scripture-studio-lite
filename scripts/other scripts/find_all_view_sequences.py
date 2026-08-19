import json

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"

views = []
with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        try:
            data = json.loads(line)
            # Find model steps that call view_file
            tool_calls = data.get("tool_calls", [])
            for tc in tool_calls:
                if tc.get("name") == "view_file":
                    args = tc.get("args") or tc.get("params") or {}
                    target = args.get("AbsolutePath") or args.get("TargetFile") or ""
                    if "App.kt" in target:
                        start = args.get("StartLine", 1)
                        end = args.get("EndLine", 800)
                        views.append((idx, start, end))
        except Exception:
            pass

# Group views that are close in step index
if views:
    current_group = [views[0]]
    for v in views[1:]:
        if v[0] - current_group[-1][0] <= 10:
            current_group.append(v)
        else:
            print(f"Group: Steps {[x[0] for x in current_group]} covering {[ (x[1], x[2]) for x in current_group ]}")
            current_group = [v]
    print(f"Group: Steps {[x[0] for x in current_group]} covering {[ (x[1], x[2]) for x in current_group ]}")
else:
    print("No views found!")
