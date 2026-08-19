with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

lines = code.split("\n")
idx = 0
n = len(code)
depth = 0
out_lines = []

# We'll do a simple character loop, but output line by line
line_num = 1
line_chars = []

# A helper to count braces in comments/strings correctly
in_string = False
in_comment = False
in_block_comment = False

for idx, line in enumerate(lines):
    line_num = idx + 1
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
    in_comment = False
    
    old_depth = depth
    depth += opens - closes
    out_lines.append(f"Line {line_num:4d} (depth {old_depth} -> {depth}): {line}")

with open(r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\depth_trace.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))

print("Trace written!")
