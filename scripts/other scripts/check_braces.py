with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

depth = 0
lines = code.split("\n")
for idx, line in enumerate(lines):
    # Count open and close braces in this line
    # Simple character parsing that ignores strings/comments if possible
    # But since we just want a rough check, let's parse chars
    in_string = False
    in_comment = False
    in_block_comment = False
    i = 0
    opens = 0
    closes = 0
    while i < len(line):
        if in_block_comment:
            if i + 1 < len(line) and line[i:i+2] == "*/":
                in_block_comment = False
                i += 2
                continue
        elif in_comment:
            break
        elif in_string:
            if line[i] == '"' and (i == 0 or line[i-1] != '\\'):
                in_string = False
        else:
            if i + 1 < len(line) and line[i:i+2] == "//":
                in_comment = True
                break
            elif i + 1 < len(line) and line[i:i+2] == "/*":
                in_block_comment = True
                i += 2
                continue
            elif line[i] == '"':
                in_string = True
            elif line[i] == '{':
                opens += 1
            elif line[i] == '}':
                closes += 1
        i += 1
    
    old_depth = depth
    depth += opens - closes
    # Print lines around nesting depth changes or errors
    if idx >= 1020 and idx <= 1060:
        print(f"Line {idx+1:4d} (depth {old_depth} -> {depth}): {line}")
    elif idx >= 2330 and idx <= 2360:
        print(f"Line {idx+1:4d} (depth {old_depth} -> {depth}): {line}")
