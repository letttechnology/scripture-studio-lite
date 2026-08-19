with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    lines = f.readlines()

replacement = """                                if (transcriptionText.isNotEmpty()) {
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(8.dp),
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
                                                .padding(horizontal = 10.dp, vertical = 5.dp)
                                        ) {
                                            Text(
                                                text = "COPY",
                                                color = Color(0xFF06B6D4),
                                                fontSize = 10.sp,
                                                fontWeight = FontWeight.Bold,
                                                letterSpacing = 0.5.sp
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
                                                .padding(horizontal = 10.dp, vertical = 5.dp)
                                        ) {
                                            Text(
                                                text = "CLEAR",
                                                color = Color(0xFFEF4444),
                                                fontSize = 10.sp,
                                                fontWeight = FontWeight.Bold,
                                                letterSpacing = 0.5.sp
                                            )
                                        }
                                    }
                                }
"""

# Replace lines 861 to 891 (indices 860 to 890, 0-indexed)
lines[860:891] = [replacement]

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Replacement successful!")
