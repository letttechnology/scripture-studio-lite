import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

lines = code.split("\n")

# Let's add the brace at line 842 (after the close brace at line 841)
# Line 841 is index 840 (0-indexed)
# Let's insert a closing brace there
lines.insert(841, "                    }")

# Let's add a closing brace at the end of App function
# The end of App function is before TranscriptionJob, which is index 2635
# Wait, let's find where TranscriptionJob starts in the modified lines
job_line = -1
for idx, line in enumerate(lines):
    if "class TranscriptionJob" in line:
        job_line = idx
        break

if job_line != -1:
    lines.insert(job_line, "}")

# Trace the stack on the test code
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

print(f"Test final stack size: {len(stack)}")
for item in stack:
    print(f"Unclosed brace at line {item}: {lines[item-1].strip()}")
