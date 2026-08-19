import re

trace_path = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\depth_trace.txt"
with open(trace_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

recovered_lines = []
for line in lines:
    if "): " in line:
        parts = line.split("): ", 1)
        recovered_lines.append(parts[1])
    else:
        recovered_lines.append(line)

code = "".join(recovered_lines)
code = code.replace("\r\n", "\n")

m = re.search(r'// Transcript Text Pane Card\s*Card\(', code)
print("Regex match is:", m)
if m:
    print("Matched text:", code[m.start():m.end()+20])
