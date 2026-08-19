with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# Normalize line endings to \n
code_norm = code.replace("\r\n", "\n")

orig_header = """            AnimatedVisibility(
                visible = statusMessage.isNotEmpty(),
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 24.dp)
                    .fillMaxWidth(0.9f)
                    .widthIn(max = 500.dp)
            ) {"""

new_header = """            AnimatedVisibility(
                visible = statusMessage.isNotEmpty(),
                modifier = Modifier.fillMaxSize()
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(bottom = 24.dp),
                    contentAlignment = Alignment.BottomCenter
                ) {"""

if orig_header in code_norm:
    idx = code_norm.index(orig_header)
    header_end = idx + len(orig_header)
    
    # Trace braces to find where AnimatedVisibility closes
    depth = 1
    pos = header_end
    n = len(code_norm)
    while pos < n and depth > 0:
        if code_norm[pos:pos+2] == "/*":
            pos += 2
            while pos < n and code_norm[pos:pos+2] != "*/":
                pos += 1
            pos += 2
            continue
        if code_norm[pos:pos+2] == "//":
            while pos < n and code_norm[pos] != "\n":
                pos += 1
            continue
        if code_norm[pos] == '"':
            pos += 1
            while pos < n and code_norm[pos] != '"':
                if code_norm[pos] == '\\':
                    pos += 2
                else:
                    pos += 1
            pos += 1
            continue
        if code_norm[pos] == '{':
            depth += 1
        elif code_norm[pos] == '}':
            depth -= 1
        if depth == 0:
            break
        pos += 1
        
    if depth == 0:
        block_content = code_norm[header_end:pos]
        new_block = new_header + block_content + "\n                }\n            }"
        code_norm = code_norm[:idx] + new_block + code_norm[pos+1:]
        print("Snackbar wrapped successfully!")
        
        # Write back (converting \n back to original \r\n if needed, or just keeping \n since git/kotlin handles \n perfectly)
        with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
            f.write(code_norm)
    else:
        print("Failed to find end of snackbar block!")
else:
    print("Snackbar header target NOT found!")

print("Updates complete!")
