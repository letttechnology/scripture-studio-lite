with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Replace snackbar header
# We search for:
# AnimatedVisibility(
#     visible = statusMessage.isNotEmpty(),
#     modifier = Modifier
#         .align(Alignment.BottomCenter)
#     ...
# ) {
#     Card(

import re

header_pattern = re.compile(
    r'AnimatedVisibility\(\s*visible\s*=\s*statusMessage\.isNotEmpty\(\),\s*modifier\s*=\s*Modifier\s*\n?\s*\.align\(Alignment\.BottomCenter\)\s*\n?\s*\.padding\(bottom\s*=\s*24\.dp\)\s*\n?\s*\.fillMaxWidth\(0\.9f\)\s*\n?\s*\.widthIn\(max\s*=\s*500\.dp\)\s*\)\s*\{'
)

# Let's check if we can find this header
match = header_pattern.search(code)
if match:
    start_pos = match.start()
    header_end = match.end()
    
    # Trace braces to find where AnimatedVisibility content lambda closes
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
        # We replace the header and insert closing brace for Box at pos
        new_header = """AnimatedVisibility(
                visible = statusMessage.isNotEmpty(),
                modifier = Modifier.fillMaxSize()
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(bottom = 24.dp),
                    contentAlignment = Alignment.BottomCenter
                ) {"""
        
        block_content = code[header_end:pos]
        # We find the Card start inside block_content and keep it.
        # But wait! The Card in the original was indent-aligned.
        # Let's replace the block
        new_block = new_header + block_content + "\n                }\n            }"
        
        code = code[:start_pos] + new_block + code[pos+1:]
        print("Snackbar wrapped successfully!")
    else:
        print("Failed to find end of snackbar block!")
else:
    print("Snackbar header target NOT found!")

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.write(code)

print("Updates complete!")
