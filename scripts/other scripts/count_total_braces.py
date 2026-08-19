with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

idx = 0
n = len(code)
opens = 0
closes = 0
in_string = False
in_comment = False
in_block_comment = False

while idx < n:
    if code[idx:idx+2] == "/*":
        idx += 2
        while idx < n and code[idx:idx+2] != "*/":
            idx += 1
        idx += 2
        continue
    if code[idx:idx+2] == "//":
        while idx < n and code[idx] != "\n":
            idx += 1
        continue
    if code[idx:idx+3] == '"""':
        idx += 3
        while idx < n and code[idx:idx+3] != '"""':
            if code[idx:idx+2] == "${":
                opens += 1
                idx += 2
            elif code[idx] == "}":
                closes += 1
                idx += 1
            else:
                idx += 1
        idx += 3
        continue
    if code[idx] == '"':
        idx += 1
        while idx < n and code[idx] != '"':
            if code[idx] == '\\':
                idx += 2
            elif code[idx:idx+2] == "${":
                opens += 1
                idx += 2
            elif code[idx] == "}":
                closes += 1
                idx += 1
            else:
                idx += 1
        idx += 1
        continue
    if code[idx] == "'":
        idx += 1
        if code[idx] == '\\':
            idx += 2
        else:
            idx += 1
        idx += 1
        continue

    if code[idx] == '[':
        opens += 1
    elif code[idx] == ']':
        closes += 1
    idx += 1

print(f"Total opens: {opens}")
print(f"Total closes: {closes}")
print(f"Difference (opens - closes): {opens - closes}")
