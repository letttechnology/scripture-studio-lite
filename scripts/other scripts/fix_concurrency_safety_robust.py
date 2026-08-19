import os

path = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# Let's locate the launch block
search_str = "coroutineScope.launch(kotlinx.coroutines.Dispatchers.Default) {"
idx = text.find(search_str)
if idx != -1:
    print("Found launch start at index:", idx)
    # Let's replace the block from idx onwards
    # We find the next matching closing brace for this launch block
    # We can do this by counting braces
    brace_count = 0
    end_idx = -1
    for char_idx in range(idx + len(search_str) - 1, len(text)):
        char = text[char_idx]
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = char_idx
                break
    
    if end_idx != -1:
        print("Found end brace at index:", end_idx)
        # Construct the new block
        new_block = """coroutineScope.launch(kotlinx.coroutines.Dispatchers.Default) {
                                            try {
                                                val text = if (isCloud) {
                                                    cloudWhisperService.transcribe(activeAudioPath, apiKey)
                                                } else {
                                                    if (localWhisperService == null) {
                                                        throw Exception("Local Whisper is not available on this platform.")
                                                    }
                                                    localWhisperService.transcribe(activeAudioPath, "")
                                                }
                                                
                                                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                                    transcriptionText = text
                                                    statusMessage = "Transcription completed."
                                                    statusIsError = false
                                                }

                                                // Auto-sync transcript text to cloud if enabled
                                                val path = activeAudioPath
                                                if (path.isNotEmpty()) {
                                                    val tempTextFile = "${path.substringBeforeLast(".")}_transcript.txt"
                                                    saveTextToFile(text, tempTextFile)
                                                    if (cloudStorageService != null) {
                                                        if (googleToken.isNotEmpty() && googleSyncEnabled) {
                                                            try {
                                                                cloudStorageService.uploadToGoogleDrive(tempTextFile, "text/plain", googleToken)
                                                                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                                                    statusMessage = "Transcription completed & synced to Google Drive."
                                                                }
                                                            } catch (e: Exception) {
                                                                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                                                    statusMessage = "Transcription completed. Google Drive Sync Failed: ${e.message}"
                                                                    statusIsError = true
                                                                }
                                                            }
                                                        }
                                                        if (oneDriveToken.isNotEmpty() && oneDriveSyncEnabled) {
                                                            try {
                                                                cloudStorageService.uploadToOneDrive(tempTextFile, oneDriveToken)
                                                                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                                                    statusMessage = "Transcription completed & synced to OneDrive."
                                                                }
                                                            } catch (e: Exception) {
                                                                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                                                    statusMessage = "Transcription completed. OneDrive Sync Failed: ${e.message}"
                                                                    statusIsError = true
                                                                }
                                                            }
                                                        }
                                                    }
                                                }

                                                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                                    amplitudeHistory.clear()
                                                    recordingDurationSec = 0
                                                    activeAudioPath = ""
                                                    SettingsStorage.put("active_audio_path", "")
                                                }
                                            } catch (e: Exception) {
                                                e.printStackTrace()
                                                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                                    statusMessage = e.message ?: "An error occurred during transcription."
                                                    statusIsError = true
                                                }
                                            } finally {
                                                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                                    isTranscribing = false
                                                }
                                            }
                                        }"""
        
        # Replace
        new_text = text[:idx] + new_block + text[end_idx+1:]
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_text)
        print("Successfully updated App.kt with robust replace!")
    else:
        print("End brace not found!")
else:
    print("Search string not found!")
