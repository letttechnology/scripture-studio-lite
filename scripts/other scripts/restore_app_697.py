import os

src = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\assembled_original_aura_697.kt"
dest = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"

with open(src, "r", encoding="utf-8") as f:
    code = f.read()

# Append startPlatformOAuth expected platform function
expect_declarations = """

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

print("Restored original visual App.kt up to step 697!")
