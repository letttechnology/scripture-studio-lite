with open(r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\depth_trace.txt", "r", encoding="utf-8") as f:
    text = f.read()

print("Length of text:", len(text))
for idx, line in enumerate(text.split("\n")):
    if "Transcript" in line or "transcript" in line:
        print(f"Line {idx+1}: {line}")
