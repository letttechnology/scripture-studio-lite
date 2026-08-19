import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Settings
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.myapplication.common.audio.AudioRecorder
import com.myapplication.common.storage.CloudStorageService
import com.myapplication.common.storage.exportFileNatively
import com.myapplication.common.transcribe.WhisperService
import com.myapplication.common.util.SettingsStorage
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

// High-fidelity Cyber Dark Palette
val BgDark = Color(0xFF0F172A)      // Slate 900
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
    cloudStorageService: CloudStorageService? = null
) {
    val coroutineScope = rememberCoroutineScope()
    
    // UI state
    var isRecording by remember { mutableStateOf(false) }
    var recordingDurationSec by remember { mutableStateOf(0) }
    var currentAmplitude by remember { mutableStateOf(0f) }
    val amplitudeHistory = remember { mutableStateListOf<Float>() }
    
    var localAudioPath by remember { mutableStateOf("") }
    var transcriptionText by remember { mutableStateOf("") }
    var isTranscribing by remember { mutableStateOf(false) }
    var transcriptionStatus by remember { mutableStateOf("") }
    
    // Persistent settings
    var selectedEngine by remember { mutableStateOf(SettingsStorage.get("selected_engine", "cloud")) }
    var apiKey by remember { mutableStateOf(SettingsStorage.get("api_key", "")) }
    var localExecPath by remember { mutableStateOf(SettingsStorage.get("local_exec_path", "")) }
    var localModelPath by remember { mutableStateOf(SettingsStorage.get("local_model_path", "")) }
    
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

    // Standard audio path helper depending on platform
    LaunchedEffect(Unit) {
        // Initialize default paths
        localAudioPath = SettingsStorage.get("audio_file_path", "")
        if (localAudioPath.isEmpty()) {
            // Default directory inside user home or cache
            val home = getPlatformDefaultDirectory()
            localAudioPath = "$home/recording_whisper.wav"
            SettingsStorage.put("audio_file_path", localAudioPath)
        }
    }

    MaterialTheme {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(BgDark)
                .padding(16.dp)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState()),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                // Header Pane
                Row(
                    modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
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
                        Text(
                            text = statusMessage,
                            color = TextLight,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.SemiBold
                        )
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

                            Spacer(modifier = Modifier.height(32.dp))

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
                                            statusMessage = "Audio saved to: $localAudioPath"
                                            statusIsError = false
                                        } else {
                                            statusMessage = ""
                                            audioRecorder.startRecording(localAudioPath)
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

                            Spacer(modifier = Modifier.height(16.dp))

                            // Actions
                            Button(
                                onClick = {
                                    if (isTranscribing) return@Button
                                    
                                    val isCloud = selectedEngine == "cloud"
                                    if (isCloud && apiKey.trim().isEmpty()) {
                                        statusMessage = "Please enter an OpenAI API key in settings."
                                        statusIsError = true
                                        return@Button
                                    }
                                    
                                    isTranscribing = true
                                    transcriptionStatus = "Transcribing audio file..."
                                    statusMessage = ""
                                    
                                    coroutineScope.launch(kotlinx.coroutines.Dispatchers.Default) {
                                        try {
                                            val text = if (isCloud) {
                                                cloudWhisperService.transcribe(localAudioPath, apiKey)
                                            } else {
                                                if (localWhisperService == null) {
                                                    throw Exception("Local Whisper is not available on this platform.")
                                                }
                                                localWhisperService.transcribe(localAudioPath, "")
                                            }
                                            transcriptionText = text
                                            statusMessage = "Transcription completed."
                                            statusIsError = false
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
                                    CircularProgressIndicator(size = 20.dp, color = TextLight)
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
                                            val tempTextFile = "${localAudioPath.substringBeforeLast(".")}_transcript.txt"
                                            saveTextToFile(transcriptionText, tempTextFile)
                                            exportFileNatively(tempTextFile, "Save Transcript")
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
                                                        val tempTextFile = "${localAudioPath.substringBeforeLast(".")}_transcript.txt"
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
                                                        val tempTextFile = "${localAudioPath.substringBeforeLast(".")}_transcript.txt"
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
                        Text("Audio Recording File Location", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(6.dp))
                        OutlinedTextField(
                            value = localAudioPath,
                            onValueChange = {
                                localAudioPath = it
                                SettingsStorage.put("audio_file_path", it)
                            },
                            modifier = Modifier.fillMaxWidth(),
                            textStyle = TextStyle(color = TextLight, fontSize = 13.sp),
                            colors = TextFieldDefaults.outlinedTextFieldColors(
                                focusedBorderColor = Color(0xFF8B5CF6),
                                unfocusedBorderColor = BorderColor
                            )
                        )

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
