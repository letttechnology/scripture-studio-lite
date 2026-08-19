with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# We will search for all AnimatedVisibility blocks that have Modifier.align
# and replace them.
# Let's locate them by searching:
# AnimatedVisibility(
#     ...
#     modifier = Modifier.align(...)
# ) {
#     Card(...) {
#         ...
#     }
# }

import re

# We can match AnimatedVisibility( ... modifier = Modifier.align(...) ) {
# and extract the full content, trace the braces of the lambda, and rewrite it.

pattern = re.compile(
    r'(AnimatedVisibility\(\s*visible\s*=\s*\w+,\s*modifier\s*=\s*Modifier\.align\((Alignment\.(Center|BottomCenter))\)\s*\)\s*\{)'
)

# Let's find all matches
idx = 0
while True:
    match = pattern.search(code, idx)
    if not match:
        break
    
    start_pos = match.start()
    header_end_pos = match.end()
    align_type = match.group(2) # e.g. Alignment.Center or Alignment.BottomCenter
    
    # Trace braces from header_end_pos to find the closing brace of the AnimatedVisibility block
    depth = 1 # We are inside the AnimatedVisibility content lambda
    pos = header_end_pos
    in_string = False
    in_comment = False
    in_block_comment = False
    n = len(code)
    
    while pos < n and depth > 0:
        # standard Kotlin char check
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
        
    # pos is now the index of the closing brace '}' of the AnimatedVisibility block
    if depth == 0:
        # We rewrite this block:
        # AnimatedVisibility(...) {
        #     Box(modifier = Modifier.fillMaxSize(), contentAlignment = align_type) {
        #          ...original contents...
        #     }
        # }
        
        orig_header = match.group(1)
        visible_expr = orig_header.split("visible = ")[1].split(",")[0].strip()
        
        # New header
        new_header = f"""AnimatedVisibility(
                visible = {visible_expr},
                modifier = Modifier.fillMaxSize()
            ) {{
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = {align_type}
                ) {{"""
        
        # Replace header and add Box closing brace before the AnimatedVisibility closing brace
        block_content = code[header_end_pos:pos]
        new_block = new_header + block_content + "\n                }\n            }"
        
        # Replace in code
        code = code[:start_pos] + new_block + code[pos+1:]
        print(f"Successfully wrapped dialog {visible_expr} with centering Box!")
        
        # Update search index (we modified the string length, so let's start next search from start_pos + len(new_block))
        idx = start_pos + len(new_block)
    else:
        print("Failed to find closing brace for a match!")
        break

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.write(code)

print("Box wrappers applied!")
