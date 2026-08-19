with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Replace Box start with mainContent declaration
box_start = """        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(BgDark)
                .padding(16.dp),
            contentAlignment = Alignment.TopCenter
        ) {"""

replacement_start = """        val mainContent: @Composable BoxScope.() -> Unit = {"""

if box_start in code:
    code = code.replace(box_start, replacement_start, 1)
    print("Box start replaced successfully!")
else:
    print("Box start target NOT found!")

# 2. Restore settings dialog align test
test_align = "modifier = with(this@Box) { Modifier.align(Alignment.Center) }"
orig_align = "modifier = Modifier.align(Alignment.Center)"
if test_align in code:
    code = code.replace(test_align, orig_align, 1)
    print("Test align restored successfully!")

# 3. Replace end of file with Box call
# Let's find the last occurrences of the close braces and replace them
lines = code.split("\n")
# The last 3 lines are:
#         }
#     }
# }
# Let's verify and replace them
end_target = """        }
    }
}"""

replacement_end = """        }
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(BgDark)
                .padding(16.dp),
            contentAlignment = Alignment.TopCenter,
            content = mainContent
        )
    }
}"""

# Join the last few lines to check
end_chunk = "\n".join(lines[-4:])
print("Current file end chunk:\n" + end_chunk)

# Replace the end
if code.endswith(end_target):
    code = code[:-len(end_target)] + replacement_end
    print("End of file replaced successfully!")
else:
    # Try replacing as text
    if end_target in code:
        # We want to replace the last occurrence
        parts = code.rsplit(end_target, 1)
        code = replacement_end.join(parts)
        print("End of file replaced via rsplit!")
    else:
        print("End of file target NOT found!")

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.write(code)

print("Modification complete!")
