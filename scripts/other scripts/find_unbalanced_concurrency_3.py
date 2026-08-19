import sys
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

    if 2600 <= line_num <= 2635:
        print(f"Line {line_num:4d} (stack size {len(stack):2d}): {line.strip()}")
