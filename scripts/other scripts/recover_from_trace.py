trace_path = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\depth_trace.txt"
dest_path = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"

print(f"Reading from: {trace_path}")

with open(trace_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

recovered_lines = []
for line in lines:
    if "): " in line:
        parts = line.split("): ", 1)
        recovered_lines.append(parts[1])
    else:
        # If no split, keep it as is (should be empty line or header)
        recovered_lines.append(line)

with open(dest_path, "w", encoding="utf-8") as f:
    f.writelines(recovered_lines)

print(f"Successfully recovered App.kt to {dest_path}!")
