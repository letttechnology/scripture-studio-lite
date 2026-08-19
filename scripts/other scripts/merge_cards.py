import sys
sys.stdout.reconfigure(encoding='utf-8')

app_path = r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt"

with open(app_path, "r", encoding="utf-8") as f:
    code = f.read()

# Locate the Transcription Config & Execution Card
# We want to extract the inner content of its Column.
card_start_token = "// Transcription Config & Execution Card"
card_idx = code.find(card_start_token)
if card_idx == -1:
    print("Error: Could not find Transcription Config & Execution Card token")
    sys.exit(1)

# Find the start of Column modifier
col_idx = code.find("Column(modifier = Modifier.padding(10.dp))", card_idx)
if col_idx == -1:
    col_idx = code.find("Column(modifier = Modifier.padding(20.dp))", card_idx)
if col_idx == -1:
    print("Error: Could not find Column start in Settings card")
    sys.exit(1)

column_start_brace = code.find("{", col_idx)
# Find the matching closing brace of this Column
depth = 1
pos = column_start_brace + 1
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

column_end_brace = pos
column_inner_content = code[column_start_brace+1:column_end_brace].strip()

# Now find where the Settings card ends (the Card closing brace, which should be the next closing brace after column_end_brace)
card_end_brace = code.find("}", column_end_brace + 1)
print(f"Column inner content length: {len(column_inner_content)}")

# Now find the Recorder Card's column end
# The active filename display line is: "activeAudioPath.substringAfterLast(\"/\").substringAfterLast(\"\\\\\")" or similar
target_line = 'activeAudioPath.substringAfterLast("/").substringAfterLast("\\\\")'
# Wait, in the file it is substringAfterLast("/") or substringAfterLast("\\")
target_pos = code.find('activeAudioPath.substringAfterLast("/").substringAfterLast')
if target_pos == -1:
    print("Error: Could not find activeAudioPath substring line")
    sys.exit(1)

# Find the Row end of the active filename row
row_start = code.rfind("Row(", 0, target_pos)
# Find the matching closing brace of this Row
depth = 1
pos = code.find("{", row_start) + 1
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

row_end = pos

# We want to insert the Divider and the column inner content right after row_end
insertion_code = f"""
                            
                            Divider(
                                color = BorderColor,
                                thickness = 1.dp,
                                modifier = Modifier.padding(vertical = 10.dp)
                            )
                            
                            {column_inner_content}"""

# Now we construct the new code:
# From start of file to row_end
part1 = code[:row_end+1]
# From row_end to card_idx (which is the start of the spacer/settings card)
# Wait! Let's check what is between row_end and card_idx.
# It should be the end of the Recorder column and card, and the Spacer.
# Let's see: row_end is the end of the Row. The Recorder Card Column has one more closing brace, and Card has one more closing brace.
# Let's locate the Column closing brace of the Recorder card.
rec_col_end = code.find("}", row_end + 1)
rec_card_end = code.find("}", rec_col_end + 1)

# We want to insert the insertion_code inside the Recorder column, i.e., before rec_col_end!
part1_inserted = code[:rec_col_end] + insertion_code + code[rec_col_end:rec_card_end+1]

# Now we skip the Spacer and the Transcription Config Card!
# The Settings Card ends at card_end_brace.
# Let's verify what is after card_end_brace: it should be a Spacer, then the Transcript Card.
next_spacer_idx = code.find("Spacer(", card_end_brace)
part2 = code[next_spacer_idx:]

new_code = part1_inserted + "\n\n" + part2

with open(app_path, "w", encoding="utf-8") as f:
    f.write(new_code)

print("Card merge completed successfully!")
