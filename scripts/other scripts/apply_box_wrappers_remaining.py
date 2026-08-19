with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

import re

# More general pattern that allows anything except commas/newlines for the visible value
pattern = re.compile(
    r'(AnimatedVisibility\(\s*visible\s*=\s*([^,\n]+),\s*modifier\s*=\s*Modifier\.align\((Alignment\.(Center|BottomCenter))\)\s*\)\s*\{)'
)

idx = 0
while True:
    match = pattern.search(code, idx)
    if not match:
        break
    
    start_pos = match.start()
    header_end_pos = match.end()
    visible_expr = match.group(2).strip()
    align_type = match.group(3)
    
    # Trace braces to find block end
    depth = 1
    pos = header_end_pos
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
        if code[pos:pos+3] == '"""':
            pos += 3
            while pos < n and code[pos:pos+3] != '"""':
                pos += 1
            pos += 3
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
        new_header = f"""AnimatedVisibility(
                visible = {visible_expr},
                modifier = Modifier.fillMaxSize()
            ) {{
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = {align_type}
                ) {{"""
        
        block_content = code[header_end_pos:pos]
        new_block = new_header + block_content + "\n                }\n            }"
        
        code = code[:start_pos] + new_block + code[pos+1:]
        print(f"Successfully wrapped dialog '{visible_expr}' with Box!")
        idx = start_pos + len(new_block)
    else:
        print("Failed to find closing brace for match!")
        break

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.write(code)

print("Remaining Box wrappers applied successfully!")
