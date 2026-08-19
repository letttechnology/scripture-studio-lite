with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update Header size
orig_header = """                    Column {
                        Text(
                            text = "AURA TRANSCRIBE",
                            fontSize = 22.sp,
                            fontWeight = FontWeight.Bold,
                            color = TextLight,
                            fontFamily = FontFamily.Monospace,
                            letterSpacing = 2.sp
                        )
                        Text(
                            text = "Offline local and high-fidelity cloud transcription",
                            fontSize = 12.sp,
                            color = TextMuted
                        )
                    }
                    
                    IconButton(
                        onClick = { showSettings = !showSettings },
                        modifier = Modifier
                            .clip(CircleShape)
                            .background(CardDark)
                            .border(1.dp, BorderColor, CircleShape)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Settings,
                            contentDescription = "Open Settings",
                            tint = TextLight
                        )
                    }"""

new_header = """                    Column {
                        Text(
                            text = "AURA TRANSCRIBE",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            color = TextLight,
                            fontFamily = FontFamily.Monospace,
                            letterSpacing = 1.5.sp
                        )
                        Text(
                            text = "Offline local and high-fidelity cloud transcription",
                            fontSize = 10.sp,
                            color = TextMuted
                        )
                    }
                    
                    IconButton(
                        onClick = { showSettings = !showSettings },
                        modifier = Modifier
                            .size(32.dp)
                            .clip(CircleShape)
                            .background(CardDark)
                            .border(1.dp, BorderColor, CircleShape)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Settings,
                            contentDescription = "Open Settings",
                            tint = TextLight,
                            modifier = Modifier.size(16.dp)
                        )
                    }"""

if orig_header in code:
    code = code.replace(orig_header, new_header, 1)
    print("Header size modified successfully!")
else:
    print("Header size target NOT found!")

# 2. Update Transcribe button disabled colors
orig_transcribe_btn = """                                    colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF06B6D4)),"""
new_transcribe_btn = """                                    colors = ButtonDefaults.buttonColors(
                                        backgroundColor = Color(0xFF06B6D4),
                                        disabledBackgroundColor = Color(0x1A06B6D4),
                                        contentColor = TextLight,
                                        disabledContentColor = TextMuted
                                    ),"""

if orig_transcribe_btn in code:
    code = code.replace(orig_transcribe_btn, new_transcribe_btn, 1)
    print("Transcribe button colors modified successfully!")
else:
    print("Transcribe button colors target NOT found!")

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.write(code)

print("Updates complete!")
