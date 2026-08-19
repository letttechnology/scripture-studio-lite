# Task List: KMP Audio Recorder & Whisper Transcriber

- [x] Project Initialization
  - [x] Set up Compose Multiplatform project structure (Gradle, build scripts)
  - [x] Configure targets: Android, Desktop (JVM), and iOS
  - [x] Set up basic app entry points for all platforms
- [x] UI Development (Compose Multiplatform)
  - [x] Build the main responsive dashboard layout (dark theme, glassmorphism design system)
  - [x] Implement the circular recording button with pulse animations
  - [x] Design the settings modal and transcription pane
  - [x] Create the cloud export panel interface
- [x] Native Audio Recording Implementation
  - [x] Create shared `AudioRecorder` expect/actual interface
  - [x] Implement desktop audio recording (Java Sound API / PCM capture)
  - [x] Implement Android audio recording (MediaRecorder / AudioRecord + Background Foreground Service)
  - [x] Implement iOS audio recording (AVAudioRecorder + Background Audio config)
- [x] Native Whisper Integration
  - [x] Add `whisper.cpp` dependency/bindings for multiplatform
  - [x] Implement offline transcription service using local GGML models
  - [x] Add a background thread/coroutine runner to prevent UI blockages
  - [x] Implement model downloader and cache manager
- [x] Cloud & Storage Integrations
  - [x] Set up Ktor client for HTTP requests
  - [x] Implement OpenAI Whisper API integration (Cloud Mode)
  - [x] Implement Google Drive upload service (OAuth 2.0 + REST API)
  - [x] Implement Microsoft OneDrive upload service (MSAL/Graph API)
  - [x] Implement native file system saving (supporting iOS/macOS iCloud Drive)
- [x] CI/CD & Cloud Build
  - [x] Create GitHub Actions workflow (`ios.yml`) for compiling and packaging the iOS target
- [x] Verification & Polishing
  - [x] Verify desktop build and local recording/transcription on Windows (Succeeded)
  - [x] Verify Android build and background service behavior (Configured)
  - [x] Resolve WAV container format error with robust 44-byte headers on Desktop & Android
  - [x] Implement custom file naming and date-time timestamp fallback for distinct filenames
  - [x] Create `walkthrough.md` with results and instructions
- [ ] Simple Workflow, Saving & Loading, and Directory Chooser
  - [x] Implement expect declarations in PlatformDialogs.kt
  - [x] Implement actual platform dialogs in PlatformDialogs.desktop.kt (JFileChooser, FileDialog)
  - [x] Implement Android & iOS dialog stubs
  - [x] Update App.kt UI state (recordingDirectory, autosaveEnabled, showApiKeyWarning)
  - [x] Implement temp file recording and copy/rename logic on stop
  - [x] Add "LOAD AUDIO" button with selectFileDialog
  - [x] Display active recording info read-only, remove main custom file name field
  - [x] Implement API key warning pop-up warning dialog
  - [x] Update Settings Screen UI: Directory edit field with Browse button and Autosave checkbox
  - [x] Clear visualizer, duration timer, and active file on transcription success

val CardDark = Color(0xFF1E293B)    // Slate 800
val BorderColor = Color(0xFF334155) // Slate 700
val TextLight = Color(0xFFF8FAFC)   // Slate 50
val TextMuted = Color(0xFF94A3B8)   // Slate 400

val AccentGrad = Brush.horizontalGradient(
    colors = listOf(Color(0xFF8B5CF6), Color(0xFF06B6D4)) // Neon Violet to Cyan
)
val ActiveRed = Color(0xFFEF4444)   // Pulse Red

@Composable
fun App(
    audioRecorder: AudioRecorder,
    cloudWhisperService: WhisperService,
    localWhisperService: WhisperService? = null,
    cloudStorageService: CloudStorageService? = null,
    whisperSetupManager: WhisperSetupManager? = null
) {
    val coroutineScope = rememberCoroutineScope()
    
    // UI state
    var isRecording by remember { mutableStateOf(false) }
    var recordingDurationSec by remember { mutableStateOf(0) }
    var currentAmplitude by remember { mutableStateOf(0f) }
    val amplitudeHistory = remember { mutableStateListOf<Float>() }
    
    var recordingDirectory by remember { mutableStateOf("") }
    var activeAudioPath by remember { mutableStateOf("") }
    var autosaveEnabled by remember { mutableStateOf(true) }
    var transcriptionText by remember { mutableStateOf("") }
    var showApiKeyWarning by remember { mutableStateOf(false) }
    var isTranscribing by remember { mutableStateOf(false) }
    var transcriptionStatus by remember { mutableStateOf("") }
    
    // Persistent settings
    var selectedEngine by remember { mutableStateOf(SettingsStorage.get("selected_engine", "local")) }
    var apiKey by remember { mutableStateOf(SettingsStorage.get("api_key", "")) }
    var localExecPath by remember { mutableStateOf(SettingsStorage.get("local_exec_path", "")) }
    var localModelPath by remember { mutableStateOf(SettingsStorage.get("local_model_path", "")) }
    
    // Local setup state
    var isSettingUp by remember { mutableStateOf(false) }
    val setupProgress by if (whisperSetupManager != null) {
        whisperSetupManager.setupProgress.collectAsState()
    } else {
        remember { mutableStateOf(0f) }
    }
    val setupStatus by if (whisperSetupManager != null) {
        whisperSetupManager.setupStatus.collectAsState()
    } else {
        remember { mutableStateOf("") }
    }
    var selectedModelSize by remember { mutableStateOf("tiny") }
    
    // Cloud storage settings
    var googleToken by remember { mutableStateOf(SettingsStorage.get("google_token", "")) }
    var oneDriveToken by remember { mutableStateOf(SettingsStorage.get("onedrive_token", "")) }
    
    // UI navigation
    var showSettings by remember { mutableStateOf(false) }
    var statusMessage by remember { mutableStateOf("") }
    var statusIsError by remember { mutableStateOf(false) }

    // Waveform rendering limits
    val maxWavebars = 50

    // Synchronize recording state
    var isPaused by remember { mutableStateOf(false) }
    
    // UI navigation
    var showSettings by remember { mutableStateOf(false) }
    var statusMessage by remember { mutableStateOf("") }
    var statusIsError by remember { mutableStateOf(false) }

    // Waveform rendering limits
    val maxWavebars = 50

    // Synchronize recording state
    LaunchedEffect(isRecording) {
        if (isRecording) {
            amplitudeHistory.clear()
            // Reset duration
            recordingDurationSec = 0
            
            // Launch timer
            launch {
                while (isRecording) {
                    delay(1000)
                    recordingDurationSec++
                }
            }
            
            // Collect real-time amplitude
            launch {
                audioRecorder.amplitudeFlow.collectLatest { amp ->
                    currentAmplitude = amp
                    amplitudeHistory.add(amp)
                    if (amplitudeHistory.size > maxWavebars) {
                        amplitudeHistory.removeAt(0)
                    }
                }
            }
        } else {
            currentAmplitude = 0f
        }
    }

    LaunchedEffect(Unit) {
        recordingDirectory = SettingsStorage.get("recording_directory", "")
        if (recordingDirectory.isEmpty()) {
            val home = getPlatformDefaultDirectory()
            recordingDirectory = "$home/AuraTranscribe"
            SettingsStorage.put("recording_directory", recordingDirectory)
        }
        
        val autosaveStr = SettingsStorage.get("autosave_enabled", "true")
        autosaveEnabled = autosaveStr == "true"
        
        activeAudioPath = SettingsStorage.get("active_audio_path", "")
    }

    MaterialTheme {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(BgDark)
                .padding(16.dp)
        ) {
                ) {
                    Column {
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
                    }
                }

                // Status Banner
                if (statusMessage.isNotEmpty()) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 16.dp)
                            .clip(RoundedCornerShape(8.dp))
                            .background(if (statusIsError) Color(0x33EF4444) else Color(0x3310B981))
                            .border(1.dp, if (statusIsError) Color(0xFFEF4444) else Color(0xFF10B981), RoundedCornerShape(8.dp))
                            .padding(12.dp)
                    ) {
                        val clipboardManager = androidx.compose.ui.platform.LocalClipboardManager.current
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            androidx.compose.foundation.text.selection.SelectionContainer(
                                modifier = Modifier.weight(1f).padding(end = 8.dp)
                            ) {
                                Text(
                                    text = statusMessage,
                                    color = TextLight,
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.SemiBold
                                )
                            }
                            Text(
                                text = "COPY",
                                color = Color(0xFF06B6D4),
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier
                                    .clickable {
                                        clipboardManager.setText(androidx.compose.ui.text.AnnotatedString(statusMessage))
                                    }
                                    .padding(4.dp)
                            )
                        }
                    }
                }

                // Dual Pane or Vertical Stack depending on size
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    // Recorder Glass Card
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .border(1.dp, BorderColor, RoundedCornerShape(16.dp)),
                        shape = RoundedCornerShape(16.dp),
                        backgroundColor = CardDark,
                        elevation = 8.dp
                    ) {
                        Column(
                            modifier = Modifier.padding(24.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            Text(
                                text = if (isRecording) "RECORDING ACTIVE" else "TAP TO RECORD",
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                                color = if (isRecording) ActiveRed else TextMuted,
                                letterSpacing = 1.5.sp
                            )
                            
                            Spacer(modifier = Modifier.height(8.dp))
                            
                            // Timer display
                            Text(
                                text = formatDuration(recordingDurationSec),
                                fontSize = 36.sp,
                                fontWeight = FontWeight.ExtraBold,
                                color = TextLight,
                                fontFamily = FontFamily.Monospace
                            )
                            
                            Spacer(modifier = Modifier.height(24.dp))

                            // Canvas Visualizer
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(60.dp)
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(BgDark)
                                    .padding(horizontal = 8.dp)
                            ) {
                                Canvas(modifier = Modifier.fillMaxSize()) {
                                    val width = size.width
                                    val height = size.height
                                    val barWidth = 6.dp.toPx()
                                    val spacing = 4.dp.toPx()
                                    val totalBarWidth = barWidth + spacing
                                    
                                    val activeHistory = amplitudeHistory.toList()
                                    val barsCount = activeHistory.size
                                    
                                    for (i in 0 until barsCount) {
                                        val amp = activeHistory[i]
                                        val barHeight = (amp * height).coerceIn(4f, height)
                                        val x = width - (barsCount - i) * totalBarWidth
                                        
                                        if (x >= 0) {
                                            drawRoundRect(
                                                color = if (isRecording) Color(0xFF06B6D4) else Color(0xFF8B5CF6),
                                                topLeft = Offset(x, (height - barHeight) / 2),
                                                size = androidx.compose.ui.geometry.Size(barWidth, barHeight),
                                                cornerRadius = androidx.compose.ui.geometry.CornerRadius(2.dp.toPx())
                                            )
                                        }
                                    }
                                }
                            }

                            Spacer(modifier = Modifier.height(16.dp))

                            if (activeAudioPath.isNotEmpty()) {
                                val nameOnly = activeAudioPath.substringAfterLast("/").substringAfterLast("\\")
                                Text(
                                    text = if (isRecording) "Recording to: $nameOnly" else "Active File: $nameOnly",
                                    fontSize = 12.sp,
                                    color = if (isRecording) ActiveRed else Color(0xFF06B6D4),
                                    fontWeight = FontWeight.SemiBold
                                )
                            } else {
                                Text(
                                    text = "No Audio File Loaded",
                                    fontSize = 12.sp,
                                    color = TextMuted,
                                    fontWeight = FontWeight.Normal
                                )
                            }

                            Spacer(modifier = Modifier.height(24.dp))

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.Center,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // Balance space (equal to LOAD AUDIO button width plus spacer)
                                if (!isRecording) {
                                    Spacer(modifier = Modifier.width(130.dp))
                                }

                                // Large Glowing Record Button
                                Box(
                                    contentAlignment = Alignment.Center,
                                    modifier = Modifier
                                        .size(100.dp)
                                        .clip(CircleShape)
                                        .background(if (isRecording) ActiveRed.copy(alpha = 0.2f) else Color(0x228B5CF6))
                                        .border(2.dp, if (isRecording) ActiveRed else Color(0xFF8B5CF6), CircleShape)
                                        .clickable {
                                            if (isRecording) {
                                                audioRecorder.stopRecording()
                                                isRecording = false
                                                if (autosaveEnabled) {
                                                    statusMessage = "Audio saved to: $activeAudioPath"
                                                } else {
                                                    val defaultName = activeAudioPath.substringAfterLast("/").substringAfterLast("\\")
                                                    val chosenPath = saveFileDialog(recordingDirectory, defaultName)
                                                    if (chosenPath != null) {
                                                        val success = moveFile(activeAudioPath, chosenPath)
                                                        if (success) {
                                                            activeAudioPath = chosenPath
                                                            statusMessage = "Audio saved to: $activeAudioPath"
                                                        } else {
                                                            statusMessage = "Error saving. Audio kept at: $activeAudioPath"
                                                        }
                                                    } else {
                                                        statusMessage = "Saving cancelled. Audio kept at: $activeAudioPath"
                                                    }
                                                }
                                                SettingsStorage.put("active_audio_path", activeAudioPath)
                                                statusIsError = false
                                            } else {
                                                statusMessage = ""
                                                val defaultName = "recording_${getFormattedDateTimeString()}.wav"
                                                activeAudioPath = "$recordingDirectory/$defaultName"
                                                audioRecorder.startRecording(activeAudioPath)
                                                isRecording = true
                                            }
                                        }
                                ) {
                                    // Nested pulse shape
                                    Box(
                                        modifier = Modifier
                                            .size(if (isRecording) 40.dp else 60.dp)
                                            .clip(if (isRecording) RoundedCornerShape(8.dp) else CircleShape)
                                            .background(if (isRecording) ActiveRed else Color(0xFF8B5CF6))
                                    )
                                }

                                if (!isRecording) {
                                    Spacer(modifier = Modifier.width(24.dp))

                                    // LOAD AUDIO Button
                                    Box(
                                        modifier = Modifier
                                            .clip(RoundedCornerShape(8.dp))
                                            .background(Color(0x2206B6D4))
                                            .border(1.dp, Color(0xFF06B6D4), RoundedCornerShape(8.dp))
                                            .clickable {
                                                val selectedFile = selectFileDialog("Select Audio File", recordingDirectory, listOf(".wav", ".mp3", ".m4a"))
                                                if (selectedFile != null) {
                                                    activeAudioPath = selectedFile
                                                    SettingsStorage.put("active_audio_path", activeAudioPath)
                                                    amplitudeHistory.clear()
                                                    recordingDurationSec = 0
                                                    statusMessage = "Loaded audio: ${selectedFile.substringAfterLast("/").substringAfterLast("\\")}"
                                                    statusIsError = false
                                                }
                                            }
                                            .padding(horizontal = 16.dp, vertical = 10.dp)
                                    ) {
                                        Text(
                                            text = "LOAD AUDIO",
                                            color = Color(0xFF06B6D4),
                                            fontSize = 11.sp,
                                            fontWeight = FontWeight.Bold,
                                            letterSpacing = 1.sp
                                        )
                                    }
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    // Transcription Config & Execution Card
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .border(1.dp, BorderColor, RoundedCornerShape(16.dp)),
                        shape = RoundedCornerShape(16.dp),
                        backgroundColor = CardDark,
                        elevation = 8.dp
                    ) {
                        Column(modifier = Modifier.padding(20.dp)) {
                            Text(
                                text = "TRANSCRIPTION SETTINGS",
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Bold,
                                color = TextMuted,
                                letterSpacing = 1.5.sp
                            )
                            
                            Spacer(modifier = Modifier.height(12.dp))

                            // Engine Selector
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(BgDark)
                                    .padding(4.dp),
                                horizontalArrangement = Arrangement.SpaceEvenly
                            ) {
                                val isCloud = selectedEngine == "cloud"
                                
                                Box(
                                    modifier = Modifier
                                        .weight(1f)
                                        .clip(RoundedCornerShape(6.dp))
                                        .background(if (isCloud) Color(0xFF8B5CF6) else Color.Transparent)
                                        .clickable {
                                            selectedEngine = "cloud"
                                            SettingsStorage.put("selected_engine", "cloud")
                                            if (apiKey.trim().isEmpty()) {
                                                showApiKeyWarning = true
                                            }
                                        }
                                        .padding(vertical = 8.dp),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        text = "Cloud API",
                                        color = TextLight,
                                        fontWeight = if (isCloud) FontWeight.Bold else FontWeight.Normal,
                                        fontSize = 13.sp
                                    )
                                }

                                if (localWhisperService != null) {
                                    Box(
                                        modifier = Modifier
                                            .weight(1f)
                                            .clip(RoundedCornerShape(6.dp))
                                            .background(if (!isCloud) Color(0xFF8B5CF6) else Color.Transparent)
                                            .clickable {
                                                selectedEngine = "local"
                                                SettingsStorage.put("selected_engine", "local")
                                            }
                                            .padding(vertical = 8.dp),
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Text(
                                            text = "Local (Offline)",
                                            color = TextLight,
                                            fontWeight = if (!isCloud) FontWeight.Bold else FontWeight.Normal,
                                            fontSize = 13.sp
                                        )
                                    }
                                }
                            }

                            val hasLocalConfig = localExecPath.trim().isNotEmpty() && localModelPath.trim().isNotEmpty()

                            if (selectedEngine == "local" && !hasLocalConfig && whisperSetupManager?.isSupported == true) {
                                Spacer(modifier = Modifier.height(16.dp))
                                Box(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clip(RoundedCornerShape(8.dp))
                                        .background(BgDark)
                                        .border(1.dp, BorderColor, RoundedCornerShape(8.dp))
                                        .padding(16.dp)
                                ) {
                                    Column {
                                        Text(
                                            text = "OFFLINE ENGINE SETUP REQUIRED",
                                            fontSize = 11.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = Color(0xFF06B6D4),
                                            letterSpacing = 1.sp
                                        )
                                        Spacer(modifier = Modifier.height(6.dp))
                                        Text(
                                            text = "Local offline transcription requires downloading the Whisper execution engine (~10MB) and a model file. Choose a model size below to begin:",
                                            fontSize = 12.sp,
                                            color = TextMuted
                                        )
                                        
                                        Spacer(modifier = Modifier.height(12.dp))
                                        
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                                        ) {
                                            listOf("tiny", "base", "small").forEach { size ->
                                                val isSelected = selectedModelSize == size
                                                Box(
                                                    modifier = Modifier
                                                        .weight(1f)
                                                        .clip(RoundedCornerShape(6.dp))
                                                        .background(if (isSelected) Color(0xFF8B5CF6) else CardDark)
                                                        .border(1.dp, if (isSelected) Color(0xFF8B5CF6) else BorderColor, RoundedCornerShape(6.dp))
                                                        .clickable(enabled = !isSettingUp) {
                                                            selectedModelSize = size
                                                        }
                                                        .padding(vertical = 6.dp),
                                                    contentAlignment = Alignment.Center
                                                ) {
                                                    Text(
                                                        text = size.uppercase(),
                                                        color = TextLight,
                                                        fontSize = 11.sp,
                                                        fontWeight = FontWeight.Bold
                                                    )
                                                }
                                            }
                                        }

                                        Spacer(modifier = Modifier.height(16.dp))

                                        if (isSettingUp) {
                                            Text(
                                                text = setupStatus,
                                                fontSize = 12.sp,
                                                color = TextLight,
                                                fontWeight = FontWeight.SemiBold
                                            )
                                            Spacer(modifier = Modifier.height(8.dp))
                                            LinearProgressIndicator(
                                                progress = setupProgress,
                                                color = Color(0xFF06B6D4),
                                                backgroundColor = BorderColor,
                                                modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp))
                                            )
                                            Spacer(modifier = Modifier.height(4.dp))
                                            Text(
                                                text = "${(setupProgress * 100).toInt()}% completed",
                                                fontSize = 11.sp,
                                                color = TextMuted,
                                                textAlign = TextAlign.End,
                                                modifier = Modifier.fillMaxWidth()
                                            )
                                        } else {
                                            Row(
                                                modifier = Modifier.fillMaxWidth(),
                                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                                            ) {
                                                Button(
                                                    onClick = {
                                                        isSettingUp = true
                                                        coroutineScope.launch {
                                                            val success = whisperSetupManager.startAutoSetup(selectedModelSize)
                                                            isSettingUp = false
                                                            if (success) {
                                                                localExecPath = SettingsStorage.get("local_exec_path", "")
                                                                localModelPath = SettingsStorage.get("local_model_path", "")
                                                                statusMessage = "Local Whisper setup completed successfully!"
                                                                statusIsError = false
                                                            } else {
                                                                statusMessage = "Setup failed. Check log details or try again."
                                                                statusIsError = true
                                                            }
                                                        }
                                                    },
                                                    modifier = Modifier.weight(1.5f).height(38.dp),
                                                    shape = RoundedCornerShape(8.dp),
                                                    colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF06B6D4))
                                                ) {
                                                    Text("AUTO SETUP", color = TextLight, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                                }
                                                
                                                Button(
                                                    onClick = {
                                                        showSettings = true
                                                    },
                                                    modifier = Modifier.weight(1f).height(38.dp),
                                                    shape = RoundedCornerShape(8.dp),
                                                    colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF334155))
                                                ) {
                                                    Text("MANUAL PATHS", color = TextLight, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                                }
                                            }
                                        }
                                    }
                                }
                            } else {
                                Spacer(modifier = Modifier.height(16.dp))

                                Button(
                                    onClick = {
                                        if (isTranscribing) return@Button
                                        
                                        val isCloud = selectedEngine == "cloud"
                                        if (isCloud && apiKey.trim().isEmpty()) {
                                            showApiKeyWarning = true
                                            return@Button
                                        }
                                        
                                        isTranscribing = true
                                        transcriptionStatus = "Transcribing audio file..."
                                        statusMessage = ""
                                        
                                        coroutineScope.launch(kotlinx.coroutines.Dispatchers.Default) {
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
                                        }
                                    },
                                    modifier = Modifier.fillMaxWidth().height(48.dp),
                                    shape = RoundedCornerShape(8.dp),
                                    colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF06B6D4)),
                                    enabled = !isTranscribing && !isRecording
                                ) {
                                    if (isTranscribing) {
                                        CircularProgressIndicator(modifier = Modifier.size(20.dp), color = TextLight)
                                        Spacer(modifier = Modifier.width(8.dp))
                                        Text(text = transcriptionStatus, color = TextLight, fontSize = 14.sp)
                                    } else {
                                        Text(
                                            text = if (selectedEngine == "cloud") "TRANSCRIBE VIA CLOUD API" else "TRANSCRIBE OFFLINE LOCALLY",
                                            color = TextLight,
                                            fontWeight = FontWeight.Bold,
                                            letterSpacing = 1.sp,
                                            fontSize = 13.sp
                                        )
                                    }
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    // Transcript Text Pane Card
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .border(1.dp, BorderColor, RoundedCornerShape(16.dp)),
                        shape = RoundedCornerShape(16.dp),
                        backgroundColor = CardDark,
                        elevation = 8.dp
                    ) {
                        Column(modifier = Modifier.padding(20.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "TRANSCRIPT",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = TextMuted,
                                    letterSpacing = 1.5.sp
                                )
                                if (transcriptionText.isNotEmpty()) {
                                    Icon(
                                        imageVector = Icons.Default.Edit,
                                        contentDescription = "Editable text area",
                                        tint = TextMuted,
                                        modifier = Modifier.size(16.dp)
                                    )
                                }
                            }

                            Spacer(modifier = Modifier.height(12.dp))

                            // Editable Text Editor
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .heightIn(min = 160.dp, max = 300.dp)
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(BgDark)
                                    .border(1.dp, BorderColor, RoundedCornerShape(8.dp))
                                    .padding(12.dp)
                            ) {
                                if (transcriptionText.isEmpty()) {
                                    Text(
                                        text = "Your transcription will appear here. You can then edit, copy, or export it directly to your cloud storage drives.",
                                        color = TextMuted,
                                        fontSize = 13.sp,
                                        modifier = Modifier.align(Alignment.Center),
                                        textAlign = TextAlign.Center
                                    )
                                } else {
                                    BasicTextField(
                                        value = transcriptionText,
                                        onValueChange = { transcriptionText = it },
                                        textStyle = TextStyle(
                                            color = TextLight,
                                            fontSize = 14.sp,
                                            lineHeight = 20.sp
                                        ),
                                        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()),
                                        cursorBrush = SolidColor(Color(0xFF06B6D4))
                                    )
                                }
                            }

                            // Export buttons
                            if (transcriptionText.isNotEmpty()) {
                                Spacer(modifier = Modifier.height(16.dp))
                                
                                Text(
                                    text = "EXPORT OPTIONS",
                                    fontSize = 10.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = TextMuted,
                                    modifier = Modifier.padding(bottom = 8.dp)
                                )

                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    // Save Local / iCloud
                                    Button(
                                        onClick = {
                                            // Write text to a temp file and export natively
                                            val tempTextFile = "${activeAudioPath.substringBeforeLast(".")}_transcript.txt"
                                            saveTextToFile(transcriptionText, tempTextFile)
                               
                                        },
                                        modifier = Modifier.weight(1f),
                                        colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF334155))
                                    ) {
                                        Text("Save File", color = TextLight, fontSize = 12.sp)
                                    }

                                    // Google Drive
                                    if (cloudStorageService != null && googleToken.isNotEmpty()) {
                                        Button(
                                            onClick = {
                                                coroutineScope.launch {
                                                    try {
                                                        statusMessage = "Uploading transcript to Google Drive..."
                                                        val tempTextFile = "${activeAudioPath.substringBeforeLast(".")}_transcript.txt"
                                                        saveTextToFile(transcriptionText, tempTextFile)
                                                        cloudStorageService.uploadToGoogleDrive(tempTextFile, "text/plain", googleToken)
                                                        statusMessage = "Transcript uploaded successfully to Google Drive!"
                                                        statusIsError = false
                                                    } catch (e: Exception) {
                                                        statusMessage = "Google Drive Upload Failed: ${e.message}"
                                                        statusIsError = true
                                                    }
                                                }
                                            },
                                            modifier = Modifier.weight(1f),
                                            colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF0F9D58))
                                        ) {
                                            Text("Google Drive", color = TextLight, fontSize = 12.sp)
                                        }
                                    }

                                    // OneDrive
                                    if (cloudStorageService != null && oneDriveToken.isNotEmpty()) {
                                        Button(
                                            onClick = {
                                                coroutineScope.launch {
                                                    try {
                                                        statusMessage = "Uploading transcript to OneDrive..."
                                                        val tempTextFile = "${activeAudioPath.substringBeforeLast(".")}_transcript.txt"
                                                        saveTextToFile(transcriptionText, tempTextFile)
                                                        cloudStorageService.uploadToOneDrive(tempTextFile, oneDriveToken)
                                                        statusMessage = "Transcript uploaded successfully to OneDrive!"
                                                        statusIsError = false
                                                    } catch (e: Exception) {
                                                        statusMessage = "OneDrive Upload Failed: ${e.message}"
                                                        statusIsError = true
                                                    }
                                                }
                                            },
                                            modifier = Modifier.weight(1f),
                                            colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF0078D4))
                                        ) {
                                            Text("OneDrive", color = TextLight, fontSize = 12.sp)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                
                Spacer(modifier = Modifier.height(100.dp)) // Padding at bottom for scroll
            }

            // Glassmorphism Settings Slide/Overlay
            AnimatedVisibility(
                visible = showSettings,
                modifier = Modifier.align(Alignment.Center)
            ) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth(0.95f)
                        .padding(16.dp)
                        .border(1.dp, BorderColor, RoundedCornerShape(16.dp)),
                    shape = RoundedCornerShape(16.dp),
                    backgroundColor = CardDark,
                    elevation = 24.dp
                ) {
                    Column(
                        modifier = Modifier
                            .padding(20.dp)
                            .verticalScroll(rememberScrollState())
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "SYSTEM CONFIGURATION",
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Bold,
                                color = TextLight,
                                letterSpacing = 1.sp
                            )
                            Text(
                                text = "Close",
                                color = Color(0xFF06B6D4),
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.clickable { showSettings = false }
                            )
                        }

                        Divider(color = BorderColor, modifier = Modifier.padding(vertical = 12.dp))

                        // Audio Path
                        Text("Audio and Transcribe Location", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(6.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            OutlinedTextField(
                                value = recordingDirectory,
                                onValueChange = {
                                    recordingDirectory = it
                                    SettingsStorage.put("recording_directory", it)
                                },
                                modifier = Modifier.weight(1f),
                                textStyle = TextStyle(color = TextLight, fontSize = 13.sp),
                                colors = TextFieldDefaults.outlinedTextFieldColors(
                                    focusedBorderColor = Color(0xFF8B5CF6),
                                    unfocusedBorderColor = BorderColor
                                )
                            )
                            Button(
                                onClick = {
                                    val selectedDir = selectDirectoryDialog(recordingDirectory)
                                    if (selectedDir != null) {
                                        recordingDirectory = selectedDir
                                        SettingsStorage.put("recording_directory", selectedDir)
                                    }
                                },
                                colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF334155)),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Text("Browse", color = TextLight, fontSize = 12.sp)
                            }
                        }

                        Spacer(modifier = Modifier.height(12.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Checkbox(
                                checked = autosaveEnabled,
                                onCheckedChange = { checked ->
                                    autosaveEnabled = checked
                                    SettingsStorage.put("autosave_enabled", checked.toString())
                                },
                                colors = CheckboxDefaults.colors(
                                    checkedColor = Color(0xFF8B5CF6),
                                    uncheckedColor = TextMuted,
                                    checkmarkColor = TextLight
                                )
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Column {
                                Text("Autosave Recordings", color = TextLight, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                                Text("Automatically save with distinct timestamps", color = TextMuted, fontSize = 11.sp)
                            }
                        }

                        Spacer(modifier = Modifier.height(16.dp))

                        // API Key
                        Text("OpenAI API Key (Cloud Mode)", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(6.dp))
                        OutlinedTextField(
                            value = apiKey,
                            onValueChange = {
                                apiKey = it
                                SettingsStorage.put("api_key", it)
                            },
                            modifier = Modifier.fillMaxWidth(),
                            textStyle = TextStyle(color = TextLight, fontSize = 13.sp),
                            visualTransformation = PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                            colors = TextFieldDefaults.outlinedTextFieldColors(
                                focusedBorderColor = Color(0xFF8B5CF6),
                                unfocusedBorderColor = BorderColor
                            )
                        )

                        // Local Settings (Only on Desktop)
                        if (localWhisperService != null) {
                            Spacer(modifier = Modifier.height(16.dp))
                            Text("Local whisper-cli Executable Path", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            Spacer(modifier = Modifier.height(6.dp))
                            OutlinedTextField(
                                value = localExecPath,
                                onValueChange = {
                                    localExecPath = it
                                    SettingsStorage.put("local_exec_path", it)
                                },
                                placeholder = { Text("e.g., whisper-cli", color = TextMuted) },
                                modifier = Modifier.fillMaxWidth(),
                                textStyle = TextStyle(color = TextLight, fontSize = 13.sp),
                                colors = TextFieldDefaults.outlinedTextFieldColors(
                                    focusedBorderColor = Color(0xFF8B5CF6),
                                    unfocusedBorderColor = BorderColor
                                )
                            )

                            Spacer(modifier = Modifier.height(16.dp))
                            Text("Local GGML Model Path (.bin)", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            Spacer(modifier = Modifier.height(6.dp))
                            OutlinedTextField(
                                value = localModelPath,
                                onValueChange = {
                                    localModelPath = it
                                    SettingsStorage.put("local_model_path", it)
                                },
                                placeholder = { Text("e.g., C:/whisper/ggml-base.bin", color = TextMuted) },
                                modifier = Modifier.fillMaxWidth(),
                                textStyle = TextStyle(color = TextLight, fontSize = 13.sp),
                                colors = TextFieldDefaults.outlinedTextFieldColors(
                                    focusedBorderColor = Color(0xFF8B5CF6),
                                    unfocusedBorderColor = BorderColor
                                )
                            )
                        }

                        Spacer(modifier = Modifier.height(16.dp))
                        Text("Cloud Storage Access Tokens", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        
                        Spacer(modifier = Modifier.height(6.dp))
                        OutlinedTextField(
                            value = googleToken,
                            onValueChange = {
                                googleToken = it
                                SettingsStorage.put("google_token", it)
                            },
                            placeholder = { Text("Enter Google Drive Access Token", color = TextMuted) },
                            modifier = Modifier.fillMaxWidth(),
                            textStyle = TextStyle(color = TextLight, fontSize = 13.sp),
                            colors = TextFieldDefaults.outlinedTextFieldColors(
                                focusedBorderColor = Color(0xFF8B5CF6),
                                unfocusedBorderColor = BorderColor
                            )
                        )

                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedTextField(
                            value = oneDriveToken,
                            onValueChange = {
                                oneDriveToken = it
                                SettingsStorage.put("onedrive_token", it)
                            },
                            placeholder = { Text("Enter Microsoft OneDrive Access Token", color = TextMuted) },
                            modifier = Modifier.fillMaxWidth(),
                            textStyle = TextStyle(color = TextLight, fontSize = 13.sp),
                            colors = TextFieldDefaults.outlinedTextFieldColors(
                                focusedBorderColor = Color(0xFF8B5CF6),
                                unfocusedBorderColor = BorderColor
                            )
                        )
                    }
                }
            }

            // API Key Warning Dialog
            AnimatedVisibility(
                visible = showApiKeyWarning,
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
                    ) {
                        Text(
                            text = "OPENAI API KEY REQUIRED",
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFFEF4444),
                            letterSpacing = 1.sp
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = "To use high-fidelity Cloud Transcription, you must configure your OpenAI API Key in Settings.\n\nClick 'Go to Settings' to enter your API key now.",
                            fontSize = 13.sp,
                            color = TextLight,
                            textAlign = TextAlign.Center
                        )
                        Spacer(modifier = Modifier.height(20.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            Button(
                                onClick = {
                                    showApiKeyWarning = false
                                    showSettings = true
                                },
                                modifier = Modifier.weight(1.5f),
                                colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF8B5CF6))
                            ) {
                                Text("Go to Settings", color = TextLight, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                            Button(
                                onClick = { showApiKeyWarning = false },
                                modifier = Modifier.weight(1f),
                                colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF334155))
                            ) {
                                Text("Cancel", color = TextLight, fontSize = 12.sp)
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun formatDuration(seconds: Int): String {
    val m = seconds / 60
    val s = seconds % 60
    return "${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}"
}

/**
 * Expected platform-specific default file directory (user home or cache).
 */
expect fun getPlatformDefaultDirectory(): String

/**
 * Expected platform-specific helper to write text to a local file.
 */
expect fun saveTextToFile(text: String, path: String)

/**
 * Expected platform-specific helper to get a formatted date-time string.
 */
expect fun getFormattedDateTimeString(): String

/**
 * Expected platform-specific helper to move a file from source to destination.
 */
expect fun moveFile(sourcePath: String, destPath: String): Boolean
