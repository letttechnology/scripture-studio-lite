# Repository Agent Rules & Tracking Standards

## Question Priority Protocol
- **ANSWER QUESTIONS FIRST**: When the user asks a question, you MUST answer the question directly and completely BEFORE doing anything else, taking actions, or writing/running code.

## Response Output Protocols
- **GitHub Issue Output**: ONLY print the GitHub Issue URL link (https://github.com/letttechnology/scripture-studio-lite/issues/<ID>) in the chat body. DO NOT output the issue body, Gherkin scenario, or summary text in the chat window.

## Workspace Common Tools Protocols
- **Primary Issue Script**: python D:\workspace\common\create_issue.py (or gh issue create).
- **NEVER** create temporary script files or scratch files when existing scripts in D:\workspace\common already perform the action.
- **GitHub Issues Exclusive**: ALL bugs, feature requests, and documentation items MUST be filed directly to GitHub Issues. Do NOT create local issue MD files.

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
