with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# We will iterate character by character through the entire code
# and keep track of state:
# - Normal
# - Single-line comment (starts with //, ends with \n)
# - Block comment (starts with /*, ends with */)
# - String literal (starts with ", ends with ", respects escape \. Wait, Kotlin strings can have template expressions like ${...} which open a new brace block!)
# - Raw string literal (starts with """, ends with """)

idx = 0
n = len(code)
stack = [] # holds tuple of (line_num, col_num, char)

def get_line_col(pos):
    # Returns 1-based line number and column number for a character index
    before = code[:pos]
    line = before.count("\n") + 1
    col = pos - before.rfind("\n")
    return line, col

while idx < n:
    # Check block comment
    if code[idx:idx+2] == "/*":
        idx += 2
        while idx < n and code[idx:idx+2] != "*/":
            idx += 1
        idx += 2
        continue
    
    # Check single line comment
    if code[idx:idx+2] == "//":
        while idx < n and code[idx] != "\n":
            idx += 1
        continue
        
    # Check raw string literal (triple quotes)
    if code[idx:idx+3] == '"""':
        idx += 3
        while idx < n and code[idx:idx+3] != '"""':
            # Inside raw string, we might have template expressions like ${expression}
            # which open a nesting level!
            # But let's check if there are template expressions. If not, just skip them.
            if code[idx:idx+2] == "${":
                line, col = get_line_col(idx)
                stack.append((line, col, "${"))
                idx += 2
            elif code[idx] == "}" and stack and stack[-1][2] == "${":
                stack.pop()
                idx += 1
            else:
                idx += 1
        idx += 3
        continue
        
    # Check regular string literal
    if code[idx] == '"':
        idx += 1
        while idx < n and code[idx] != '"':
            if code[idx] == '\\':
                idx += 2
            elif code[idx:idx+2] == "${":
                line, col = get_line_col(idx)
                stack.append((line, col, "${"))
                idx += 2
            elif code[idx] == "}" and stack and stack[-1][2] == "${":
                stack.pop()
                idx += 1
            else:
                idx += 1
        idx += 1
        continue
        
    # Character literals
    if code[idx] == "'":
        idx += 1
        if code[idx] == '\\':
            idx += 2
        else:
            idx += 1
        idx += 1
        continue

    # Braces tracking
    if code[idx] == '{':
        line, col = get_line_col(idx)
        stack.append((line, col, "{"))
    elif code[idx] == '}':
        line, col = get_line_col(idx)
        if stack:
            top = stack[-1][2]
            if top == "{" or top == "${":
                stack.pop()
            else:
                print(f"Brace mismatch at line {line}, col {col}: found '}}' but top of stack is '{top}'")
        else:
            print(f"Extra closing brace '}}' at line {line}, col {col}")
            
    idx += 1

print("\n--- Remaining Unclosed Braces ---")
for line, col, char in stack:
    # Print the line text
    line_text = code.split("\n")[line-1]
    print(f"Line {line:4d}, col {col:2d}: '{char}' in: {line_text.strip()}")
