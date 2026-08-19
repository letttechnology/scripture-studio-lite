The following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.
                                            googleTranscriptSyncEnabled = false
                                            SettingsStorage.put("google_audio_sync_enabled", "false")
                                            SettingsStorage.put("google_transcript_sync_enabled", "false")
                                            statusMessage = "Disconnected Google Drive."
                                            statusIsError = false
                                        } else {
                                            if (!OAuthConfig.isGoogleConfigured()) {
                                                showLoginDialog = "google"
                                            } else {
                                                statusMessage = "Launching Google sign-in in your default browser..."
                                                statusIsError = false
                                                startPlatformOAuth(
                                                    "google",
                                                    OAuthConfig.GOOGLE_CLIENT_ID,
                                                    OAuthConfig.GOOGLE_CLIENT_SECRET,
                                                    onSuccess = { token ->
                                                        googleToken = token
                                                        SettingsStorage.put("google_token", token)
                                                        statusMessage = "Google Drive connected successfully!"
                                                        statusIsError = false
                                                    },
                                                    onError = { err ->
                                                        statusMessage = "Google connection failed: $err"
                                                        statusIsError = true
                                                    }
                                                )
                                            }
                                        }
                                    },
                                    colors = ButtonDefaults.buttonColors(
                                        backgroundColor = if (googleToken.isNotEmpty()) Color(0x33EF4444) else Color(0x3306B6D4)
                                    ),
                                    shape = RoundedCornerShape(6.dp)
                                ) {
                                    Text(
                                        text = if (googleToken.isNotEmpty()) "Disconnect" else "Connect",
                                        color = if (googleToken.isNotEmpty()) Color(0xFFEF4444) else Color(0xFF06B6D4),
                                        fontSize = 11.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.

The following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.
                }
            }

            // Mock Login / OAuth Authorization Dialog
            AnimatedVisibility(
                visible = showLoginDialog != null,
                modifier = Modifier.align(Alignment.Center)
            ) {
                val provider = showLoginDialog ?: ""
                var username by remember { mutableStateOf("") }
                var password by remember { mutableStateOf("") }
                var isConnecting by remember { mutableStateOf(false) }

                // Prepopulate mock data
                LaunchedEffect(provider) {
                    if (provider.isNotEmpty()) {
                        username = when (provider) {
                            "google" -> "alex.jones@gmail.com"
                            "onedrive" -> "alex.jones@outlook.com"
                            else -> "alex.jones@icloud.com"
                        }
                        password = "••••••••••••"
                    }
                }

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
                        val headerText = when (provider) {
                            "google" -> "Sign in with Google"
                            "onedrive" -> "Sign in with Microsoft"
                            else -> "Sign in with Apple ID"
                        }
                        val accentColor = when (provider) {
                            "google" -> Color(0xFF0F9D58)
                            "onedrive" -> Color(0xFF0078D4)
                            else -> Color(0xFF8B5CF6)
                        }

                        Text(
                            text = headerText,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            color = TextLight,
                            letterSpacing = 1.sp
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = "Aura Transcribe requests access to your files & folder storage to automatically sync audio recordings and transcripts.",
                            fontSize = 12.sp,
                            color = TextMuted,
                            textAlign = TextAlign.Center
                        )
                        Spacer(modifier = Modifier.height(16.dp))

                        Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                            Text("Email / Username", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            OutlinedTextField(
                                value = username,
                                onValueChange = { username = it },
                                modifier = Modifier.fillMaxWidth(),
                                textStyle = TextStyle(color = TextLight, fontSize = 13.sp),
                                colors = TextFieldDefaults.outlinedTextFieldColors(
                                    focusedBorderColor = accentColor,
                                    unfocusedBorderColor = BorderColor
                                ),
                                enabled = !isConnecting
                            )

                            Text("Password", color = TextMuted, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            OutlinedTextField(
                                value = password,
                                onValueChange = { password = it },
                                modifier = Modifier.fillMaxWidth(),
                                textStyle = TextStyle(color = TextLight, fontSize = 13.sp),
                                visualTransformation = PasswordVisualTransformation(),
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                                colors = TextFieldDefaults.outlinedTextFieldColors(
                                    focusedBorderColor = accentColor,
                                    unfocusedBorderColor = BorderColor
                                ),
                                enabled = !isConnecting
                            )
                        }

                        Spacer(modifier = Modifier.height(24.dp))

                        if (isConnecting) {
                            CircularProgressIndicator(color = accentColor, modifier = Modifier.size(24.dp))
                            Spacer(modifier = Modifier.height(8.dp))
                            Text("Connecting account and generating token...", color = TextMuted, fontSize = 11.sp)
                        } else {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(12.dp)
                            ) {
                                Button(
                                    onClick = {
                                        isConnecting = true
                                        coroutineScope.launch {
                                            delay(1000) // Simulate OAuth callback delay
                                            isConnecting = false
                                            val mockToken = "mock_token_${provider}_" + getFormattedDateTimeString()
                                            when (provider) {
                                                "google" -> {
                                                    googleToken = mockToken
                                                    SettingsStorage.put("google_token", mockToken)
                                                }
                                                "onedrive" -> {
                                                    oneDriveToken = mockToken
                                                    SettingsStorage.put("onedrive_token", mockToken)
                                                }
                                                "apple" -> {
                                                    appleToken = mockToken
                                                    SettingsStorage.put("apple_token", mockToken)
                                                }
                                            }
                                            showLoginDialog = null
                                            statusMessage = "Successfully connected your " + when (provider) {
                                                "google" -> "Google Drive"
                                                "onedrive" -> "OneDrive"
                                                else -> "iCloud"
                                            } + " account!"
                                            statusIsError = false
                                        }
                                    },
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.
