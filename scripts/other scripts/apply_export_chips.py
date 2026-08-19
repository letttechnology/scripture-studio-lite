with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# 1. First, locate and delete the old bottom export buttons block.
# Let's inspect the block from:
# // Export buttons
# if (transcriptionText.isNotEmpty()) {
#     ...
# }
# and delete it.

# We will use brace tracing to cleanly delete it.
import re

pattern = re.compile(r'// Export buttons\s*if\s*\(transcriptionText\.isNotEmpty\(\)\)\s*\{')
match = pattern.search(code)
if match:
    start_pos = match.start()
    header_end = match.end()
    
    # Trace braces
    depth = 1
    pos = header_end
    n = len(code)
    while pos < n and depth > 0:
        if code[pos:pos+2] == "/*":
            pos += 2
            while pos < n and code[pos:pos+2] != "*/":
                pos += 1
            pos += 2
            continue
        if code[pos:pos+2] == "//":
            while pos < n and code[pos] != "\n":
                pos += 1
            continue
        if code[pos:pos+3] == '"""':
            pos += 3
            while pos < n and code[pos:pos+3] != '"""':
                pos += 1
            pos += 3
            continue
        if code[pos] == '"':
            pos += 1
            while pos < n and code[pos] != '"':
                if code[pos] == '\\':
                    pos += 2
                else:
                    pos += 1
            pos += 1
            continue
            
        if code[pos] == '{':
            depth += 1
        elif code[pos] == '}':
            depth -= 1
        
        if depth == 0:
            break
        pos += 1
        
    if depth == 0:
        # Delete this whole block
        code = code[:start_pos] + code[pos+1:]
        print("Deleted old bottom export buttons successfully!")
    else:
        print("Failed to find closing brace of bottom export buttons!")
else:
    print("Old bottom export buttons block NOT found!")

# 2. Add EXPORT, DRIVE, and ONEDRIVE chips to the transcript card header.
# Let's locate the Copy/Clear Row:
# if (transcriptionText.isNotEmpty()) {
#     Row(
#         horizontalArrangement = Arrangement.spacedBy(8.dp),
#         verticalAlignment = Alignment.CenterVertically
#     ) {
#         // Copy Chip
#         ...
#         // Clear Chip
#         ...
#     }
# }

chips_row_start = """                                if (transcriptionText.isNotEmpty()) {
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {"""

# We will replace this section with a new Row containing Copy, Clear, and the export chips!
replacement_chips = """                                if (transcriptionText.isNotEmpty()) {
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        // Copy Chip
                                        Box(
                                            modifier = Modifier
                                                .clip(RoundedCornerShape(6.dp))
                                                .background(Color(0x2206B6D4))
                                                .border(1.dp, Color(0xFF06B6D4), RoundedCornerShape(6.dp))
                                                .clickable {
                                                    clipboardManager.setText(androidx.compose.ui.text.AnnotatedString(transcriptionText))
                                                    statusMessage = "Copied transcript to clipboard."
                                                    statusIsError = false
                                                }
                                                .padding(horizontal = 8.dp, vertical = 4.dp)
                                        ) {
                                            Text(
                                                text = "COPY",
                                                color = Color(0xFF06B6D4),
                                                fontSize = 9.sp,
                                                fontWeight = FontWeight.Bold
                                            )
                                        }

                                        // Clear Chip
                                        Box(
                                            modifier = Modifier
                                                .clip(RoundedCornerShape(6.dp))
                                                .background(Color(0x22EF4444))
                                                .border(1.dp, Color(0xFFEF4444), RoundedCornerShape(6.dp))
                                                .clickable {
                                                    transcriptionText = ""
                                                }
                                                .padding(horizontal = 8.dp, vertical = 4.dp)
                                        ) {
                                            Text(
                                                text = "CLEAR",
                                                color = Color(0xFFEF4444),
                                                fontSize = 9.sp,
                                                fontWeight = FontWeight.Bold
                                            )
                                        }

                                        // Save (Local) Chip
                                        Box(
                                            modifier = Modifier
                                                .clip(RoundedCornerShape(6.dp))
                                                .background(Color(0x228B5CF6))
                                                .border(1.dp, Color(0xFF8B5CF6), RoundedCornerShape(6.dp))
                                                .clickable {
                                                    val tempTextFile = "transcript_${getFormattedDateTimeString()}.txt"
                                                    val targetPath = "$recordingDirectory/$tempTextFile"
                                                    saveTextToFile(transcriptionText, targetPath)
                                                    exportFileNatively(targetPath, "Save Transcript")
                                                }
                                                .padding(horizontal = 8.dp, vertical = 4.dp)
                                        ) {
                                            Text(
                                                text = "SAVE",
                                                color = Color(0xFF8B5CF6),
                                                fontSize = 9.sp,
                                                fontWeight = FontWeight.Bold
                                            )
                                        }

                                        // Google Drive Chip
                                        if (googleToken.isNotEmpty() && !googleTranscriptSyncEnabled) {
                                            Box(
                                                modifier = Modifier
                                                    .clip(RoundedCornerShape(6.dp))
                                                    .background(Color(0x220F9D58))
                                                    .border(1.dp, Color(0xFF0F9D58), RoundedCornerShape(6.dp))
                                                    .clickable {
                                                        coroutineScope.launch {
                                                            try {
                                                                statusMessage = "Uploading transcript to Google Drive..."
                                                                statusIsError = false
                                                                val tempTextFile = "transcript_${getFormattedDateTimeString()}.txt"
                                                                val targetPath = "$recordingDirectory/$tempTextFile"
                                                                saveTextToFile(transcriptionText, targetPath)
                                                                cloudStorageService?.uploadToGoogleDrive(targetPath, "text/plain", googleToken)
                                                                statusMessage = "Transcript uploaded successfully to Google Drive!"
                                                                statusIsError = false
                                                            } catch (e: Exception) {
                                                                statusMessage = "Google Drive Upload Failed: ${e.message}"
                                                                statusIsError = true
                                                            }
                                                        }
                                                    }
                                                    .padding(horizontal = 8.dp, vertical = 4.dp)
                                            ) {
                                                Text(
                                                    text = "DRIVE",
                                                    color = Color(0xFF0F9D58),
                                                    fontSize = 9.sp,
                                                    fontWeight = FontWeight.Bold
                                                )
                                            }
                                        }

                                        // OneDrive Chip
                                        if (oneDriveToken.isNotEmpty() && !oneDriveTranscriptSyncEnabled) {
                                            Box(
                                                modifier = Modifier
                                                    .clip(RoundedCornerShape(6.dp))
                                                    .background(Color(0x220078D4))
                                                    .border(1.dp, Color(0xFF0078D4), RoundedCornerShape(6.dp))
                                                    .clickable {
                                                        coroutineScope.launch {
                                                            try {
                                                                statusMessage = "Uploading transcript to OneDrive..."
                                                                statusIsError = false
                                                                val tempTextFile = "transcript_${getFormattedDateTimeString()}.txt"
                                                                val targetPath = "$recordingDirectory/$tempTextFile"
                                                                saveTextToFile(transcriptionText, targetPath)
                                                                cloudStorageService?.uploadToOneDrive(targetPath, oneDriveToken)
                                                                statusMessage = "Transcript uploaded successfully to OneDrive!"
                                                                statusIsError = false
                                                            } catch (e: Exception) {
                                                                statusMessage = "OneDrive Upload Failed: ${e.message}"
                                                                statusIsError = true
                                                            }
                                                        }
                                                    }
                                                    .padding(horizontal = 8.dp, vertical = 4.dp)
                                            ) {
                                                Text(
                                                    text = "ONEDRIVE",
                                                    color = Color(0xFF0078D4),
                                                    fontSize = 9.sp,
                                                    fontWeight = FontWeight.Bold
                                                )
                                            }
                                        }"""

# Locate the copy/clear block inside the Row and replace it
# We will do a robust replacement of the Row block
# Let's search for chips_row_start
if chips_row_start in code:
    # We want to replace the whole content lambda of this row with our replacement_chips.
    # To do this, let's trace the braces of the Row content lambda.
    idx_row = code.index(chips_row_start)
    header_end = idx_row + len(chips_row_start)
    
    depth = 1
    pos = header_end
    n = len(code)
    while pos < n and depth > 0:
        if code[pos:pos+2] == "/*":
            pos += 2
            while pos < n and code[pos:pos+2] != "*/":
                pos += 1
            pos += 2
            continue
        if code[pos:pos+2] == "//":
            while pos < n and code[pos] != "\n":
                pos += 1
            continue
        if code[pos] == '"':
            pos += 1
            while pos < n and code[pos] != '"':
                if code[pos] == '\\':
                    pos += 2
                else:
                    pos += 1
            pos += 1
            continue
        if code[pos] == '{':
            depth += 1
        elif code[pos] == '}':
            depth -= 1
        if depth == 0:
            break
        pos += 1
        
    if depth == 0:
        # replace from chips_row_start to pos (closing brace of Row content lambda, plus the closing brace of the outer if block which is next)
        # Wait, the closing brace of the Row content lambda is at pos.
        # And the next brace closes the if block. Let's find it.
        pos_if_close = pos + 1
        while pos_if_close < n and code[pos_if_close].isspace():
            pos_if_close += 1
        if pos_if_close < n and code[pos_if_close] == '}':
            # successfully found the if close brace!
            code = code[:idx_row] + replacement_chips + "\n                                    }\n                                }" + code[pos_if_close+1:]
            print("Successfully replaced chips row inside transcript card header!")
        else:
            print("Failed to locate closing brace of the outer if block!")
    else:
        print("Failed to locate closing brace of the Row content lambda!")
else:
    print("Copy/Clear Row start NOT found!")

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.write(code)

print("Export options refactored!")
