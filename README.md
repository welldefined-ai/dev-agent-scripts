# dev-agent-scripts
A collection of handy scripts that direct AI agents like Claude Code to assist with development tasks.

## Git History Analysis Script

The `summarize_commit_history.sh` script automatically analyzes your Git commit history
and generates high-level summaries of your project's evolution. It processes commits in
configurable blocks (default 100) and uses Claude CLI to create intelligent summaries
focusing on architectural changes, major features, and design evolution rather than
low-level implementation details. The script outputs a timestamped YAML file
(`history_summary_YYYYMMDD_HHMMSS.yml`) containing chronological evolution blocks with
summaries and key changes. It supports resume functionality to continue interrupted
analyses and handles edge cases like partial blocks gracefully. Requires Git repository
access and Claude CLI authentication.

**Usage:** `./summarize_commit_history.sh -i 50 -f my_analysis` or
`./summarize_commit_history.sh --continue` to resume.
