# Repository Agent Rules & Tracking Standards

## Question Priority Protocol
- **ANSWER QUESTIONS FIRST**: When the user asks a question, you MUST answer the question directly and completely BEFORE doing anything else, taking actions, or writing/running code.

## Response Output Protocols
- **GitHub Issue Output**: ONLY print the GitHub Issue URL link (https://github.com/letttechnology/scripture-studio-lite/issues/<ID>) in the chat body. DO NOT output the issue body, Gherkin scenario, or summary text in the chat window.
- **No Code/Diff/File Dumping**: DO NOT print code blocks, diffs, or text file contents in the chat body. Only provide clickable file links with line ranges (e.g. `[App.tsx:L85-280](file:///d:/workspace/scripture-studio/src/App.tsx#L85-L280)`) pointing directly to the edited or created files.
- **Rolling Attempt History & Issue Comments**: When updating or resolving issues after multiple attempts, do NOT overwrite prior troubleshooting steps. Document all previous attempts, why they failed / what was ruled out, and append comments with the empirical verification.

## Workspace Common Tools Protocols
- **Use Pre-existing Tooling**: ALWAYS use existing scripts in `D:\workspace\common\` (such as `create_issue.py`, `fetch_issue.py`) or direct CLI commands (`gh`, `git`). DO NOT create new temporary scratch scripts each time to perform GitHub or Git operations.
- **Root Cause Problem Solving over Workarounds**: When a CLI command fails or hits authentication/formatting hurdles, resolve the underlying environment or command invocation root cause (e.g. `$env:GH_TOKEN` + stdin piping `@'...'@ | gh issue edit <ID> --body-file -`) instead of creating temporary workaround scripts.

## Autonomous Execution & Anti-Prompting Rules
- **NEVER CREATE PLAN MD FILES**: Do NOT create `implementation_plan.md` or any local plan markdown files under any circumstances.
- **NEVER REQUEST ARTIFACT FEEDBACK**: `RequestFeedback` must ALWAYS be `false` on all artifacts. Never pause execution for artifact reviews or approval buttons.
- **GITHUB ISSUES EXCLUSIVE**: ALL features, bugs, tasks, and plans MUST be filed directly to GitHub Issues via `python D:\workspace\common\create_issue.py` or `gh issue create`.
- **WORK ISSUES DIRECTLY**: Create the GitHub issue, work the code immediately in auto mode, and close the GitHub issue upon completion.

## GitHub Issue Creation Format
All GitHub issues MUST follow this structure in GitHub:
- **Label**: (ug, nhancement, documentation, etc.)
- **User Story**: As a <role>, I want <feature/fix> so that <benefit>.
- **Gherkin Scenario**:
  - **Given**: Initial context / state
  - **When**: Action performed
  - **Then**: Expected outcome
- **Proposed Technical Details**: Root cause analysis and proposed architecture changes.
- **Implemented Resolution**: Exact fix and verification steps.
