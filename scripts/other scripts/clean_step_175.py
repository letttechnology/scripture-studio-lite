import re

src = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\step_175_app.kt"
dest = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"

with open(src, "r", encoding="utf-8") as f:
    lines = f.readlines()

clean_lines = []
for line in lines:
    m = re.match(r"^\s*\d+:\s?(.*)", line)
    if m:
        clean_lines.append(m.group(1) + "\n")
    else:
        if line.strip() == "":
            clean_lines.append("\n")

# Append expected platform-specific functions that were added in later stages of previous session
expect_declarations = """

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

with open(dest, "w", encoding="utf-8") as f:
    f.writelines(clean_lines)
    f.write(expect_declarations)

print("Clean App.kt generated in workspace!")
