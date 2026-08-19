import os

src = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\step_175_app.kt"
dest = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"

with open(src, "r", encoding="utf-8") as f:
    code = f.read()

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
    f.write(code)
    f.write(expect_declarations)

print("Directly restored App.kt!")
