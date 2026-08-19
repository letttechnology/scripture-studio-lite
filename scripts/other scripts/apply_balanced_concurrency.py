import sys
import re
sys.stdout.reconfigure(encoding='utf-8')

# 1. Recover App.kt from trace
trace_path = r"C:\Users\blue1\.gemini\antigravity-ide\brain\26225130-f206-43ae-a1b2-908d3a977cd1\scratch\depth_trace.txt"
with open(trace_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

recovered_lines = []
for line in lines:
    if "): " in line:
        parts = line.split("): ", 1)
        recovered_lines.append(parts[1])
    else:
        recovered_lines.append(line)

code = "".join(recovered_lines)

# Normalize line endings
code = code.replace("\r\n", "\n")

# 2. Add imports at the top
code = code.replace(
    "import androidx.compose.foundation.rememberScrollState",
    "import androidx.compose.foundation.rememberScrollState\nimport androidx.compose.foundation.horizontalScroll",
    1
)

# 3. Add TranscriptionJob class at the bottom (before formatDuration)
job_class = """
class TranscriptionJob(
    val id: String,
    val filename: String,
    val audioPath: String,
    val engine: String,
    text: String = "",
    isRunning: Boolean = true,
    isError: Boolean = false,
    statusMessage: String = "Transcribing..."
) {
    var text by androidx.compose.runtime.mutableStateOf(text)
    var isRunning by androidx.compose.runtime.mutableStateOf(isRunning)
    var isError by androidx.compose.runtime.mutableStateOf(isError)
    var statusMessage by androidx.compose.runtime.mutableStateOf(statusMessage)
}
"""
code = code.replace("private fun formatDuration", job_class + "\nprivate fun formatDuration", 1)

# 4. Apply states at top of App
orig_states = """    var autosaveEnabled by remember { mutableStateOf(true) }
    var transcriptionText by remember { mutableStateOf("") }
    var showApiKeyWarning by remember { mutableStateOf(false) }
    var isTranscribing by remember { mutableStateOf(false) }
    var transcriptionStatus by remember { mutableStateOf("") }"""

new_states = """    var autosaveEnabled by remember { mutableStateOf(true) }
    val transcriptionJobs = remember { mutableStateListOf<TranscriptionJob>() }
    var selectedJobId by remember { mutableStateOf<String?>(null) }
    var showApiKeyWarning by remember { mutableStateOf(false) }
    var maxJobsLimit by remember { mutableStateOf(SettingsStorage.get("max_jobs_limit", "4").toIntOrNull() ?: 4) }
    var jobToConfirmClose by remember { mutableStateOf<TranscriptionJob?>(null) }"""

code = code.replace(orig_states, new_states, 1)

# 5. Apply Header size updates
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

code = code.replace(orig_header, new_header, 1)

# 6. Apply Transcribe Button replacement with robust nesting tracing
new_button = """// Transcribe Button
                                Button(
                                    onClick = {
                                        if (transcriptionJobs.size >= maxJobsLimit) {
                                            statusMessage = "Maximum number of transcription tabs ($maxJobsLimit) reached. Please close tabs first."
                                            statusIsError = true
                                            return@Button
                                        }
                                        
                                        if (!isPro && transcribeCount >= 3) {
                                            showPaywall = true
                                            return@Button
                                        }
                                        
                                        val isCloud = selectedEngine == "cloud"
                                        if (isCloud && apiKey.trim().isEmpty()) {
                                            showApiKeyWarning = true
                                            return@Button
                                        }
                                        
                                        val audioPathToTranscribe = activeAudioPath
                                        val filename = audioPathToTranscribe.substringAfterLast("/").substringAfterLast("\\\\")
                                        val jobId = getFormattedDateTimeString() + "_" + filename
                                        
                                        val newJob = TranscriptionJob(
                                            id = jobId,
                                            filename = filename,
                                            audioPath = audioPathToTranscribe,
                                            engine = selectedEngine
                                        )
                                        
                                        transcriptionJobs.add(newJob)
                                        selectedJobId = jobId
                                        
                                        // Clear active audio states immediately
                                        activeAudioPath = ""
                                        SettingsStorage.put("active_audio_path", "")
                                        amplitudeHistory.clear()
                                        recordingDurationSec = 0
                                        
                                        transcribeCount++
                                        SettingsStorage.put("transcribe_count", transcribeCount.toString())
                                        
                                        coroutineScope.launch(kotlinx.coroutines.Dispatchers.Default) {
                                            try {
                                                val text = if (newJob.engine == "cloud") {
                                                     cloudWhisperService.transcribe(newJob.audioPath, apiKey)
                                                } else {
                                                     if (localWhisperService == null) {
                                                         throw Exception("Local Whisper is not available on this platform.")
                                                     }
                                                     localWhisperService.transcribe(newJob.audioPath, "")
                                                }
                                                newJob.text = text
                                                newJob.isRunning = false
                                                newJob.statusMessage = "Completed"
                                                
                                                // Auto-sync transcript text to cloud if enabled
                                                val path = newJob.audioPath
                                                if (path.isNotEmpty()) {
                                                    val tempTextFile = "${path.substringBeforeLast(".")}_transcript.txt"
                                                    saveTextToFile(text, tempTextFile)
                                                    if (cloudStorageService != null) {
                                                        if (googleToken.isNotEmpty() && googleTranscriptSyncEnabled) {
                                                            try {
                                                                cloudStorageService.uploadToGoogleDrive(tempTextFile, "text/plain", googleToken)
                                                            } catch (e: Exception) {
                                                            }
                                                        }
                                                        if (oneDriveToken.isNotEmpty() && oneDriveTranscriptSyncEnabled) {
                                                            try {
                                                                cloudStorageService.uploadToOneDrive(tempTextFile, oneDriveToken)
                                                            } catch (e: Exception) {
                                                            }
                                                        }
                                                    }
                                                }
                                            } catch (e: Exception) {
                                                e.printStackTrace()
                                                newJob.isError = true
                                                newJob.isRunning = false
                                                newJob.statusMessage = e.message ?: "An error occurred during transcription."
                                            }
                                        }
                                    },
                                    modifier = Modifier
                                        .weight(0.9f)
                                        .height(40.dp),
                                    shape = RoundedCornerShape(8.dp),
                                    colors = ButtonDefaults.buttonColors(
                                        backgroundColor = Color(0xFF06B6D4),
                                        disabledBackgroundColor = Color(0x1A06B6D4),
                                        contentColor = TextLight,
                                        disabledContentColor = TextMuted
                                    ),
                                    enabled = !isRecording && activeAudioPath.isNotEmpty()
                                ) {
                                    Text(
                                        text = "Transcribe",
                                        color = TextLight,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 12.sp
                                    )
                                }"""

# Find // Transcribe Button
btn_idx = code.find("// Transcribe Button")
if btn_idx != -1:
    start_pos = code.find("Button", btn_idx)
    p_depth = 0
    pos = code.find("(", start_pos)
    n = len(code)
    while pos < n:
        if code[pos] == '(':
            p_depth += 1
        elif code[pos] == ')':
            p_depth -= 1
            if p_depth == 0:
                break
        pos += 1
    
    brace_start = code.find("{", pos)
    b_depth = 1
    brace_pos = brace_start + 1
    while brace_pos < n and b_depth > 0:
        if code[brace_pos:brace_pos+2] == "/*":
            brace_pos += 2
            while brace_pos < n and code[brace_pos:brace_pos+2] != "*/":
                brace_pos += 1
            brace_pos += 2
            continue
        if code[brace_pos:brace_pos+2] == "//":
            while brace_pos < n and code[brace_pos] != "\n":
                brace_pos += 1
            continue
        if code[brace_pos] == '"':
            brace_pos += 1
            while brace_pos < n and code[brace_pos] != '"':
                if code[brace_pos] == '\\':
                    brace_pos += 2
                else:
                    brace_pos += 1
            brace_pos += 1
            continue
        if code[brace_pos] == '{':
            b_depth += 1
        elif code[brace_pos] == '}':
            b_depth -= 1
        if b_depth == 0:
            break
        brace_pos += 1
    
    code = code[:start_pos] + new_button + code[brace_pos+1:]
    print("Transcribe button replaced robustly!")

# 7. Replace Transcript Card
new_card = """// Transcript Text Pane Card
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .border(1.dp, BorderColor, RoundedCornerShape(16.dp)),
                        shape = RoundedCornerShape(16.dp),
                        backgroundColor = CardDark,
                        elevation = 8.dp
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            val clipboardManager = androidx.compose.ui.platform.LocalClipboardManager.current
                            
                            // If we have jobs, display the Tabs row!
                            if (transcriptionJobs.isNotEmpty()) {
                                // A scrollable row of tabs
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(bottom = 12.dp)
                                        .horizontalScroll(rememberScrollState()),
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    transcriptionJobs.forEach { job ->
                                        val isSelected = selectedJobId == job.id
                                        
                                        // Tab chip
                                        Row(
                                            modifier = Modifier
                                                .clip(RoundedCornerShape(8.dp))
                                                .background(if (isSelected) Color(0x338B5CF6) else Color(0xFF1E293B))
                                                .border(1.dp, if (isSelected) Color(0xFF8B5CF6) else BorderColor, RoundedCornerShape(8.dp))
                                                .clickable { selectedJobId = job.id }
                                                .padding(horizontal = 10.dp, vertical = 6.dp),
                                            verticalAlignment = Alignment.CenterVertically,
                                            horizontalArrangement = Arrangement.spacedBy(6.dp)
                                        ) {
                                            // Status Indicator dot/spinner
                                            if (job.isRunning) {
                                                CircularProgressIndicator(
                                                    modifier = Modifier.size(10.dp),
                                                    color = Color(0xFF06B6D4),
                                                    strokeWidth = 1.5.dp
                                                )
                                            } else {
                                                Box(
                                                    modifier = Modifier
                                                        .size(8.dp)
                                                        .clip(CircleShape)
                                                        .background(if (job.isError) Color(0xFFEF4444) else Color(0xFF10B981))
                                                )
                                            }
                                            
                                            // Filename
                                            val displayName = if (job.filename.length > 12) {
                                                job.filename.take(10) + "..."
                                            } else {
                                                job.filename
                                            }
                                            Text(
                                                text = displayName,
                                                color = if (isSelected) TextLight else TextMuted,
                                                fontSize = 11.sp,
                                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal
                                            )
                                            
                                            // Close button (X)
                                            Box(
                                                modifier = Modifier
                                                    .size(14.dp)
                                                    .clip(CircleShape)
                                                    .background(Color(0x22FFFFFF))
                                                    .clickable {
                                                        if (job.isRunning) {
                                                            jobToConfirmClose = job
                                                        } else {
                                                            val idx = transcriptionJobs.indexOf(job)
                                                            transcriptionJobs.remove(job)
                                                            if (selectedJobId == job.id) {
                                                                selectedJobId = if (transcriptionJobs.isNotEmpty()) {
                                                                    transcriptionJobs[maxOf(0, idx - 1)].id
                                                                } else {
                                                                    null
                                                                }
                                                            }
                                                        }
                                                    },
                                                contentAlignment = Alignment.Center
                                            ) {
                                                Text(
                                                    text = "×",
                                                    color = TextLight,
                                                    fontSize = 10.sp,
                                                    fontWeight = FontWeight.Bold,
                                                    modifier = Modifier.padding(bottom = 2.dp)
                                                )
                                            }
                                        }
                                    }
                                }
                                
                                Divider(color = BorderColor, thickness = 1.dp, modifier = Modifier.padding(bottom = 12.dp))
                            }
                            
                            // Currently active job details
                            val activeJob = transcriptionJobs.find { it.id == selectedJobId }
                            
                            // Title & Action Row
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = if (activeJob != null) activeJob.filename.uppercase() else "TRANSCRIPT",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = TextMuted,
                                    letterSpacing = 1.5.sp,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    modifier = Modifier.weight(1f).padding(end = 8.dp)
                                )
                                
                                if (activeJob != null) {
                                    val jobText = activeJob.text
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
                                                .clickable(enabled = jobText.isNotEmpty()) {
                                                    clipboardManager.setText(androidx.compose.ui.text.AnnotatedString(jobText))
                                                    statusMessage = "Copied transcript to clipboard."
                                                    statusIsError = false
                                                }
                                                .padding(horizontal = 8.dp, vertical = 4.dp)
                                        ) {
                                            Text(
                                                text = "COPY",
                                                color = if (jobText.isNotEmpty()) Color(0xFF06B6D4) else TextMuted,
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
                                                .clickable(enabled = jobText.isNotEmpty()) {
                                                    activeJob.text = ""
                                                }
                                                .padding(horizontal = 8.dp, vertical = 4.dp)
                                        ) {
                                            Text(
                                                text = "CLEAR",
                                                color = if (jobText.isNotEmpty()) Color(0xFFEF4444) else TextMuted,
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
                                                .clickable(enabled = jobText.isNotEmpty()) {
                                                    val tempTextFile = "${activeJob.filename.substringBeforeLast(".")}_transcript.txt"
                                                    val targetPath = "$recordingDirectory/$tempTextFile"
                                                    saveTextToFile(jobText, targetPath)
                                                    exportFileNatively(targetPath, "Save Transcript")
                                                }
                                                .padding(horizontal = 8.dp, vertical = 4.dp)
                                        ) {
                                            Text(
                                                text = "SAVE",
                                                color = if (jobText.isNotEmpty()) Color(0xFF8B5CF6) else TextMuted,
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
                                                    .clickable(enabled = jobText.isNotEmpty()) {
                                                        coroutineScope.launch {
                                                            try {
                                                                statusMessage = "Uploading transcript to Google Drive..."
                                                                statusIsError = false
                                                                val tempTextFile = "${activeJob.filename.substringBeforeLast(".")}_transcript.txt"
                                                                val targetPath = "$recordingDirectory/$tempTextFile"
                                                                saveTextToFile(jobText, targetPath)
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
                                                    color = if (jobText.isNotEmpty()) Color(0xFF0F9D58) else TextMuted,
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
                                                    .clickable(enabled = jobText.isNotEmpty()) {
                                                        coroutineScope.launch {
                                                            try {
                                                                statusMessage = "Uploading transcript to OneDrive..."
                                                                statusIsError = false
                                                                val tempTextFile = "${activeJob.filename.substringBeforeLast(".")}_transcript.txt"
                                                                val targetPath = "$recordingDirectory/$tempTextFile"
                                                                saveTextToFile(jobText, targetPath)
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
                                                    color = if (jobText.isNotEmpty()) Color(0xFF0078D4) else TextMuted,
                                                    fontSize = 9.sp,
                                                    fontWeight = FontWeight.Bold
                                                )
                                            }
                                        }
                                    }
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
                                if (activeJob == null) {
                                    Text(
                                        text = "Your transcription will appear here. You can then edit, copy, or export it directly to your cloud storage drives.",
                                        color = TextMuted,
                                        fontSize = 13.sp,
                                        modifier = Modifier.align(Alignment.Center),
                                        textAlign = TextAlign.Center
                                    )
                                } else {
                                    if (activeJob.isRunning) {
                                        Column(
                                            modifier = Modifier.align(Alignment.Center),
                                            horizontalAlignment = Alignment.CenterHorizontally,
                                            verticalArrangement = Arrangement.spacedBy(8.dp)
                                        ) {
                                            CircularProgressIndicator(color = Color(0xFF06B6D4), modifier = Modifier.size(24.dp))
                                            Text(
                                                text = activeJob.statusMessage,
                                                color = TextLight,
                                                fontSize = 12.sp,
                                                fontWeight = FontWeight.SemiBold
                                            )
                                        }
                                    } else if (activeJob.isError) {
                                        Column(
                                            modifier = Modifier.align(Alignment.Center),
                                            horizontalAlignment = Alignment.CenterHorizontally,
                                            verticalArrangement = Arrangement.spacedBy(8.dp)
                                        ) {
                                            Text(
                                                text = "⚠ Transcription Failed",
                                                color = Color(0xFFEF4444),
                                                fontSize = 14.sp,
                                                fontWeight = FontWeight.Bold
                                            )
                                            Text(
                                                text = activeJob.statusMessage,
                                                color = TextMuted,
                                                fontSize = 12.sp,
                                                textAlign = TextAlign.Center,
                                                modifier = Modifier.padding(horizontal = 16.dp)
                                            )
                                        }
                                    } else {
                                        BasicTextField(
                                            value = activeJob.text,
                                            onValueChange = { activeJob.text = it },
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
                            }
                        }
                    }"""

card_match = re.search(r'// Transcript Text Pane Card\s*Card\(', code)
if card_match:
    start_pos = card_match.start()
    depth = 0
    seen_first_brace = False
    pos = card_match.end()
    n = len(code)
    while pos < n:
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
            seen_first_brace = True
        elif code[pos] == '}':
            depth -= 1
        
        if seen_first_brace and depth == 0:
            break
        pos += 1
        
    code = code[:start_pos] + new_card + code[pos+1:]
    print("Transcript Card replaced!")
else:
    print("Transcript Card target NOT found!")

# 8. Add Max Transcription Tabs option inside Settings Dialog
settings_target = """                        // API Key
                        Text("OpenAI API Key (Cloud Mode)", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)"""

settings_addition = """                        // Max tabs limit settings
                        Spacer(modifier = Modifier.height(16.dp))
                        Text("Max Transcription Tabs Limit", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(6.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            listOf(2, 4, 6, 8).forEach { limit ->
                                val isSelected = maxJobsLimit == limit
                                Box(
                                    modifier = Modifier
                                        .weight(1f)
                                        .clip(RoundedCornerShape(6.dp))
                                        .background(if (isSelected) Color(0xFF8B5CF6) else Color(0xFF1E293B))
                                        .border(1.dp, if (isSelected) Color(0xFF8B5CF6) else BorderColor, RoundedCornerShape(6.dp))
                                        .clickable {
                                            maxJobsLimit = limit
                                            SettingsStorage.put("max_jobs_limit", limit.toString())
                                        }
                                        .padding(vertical = 8.dp),
                                    contentAlignment = Alignment.Center
                                ) {
                                    Text(
                                        text = limit.toString(),
                                        color = TextLight,
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(16.dp))

                        // API Key
                        Text("OpenAI API Key (Cloud Mode)", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)"""

if settings_target in code:
    code = code.replace(settings_target, settings_addition, 1)
    print("Max Tabs Limit added to Settings!")

# 9. Add Confirmation overlay for closing running transcription
overlay_target = """            // Cloud File Picker Dialog"""
overlay_addition = """            // Confirm Close Running Transcription Dialog
            AnimatedVisibility(
                visible = jobToConfirmClose != null,
                modifier = Modifier.fillMaxSize()
            ) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    val job = jobToConfirmClose
                    if (job != null) {
                        Card(
                            modifier = Modifier.widthIn(max = 400.dp).padding(16.dp).border(1.dp, BorderColor, RoundedCornerShape(12.dp)),
                            shape = RoundedCornerShape(12.dp),
                            backgroundColor = CardDark,
                            elevation = 24.dp
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text("Cancel Transcription?", color = TextLight, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                Spacer(modifier = Modifier.height(8.dp))
                                Text("The job for '${job.filename}' is still running. Closing this tab will cancel/discard the active transcription. Proceed?", color = TextMuted, fontSize = 12.sp)
                                Spacer(modifier = Modifier.height(16.dp))
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                                ) {
                                    Button(
                                        onClick = { jobToConfirmClose = null },
                                        modifier = Modifier.weight(1f).height(36.dp),
                                        colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFF334155))
                                    ) {
                                        Text("No", color = TextLight, fontSize = 12.sp)
                                    }
                                    Button(
                                        onClick = {
                                            // Close the job!
                                            val idx = transcriptionJobs.indexOf(job)
                                            transcriptionJobs.remove(job)
                                            if (selectedJobId == job.id) {
                                                selectedJobId = if (transcriptionJobs.isNotEmpty()) {
                                                    transcriptionJobs[maxOf(0, idx - 1)].id
                                                } else {
                                                    null
                                                }
                                            }
                                            jobToConfirmClose = null
                                        },
                                        modifier = Modifier.weight(1f).height(36.dp),
                                        colors = ButtonDefaults.buttonColors(backgroundColor = Color(0xFFEF4444))
                                    ) {
                                        Text("Yes, Discard", color = TextLight, fontSize = 12.sp)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Cloud File Picker Dialog"""

if overlay_target in code:
    code = code.replace(overlay_target, overlay_addition, 1)
    print("Confirm Close dialog overlay added!")

lines = code.split("\n")

# Verify stack trace
stack = []
for idx, line in enumerate(lines):
    line_num = idx + 1
    pos = 0
    n = len(line)
    while pos < n:
        if line[pos] == "{":
            stack.append(line_num)
        elif line[pos] == "}":
            if stack:
                stack.pop()
            else:
                print(f"Extra closing brace at line {line_num}: {line.strip()}")
        pos += 1

print(f"Validation final stack size: {len(stack)}")
if len(stack) == 0:
    with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
        f.write(code)
    print("SUCCESS: App.kt written successfully with balanced braces!")
else:
    print("ERROR: Braces are still unbalanced! File NOT written.")
