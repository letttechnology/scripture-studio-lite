with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

lines = code.split("\n")
stack = []
in_block_comment = False

for idx, line in enumerate(lines):
    line_num = idx + 1
    
    in_string = False
    in_comment = False
    
    i = 0
    while i < len(line):
        if in_block_comment:
            if i + 1 < len(line) and line[i:i+2] == "*/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
            
        if in_comment:
            break
            
        if in_string:
            if line[i] == '"':
                bs = 0
                k = i - 1
                while k >= 0 and line[k] == '\\':
                    bs += 1
                    k -= 1
                if bs % 2 == 0:
                    in_string = False
            i += 1
            continue
            
        if line[i:i+2] == "//":
            in_comment = True
            break
        elif line[i:i+2] == "/*":
            in_block_comment = True
            i += 2
            continue
        elif line[i] == '"':
            in_string = True
            i += 1
            continue
        elif line[i] == "'":
            i += 1
            if line[i] == '\\':
                i += 2
            else:
                i += 1
            i += 1
            continue
        elif line[i] == '{':
            stack.append((line_num, line.strip()))
        elif line[i] == '}':
            if stack:
                stack.pop()
            else:
                print(f"Extra closing brace at line {line_num}: {line.strip()}")
        i += 1

print(f"Stack size at end of file: {len(stack)}")
for line_num, text in stack:
    print(f"Line {line_num:4d}: {text}")
