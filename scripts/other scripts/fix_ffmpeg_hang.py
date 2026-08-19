import os

path = r"d:\workspace-vscode-antigravity\shared\src\desktopMain\kotlin\com\myapplication\common\transcribe\LocalWhisperService.kt"
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

target_is_ffmpeg = """    private fun isFfmpegAvailable(): Boolean {
        return try {
            val process = ProcessBuilder("ffmpeg", "-version").start()
            process.waitFor() == 0
        } catch (e: Exception) {
            false
        }
    }"""

replacement_is_ffmpeg = """    private fun isFfmpegAvailable(): Boolean {
        return try {
            val pb = ProcessBuilder("ffmpeg", "-version")
            pb.redirectErrorStream(true)
            val process = pb.start()
            process.inputStream.bufferedReader().use { reader ->
                while (reader.readLine() != null) { /* discard */ }
            }
            process.waitFor() == 0
        } catch (e: Exception) {
            false
        }
    }"""

target_convert = """    private fun convertToWav(inputFile: File, outputFile: File): Boolean {
        return try {
            // ffmpeg -y -i <input> -ar 16000 -ac 1 -c:a pcm_s16le <output>
            val command = listOf(
                "ffmpeg",
                "-y",
                "-i", inputFile.absolutePath,
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                outputFile.absolutePath
            )
            val process = ProcessBuilder(command).start()
            process.waitFor() == 0
        } catch (e: Exception) {
            false
        }
    }"""

replacement_convert = """    private fun convertToWav(inputFile: File, outputFile: File): Boolean {
        return try {
            // ffmpeg -y -i <input> -ar 16000 -ac 1 -c:a pcm_s16le <output>
            val command = listOf(
                "ffmpeg",
                "-y",
                "-i", inputFile.absolutePath,
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                outputFile.absolutePath
            )
            val pb = ProcessBuilder(command)
            pb.redirectErrorStream(true)
            val process = pb.start()
            process.inputStream.bufferedReader().use { reader ->
                while (reader.readLine() != null) { /* discard */ }
            }
            process.waitFor() == 0
        } catch (e: Exception) {
            false
        }
    }"""

# Normalise newlines
text_norm = text.replace("\r\n", "\n")
target_is_ffmpeg_norm = target_is_ffmpeg.replace("\r\n", "\n")
replacement_is_ffmpeg_norm = replacement_is_ffmpeg.replace("\r\n", "\n")
target_convert_norm = target_convert.replace("\r\n", "\n")
replacement_convert_norm = replacement_convert.replace("\r\n", "\n")

if target_is_ffmpeg_norm in text_norm and target_convert_norm in text_norm:
    text_norm = text_norm.replace(target_is_ffmpeg_norm, replacement_is_ffmpeg_norm)
    text_norm = text_norm.replace(target_convert_norm, replacement_convert_norm)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text_norm)
    print("Successfully fixed stream blocking in LocalWhisperService.kt!")
else:
    print("Could not find targets in LocalWhisperService.kt!")
