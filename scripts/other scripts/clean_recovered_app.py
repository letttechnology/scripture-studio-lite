import re

src = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\recovered_old_app.txt"
dest = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\clean_app.kt"

with open(src, "r", encoding="utf-8") as f:
    lines = f.readlines()

clean_lines = []
for line in lines:
    # check if line starts with a number followed by colon and space
    m = re.match(r"^\s*\d+:\s?(.*)", line)
    if m:
        clean_lines.append(m.group(1) + "\n")
    else:
        # If it's a metadata header or something, skip it unless it's an empty line
        if line.strip() == "":
            clean_lines.append("\n")

# Write clean app
with open(dest, "w", encoding="utf-8") as f:
    f.writelines(clean_lines)

print("Clean App.kt generated in scratch!")
