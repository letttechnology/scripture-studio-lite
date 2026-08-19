import os

path = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

# Let's define the original transcription block target
target = """                                        coroutineScope.launch(kotlinx.coroutines.Dispatchers.Default) {
                                            try {
                                                val text = if (isCloud) {
                                                    cloudWhisperService.transcribe(activeAudioPath, apiKey)
                                                } else {
                                                    if (localWhisperService == null) {
                                                        throw Exception("Local Whisper is not available on this platform.")
                                                    }
                                                    localWhisperService.transcribe(activeAudioPath, "")
                                                }
                                                transcriptionText = text
                                                statusMessage = "Transcription completed."
                                                statusIsError = false

                                                // Auto-sync transcript text to cloud if enabled
                                                val path = activeAudioPath
                                                if (path.isNotEmpty()) {
                                                    val tempTextFile = "${path.substringBeforeLast(".")}_transcript.txt"
                                                    saveTextToFile(text, tempTextFile)
                                                    if (cloudStorageService != null) {
                                                        if (googleToken.isNotEmpty() && googleSyncEnabled) {
                                                            try {
                                                                cloudStorageService.uploadToGoogleDrive(tempTextFile, "text/plain", googleToken)
                                                                statusMessage = "Transcription completed & synced to Google Drive."
                                                            } catch (e: Exception) {
                                                                statusMessage = "Transcription completed. Google Drive Sync Failed: ${e.message}"
                                                                statusIsError = true
                                                            }
                                                        }
                                                        if (oneDriveToken.isNotEmpty() && oneDriveSyncEnabled) {
                                                            try {
                                                                cloudStorageService.uploadToOneDrive(tempTextFile, oneDriveToken)
                                                                statusMessage = "Transcription completed & synced to OneDrive."
                                                            } catch (e: Exception) {
                                                                statusMessage = "Transcription completed. OneDrive Sync Failed: ${e.message}"
                                                                statusIsError = true
                                                            }
                                                        }
                                                    }
                                                }

                                                amplitudeHistory.clear()
                                                recordingDurationSec = 0
                                                activeAudioPath = ""
                                                SettingsStorage.put("active_audio_path", "")
                                            } catch (e: Exception) {
                                                e.printStackTrace()
                                                statusMessage = e.message ?: "An error occurred during transcription."
                                                statusIsError = true
                                            } finally {
                                                isTranscribing = false
                                            }
                                        }"""

# And the thread-safe replacement
replacement = """        coroutineScope.launch(kotlinx.coroutines.Dispatchers.Default) {
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

# Normalise newline variations
text_norm = text.replace("\r\n", "\n")
target_norm = target.replace("\r\n", "\n")
replacement_norm = replacement.replace("\r\n", "\n")

if target_norm in text_norm:
    print("Found transcription block target!")
    text_norm = text_norm.replace(target_norm, replacement_norm)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text_norm)
    print("Successfully replaced with thread-safe coroutine updates!")
else:
    print("Target block not found!")
