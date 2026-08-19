import os

path = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# Normalize
text = text.replace("\r\n", "\n")

# 1. Add TextOverflow import
if "import androidx.compose.ui.text.style.TextOverflow" not in text:
    text = text.replace(
        "import androidx.compose.ui.text.style.TextAlign",
        "import androidx.compose.ui.text.style.TextAlign\nimport androidx.compose.ui.text.style.TextOverflow",
        1
    )

# 2. Modify Save Source Selector Dialog
dialog_target = """            // Save Source Selector Dialog
            AnimatedVisibility(
                visible = showSaveSourceDialog,
                modifier = Modifier.align(Alignment.Center)
            ) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth(0.9f)
                        .padding(16.dp)
                        .border(1.dp, BorderColor, RoundedCornerShape(16.dp)),
                    shape = RoundedCornerShape(16.dp),
                    backgroundColor = CardDark,
                    elevation = 24.dp
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {"""

dialog_replacement = """            // Save Source Selector Dialog
            AnimatedVisibility(
                visible = showSaveSourceDialog,
                modifier = Modifier.align(Alignment.Center)
            ) {
                val activeText = transcriptionJobs.find { it.id == selectedJobId }?.text ?: ""
                Card(
                    modifier = Modifier
                        .fillMaxWidth(0.9f)
                        .padding(16.dp)
                        .border(1.dp, BorderColor, RoundedCornerShape(16.dp)),
                    shape = RoundedCornerShape(16.dp),
                    backgroundColor = CardDark,
                    elevation = 24.dp
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {"""

if dialog_target in text:
    text = text.replace(dialog_target, dialog_replacement, 1)
    print("Injected activeText definition!")

# Replace the 4 occurrences of transcriptionText within the dialog range
# Since the dialog is at the end of the file, we can find the dialog part and replace transcriptionText within it
dialog_idx = text.find("// Save Source Selector Dialog")
if dialog_idx != -1:
    dialog_part = text[dialog_idx:]
    dialog_part_fixed = dialog_part.replace("saveTextToFile(transcriptionText", "saveTextToFile(activeText")
    text = text[:dialog_idx] + dialog_part_fixed
    print("Replaced transcriptionText in save source dialog!")

with open(path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(text)

print("App.kt compilation fixes applied successfully!")
