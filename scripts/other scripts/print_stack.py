with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

lines = code.split("\n")
stack = []
in_string = False
in_comment = False
in_block_comment = False

for idx, line in enumerate(lines):
    line_num = idx + 1
    if line_num == 2345:
        break
    i = 0
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
                stack.append((line_num, line.strip()))
            elif line[i] == '}':
                if stack:
                    stack.pop()
                else:
                    print(f"Extra closing brace at line {line_num}: {line.strip()}")
        i += 1
    in_comment = False

print(f"Stack size at line 2344: {len(stack)}")
for line_num, text in stack:
    print(f"Line {line_num:4d}: {text}")
