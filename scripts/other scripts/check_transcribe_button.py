path = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# Let's search for transcription action button
idx = text.find('transcriptionStatus = "Transcribing audio file..."')
if idx != -1:
    print("Found transcriptionStatus at index:", idx)
    # Print lines around it
    lines = text[:idx].split("\n")
    print("\n".join(lines[-15:]))
else:
    print("transcriptionStatus not found!")
