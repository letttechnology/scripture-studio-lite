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
                popped_num, popped_name = stack.pop()
                # Print every pop that is an outer layout block or top-level element
                if popped_num in [68, 69, 184, 185, 186, 192, 193, 194, 199, 200, 512, 519, 520, 843, 844, 845, 846, 849, 850, 851, 852, 853, 854, 855, 856, 857, 1180, 1181, 1182, 1183]:
                    print(f"Brace opened at line {popped_num} ({popped_name}) closed at line {line_num}!")
            else:
                print(f"Extra closing brace at line {line_num}")
        pos += 1
