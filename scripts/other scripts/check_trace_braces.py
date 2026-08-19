import sys
sys.stdout.reconfigure(encoding='utf-8')

trace_path = r"C:\\Users\\blue1\\.gemini\\antigravity-ide\\brain\\26225130-f206-43ae-a1b2-908d3a977cd1\\scratch\\depth_trace.txt"
with open(trace_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

recovered_lines = []
for line in lines:
    if "): " in line:
        parts = line.split("): ", 1)
        recovered_lines.append(parts[1])
    else:
        recovered_lines.append(line)

stack = []
for idx, line in enumerate(recovered_lines):
    line_num = idx + 1
    pos = 0
    n = len(line)
    while pos < n:
        if line[pos] == "{":
            stack.append((line_num, line.strip()))
        elif line[pos] == "}":
            if stack:
                stack.pop()
            else:
                print(f"Extra closing brace at line {line_num}: {line.strip()}")
        pos += 1

print(f"Final stack size: {len(stack)}")
for item in stack:
    print(f"Unclosed brace at line {item[0]}: {item[1]}")
