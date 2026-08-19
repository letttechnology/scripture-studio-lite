with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Revert Box start changes
# Replace val mainContent: @Composable BoxScope.() -> Unit = { ... val boxScope = this
# back to Box(...) {
boxScope_decl = "val mainContent: @Composable BoxScope.() -> Unit = {\n        val boxScope = this"
original_box_start = """        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(BgDark)
                .padding(16.dp),
            contentAlignment = Alignment.TopCenter
        ) {"""

if boxScope_decl in code:
    code = code.replace(boxScope_decl, original_box_start, 1)
    print("Box start reverted successfully!")
else:
    # Check if boxScope is there without newlines
    if "val mainContent: @Composable BoxScope.() -> Unit = {" in code:
        code = code.replace("val mainContent: @Composable BoxScope.() -> Unit = {", original_box_start, 1)
        # remove val boxScope = this if present
        code = code.replace("        val boxScope = this\n", "")
        print("Box start reverted (fallback)!")

# 2. Revert Box end changes
# Replace the end box call back to the original 3 closing braces
end_box_call = """        }
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(BgDark)
                .padding(16.dp),
            contentAlignment = Alignment.TopCenter,
            content = mainContent
        )
    }
}"""

original_end = """        }
    }
}"""

if end_box_call in code:
    code = code.replace(end_box_call, original_end, 1)
    print("Box end reverted successfully!")

# 3. Clean up the explicit with(boxScope) calls we added
code = code.replace("with(boxScope) { Modifier.align(Alignment.Center) }", "Modifier.align(Alignment.Center)")
code = code.replace("with(boxScope) { Modifier.align(Alignment.BottomCenter) }", "Modifier.align(Alignment.BottomCenter)")

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.write(code)

print("BoxScope wrap reverted completely!")
