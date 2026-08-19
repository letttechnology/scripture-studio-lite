with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

idx = 0
n = len(code)
stack = [] # holds tuple of (line_num, col_num, char)

def get_line_col(pos):
    before = code[:pos]
    line = before.count("\n") + 1
    col = pos - before.rfind("\n")
    return line, col

matching = {
    '}': '{',
    ')': '(',
    ']': '['
}

while idx < n:
    # Block comment
    if code[idx:idx+2] == "/*":
        idx += 2
        while idx < n and code[idx:idx+2] != "*/":
            idx += 1
        idx += 2
        continue
    
    # Single line comment
    if code[idx:idx+2] == "//":
        while idx < n and code[idx] != "\n":
            idx += 1
        continue
        
    # Raw string literal
    if code[idx:idx+3] == '"""':
        idx += 3
        while idx < n and code[idx:idx+3] != '"""':
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
        
    # String literal
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
        
    # Character literal
    if code[idx] == "'":
        idx += 1
        if code[idx] == '\\':
            idx += 2
        else:
            idx += 1
        idx += 1
        continue

    # Braces, brackets, parentheses
    char = code[idx]
    if char in ('{', '(', '['):
        line, col = get_line_col(idx)
        stack.append((line, col, char))
    elif char in ('}', ')', ']'):
        line, col = get_line_col(idx)
        target = matching[char]
        if stack:
            # Pop until we match, or check if it matches the top
            top = stack[-1][2]
            if top == target or (char == '}' and top == '${'):
                stack.pop()
            else:
                print(f"Mismatch at line {line}, col {col}: found '{char}' but top of stack is '{top}' (opened at line {stack[-1][0]})")
                # Pop to keep going
                stack.pop()
        else:
            print(f"Extra closing '{char}' at line {line}, col {col}")
            
    idx += 1

print("\n--- Remaining Unclosed Elements ---")
for line, col, char in stack:
    line_text = code.split("\n")[line-1]
    print(f"Line {line:4d}, col {col:2d}: '{char}' in: {line_text.strip()}")
