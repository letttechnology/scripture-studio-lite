import sys
sys.stdout.reconfigure(encoding='utf-8')

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# Let's count line occurrences of target lines
lines = code.split("\n")

# Let's locate the double closing braces around line 843-845
# We want to find:
#                     }
#                     }
# 
#                     Spacer(modifier = Modifier.height(16.dp))
target_idx = -1
for idx in range(len(lines) - 2):
    if lines[idx].strip() == "}" and lines[idx+1].strip() == "}" and "Spacer(modifier = Modifier.height(16.dp))" in lines[idx+3]:
        target_idx = idx + 1
        break

if target_idx != -1:
    print(f"Found double brace at line {target_idx + 1} and {target_idx + 2}!")
    # Remove one of them (the second one)
    test_lines = lines[:target_idx+1] + lines[target_idx+2:]
    
    # Trace stack
    stack = []
    for line_idx, line in enumerate(test_lines):
        line_num = line_idx + 1
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

    print(f"Final stack size after deletion: {len(stack)}")
    for item in stack:
        print(f"Unclosed brace at line {item}: {test_lines[item-1].strip()}")
else:
    print("Could not find the target double brace!")
