import os
import json
import re

old_transcript = r"C:\Users\blue1\.gemini\antigravity-ide\brain\2be073ed-4b27-4fb4-8f23-f8dff10d4100\.system_generated\logs\transcript_full.jsonl"
dest = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"

all_lines = {}

with open(old_transcript, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if idx > 697:
            break
        try:
            data = json.loads(line)
            content = data.get("content", "")
            if "Showing lines" in content:
                # Extract File Path line
                fp_line = [l for l in content.split("\n") if "File Path:" in l]
                if fp_line:
                    fp = fp_line[0].replace("\\", "/")
                    if "commonMain/kotlin/App.kt" in fp:
                        print(f"Step {idx} is a valid App.kt output! Path: {fp}")
                        lines = content.split("\n")
                        for l in lines:
                            m = re.match(r"^\s*(\d+):\s?(.*)", l)
                            if m:
                                ln = int(m.group(1))
                                code = m.group(2)
                                all_lines[ln] = code
        except Exception as e:
            pass

# Write the final assembled code
if all_lines:
    expect_declarations = """

expect fun getPlatformDefaultDirectory(): String

expect fun saveTextToFile(text: String, path: String)

expect fun getFormattedDateTimeString(): String

expect fun moveFile(sourcePath: String, destPath: String): Boolean

expect fun startPlatformOAuth(
    provider: String,
    clientId: String,
    clientSecret: String,
    onSuccess: (String) -> Unit,
    onError: (String) -> Unit
)
"""
    with open(dest, "w", encoding="utf-8") as out:
        for ln in sorted(all_lines.keys()):
            out.write(all_lines[ln] + "\n")
        out.write(expect_declarations)
    print(f"Original visual App.kt up to step 697 saved! Total lines: {len(all_lines)}")
else:
    print("No lines found!")
