# cli-log

A tool that logs CLI sessions by capturing all input and output while preserving the interactive experience.

## Installation

```bash
./setup.sh
```

This creates a virtual environment and installs cli-log as an editable package.

## Usage

```bash
cli-log <command> [args...]
```

### Examples

```bash
# Log a Python REPL session
cli-log python

# Log a Git workflow
cli-log git status

# Log an SSH session
cli-log ssh user@server

# Log a complex command with arguments
cli-log docker run -it ubuntu bash
```

## Output

Creates timestamped log files in the current directory:
- Format: `<command>-YYYYMMDD-HHMMSS.log`
- Example: `python-20240115-143022.log`

The logs contain:
- Command executed
- Timestamp
- All user input (marked as `[USER INPUT]`)
- All output (marked as `[OUTPUT]`)
- Exit code

ANSI escape codes are stripped from logs for readability while preserving colors in the terminal.

## Features

- Preserves interactive terminal behavior (colors, cursor movement, etc.)
- Handles window resizing
- Captures exit codes
- Supports Ctrl+C interruption
- Works with any CLI application

