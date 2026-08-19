with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add boxScope declaration at the start of mainContent
start_target = "val mainContent: @Composable BoxScope.() -> Unit = {"
start_replacement = start_target + "\n        val boxScope = this"

if start_target in code and start_replacement not in code:
    code = code.replace(start_target, start_replacement, 1)
    print("boxScope declaration added successfully!")
else:
    print("boxScope start target NOT found or already added.")

# 2. Replace align(Alignment.Center) occurrences
# We want to be careful to only replace the ones that are unresolved
# Let's replace they are Modifier.align(...)
code = code.replace("Modifier.align(Alignment.Center)", "with(boxScope) { Modifier.align(Alignment.Center) }")
code = code.replace("Modifier.align(Alignment.BottomCenter)", "with(boxScope) { Modifier.align(Alignment.BottomCenter) }")

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.write(code)

print("Alignment wrapper applied successfully!")
