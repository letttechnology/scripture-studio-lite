import re

src = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\step_175_app.kt"
dest = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"

with open(src, "r", encoding="utf-8") as f:
    lines = f.readlines()

clean_lines = []
for line_idx, line in enumerate(lines):
    # Skip the first 7 metadata lines
    if line_idx < 7:
        continue
    
    # We want to match: line_number: [code_line_number:] code
    # e.g. "8: 1: import ..."
    # Let's clean it iteratively
    s = line.strip("\r\n")
    
    # Strip first line number prefix (e.g. "8: ")
    m1 = re.match(r"^\s*\d+:\s?(.*)", s)
    if m1:
        s = m1.group(1)
        # Strip second line number prefix (e.g. "1: ")
        m2 = re.match(r"^\s*\d+:\s?(.*)", s)
        if m2:
            s = m2.group(1)
        clean_lines.append(s + "\n")
    else:
        if s.strip() == "":
            clean_lines.append("\n")

# Append expected platform-specific functions
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

with open(dest, "w", encoding="utf-8") as f:
    f.writelines(clean_lines)
    f.write(expect_declarations)

print("Double cleaned App.kt generated in workspace!")
