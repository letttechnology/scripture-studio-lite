with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Replace snackbar header
orig_header = """            // Status Banner at bottom (Floating Snackbar style)
            AnimatedVisibility(
                visible = statusMessage.isNotEmpty(),
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 24.dp)
                    .fillMaxWidth(0.9f)
                    .widthIn(max = 500.dp)
            ) {
                Card("""

new_header = """            // Status Banner at bottom (Floating Snackbar style)
            AnimatedVisibility(
                visible = statusMessage.isNotEmpty(),
                modifier = Modifier.fillMaxSize()
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(bottom = 24.dp),
                    contentAlignment = Alignment.BottomCenter
                ) {
                    Card("""

if orig_header in code:
    code = code.replace(orig_header, new_header, 1)
    print("Snackbar header wrapped successfully!")
else:
    # try normalization of spaces
    print("Snackbar header target NOT found!")

# 2. Add Box close brace before AnimatedVisibility close brace
# The end of the file currently is:
#                     }
#                 }
#             }
#     }
# }
# And we want it to be:
#                     }
#                 }
#             }
#         }
#     }
# }

orig_end = """                    }
                }
            }
    }
}"""

new_end = """                    }
                }
            }
        }
    }
}"""

if code.endswith(orig_end) or orig_end in code:
    # replace the last occurrence of orig_end
    parts = code.rsplit(orig_end, 1)
    code = new_end.join(parts)
    print("Snackbar end wrapped successfully!")
else:
    print("Snackbar end target NOT found!")

with open(r"d:\workspace-vscode-antigravity\shared\src\commonMain\kotlin\App.kt", "w", encoding="utf-8") as f:
    f.write(code)

print("Snackbar Box wrap completed!")
