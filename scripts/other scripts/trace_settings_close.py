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
            stack.append((line_num, line.strip()))
        elif line[pos] == "}":
            if stack:
                stack.pop()
        pos += 1

    if 830 <= line_num <= 846:
        print(f"Line {line_num:4d}: {line.strip()}")
        print(f"      Stack: {[item[0] for item in stack]}")
