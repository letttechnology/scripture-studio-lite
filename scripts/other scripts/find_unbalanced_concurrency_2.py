import sys
# Set standard output encoding to utf-8 to prevent charmap errors
sys.stdout.reconfigure(encoding='utf-8')

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

lines = code.split("\n")

stack = []
for idx, line in enumerate(lines):
    line_num = idx + 1
    pos = 0
    n = len(line)
    while pos < n:
        if line[pos] == "{":
            stack.append(line_num)
        elif line[pos] == "}":
            if stack:
                stack.pop()
            else:
                print(f"Extra closing brace at line {line_num}: {line.strip()}")
        pos += 1

print(f"Final stack size: {len(stack)}")
for item in stack:
    print(f"Unclosed brace at line {item}: {lines[item-1].strip()}")
