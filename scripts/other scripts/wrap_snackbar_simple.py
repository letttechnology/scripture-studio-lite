with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

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

if orig_header in code:
    idx = code.index(orig_header)
    header_end = idx + len(orig_header)
    
    # Trace braces to find where AnimatedVisibility closes
    depth = 1
    pos = header_end
    n = len(code)
    while pos < n and depth > 0:
        if code[pos:pos+2] == "/*":
            pos += 2
            while pos < n and code[pos:pos+2] != "*/":
                pos += 1
            pos += 2
            continue
        if code[pos:pos+2] == "//":
            while pos < n and code[pos] != "\n":
                pos += 1
            continue
        if code[pos] == '"':
            pos += 1
            while pos < n and code[pos] != '"':
                if code[pos] == '\\':
                    pos += 2
                else:
                    pos += 1
            pos += 1
            continue
        if code[pos] == '{':
            depth += 1
        elif code[pos] == '}':
            depth -= 1
        if depth == 0:
            break
        pos += 1
        
    if depth == 0:
        block_content = code[header_end:pos]
        new_block = new_header + block_content + "\n                }\n            }"
        code = code[:idx] + new_block + code[pos+1:]
        print("Snackbar wrapped successfully!")
    else:
        print("Failed to find end of snackbar block!")
else:
    print("Snackbar header target NOT found!")

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.write(code)

print("Updates complete!")
