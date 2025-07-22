# gitsum

A Git commit history summarization tool that uses Claude Code CLI to generate intelligent summaries of your project's evolution.

## What is gitsum?

gitsum summarizes your Git commit history in configurable blocks, focusing on:
- Major architectural changes and design evolution
- Key functional additions or modifications  
- Important refactoring or structural improvements
- Significant technology adoption or framework changes

Instead of getting lost in individual commit messages, gitsum provides a bird's-eye view of how your project has evolved over time.

## Features

- **Intelligent Summarization**: Uses Claude AI to understand and summarize code changes contextually
- **Configurable Block Size**: Process commits in blocks of any size (default: 100)
- **Resume Support**: Continue interrupted summarization from where you left off
- **Timestamped Output**: Each summarization run gets a unique timestamp to avoid conflicts
- **YAML Output**: Structured, readable format for further processing or documentation

## Prerequisites

1. **Git Repository**: Must be run from within a Git repository with commit history
2. **Claude Code CLI**: Install and configure the Claude CLI
   ```bash
   npm install -g @anthropic-ai/claude-cli
   ```
   Visit the [Claude Code quickstart guide](https://docs.anthropic.com/en/docs/claude-code/quickstart) for setup instructions.
3. **Internet Connection**: Required for Claude API access

## Installation

1. Clone or download this repository
2. Make the script executable:
   ```bash
   chmod +x gitsum/gitsum.sh
   ```
3. Optionally, add to your PATH for global access:
   ```bash
   # Add to ~/.bashrc or ~/.zshrc
   export PATH="$PATH:/path/to/dev-agent-scripts/gitsum"
   ```

## Usage

### Basic Usage
```bash
# Summarize entire history with default settings (100 commits per block)
./gitsum.sh

# Summarize in smaller blocks for more detailed summaries
./gitsum.sh -i 50

# Use custom output file name
./gitsum.sh -f my_project_evolution
```

### Advanced Usage
```bash
# Resume an interrupted summarization
./gitsum.sh --continue

# Combine options
./gitsum.sh -i 25 -f detailed_analysis --continue
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `-i, --interval INTERVAL` | Number of commits per analysis block | 100 |
| `-f, --file FILE` | Base output file name | `history_summary` |
| `-c, --continue` | Continue from existing summarization | false |
| `-h, --help` | Show help message | - |

## Output Format

gitsum generates timestamped YAML files (e.g., `history_summary_20250122_143022.yml`) with the following structure:

```yaml
project_evolution_summary:
  metadata:
    total_commits: 1500
    summary_method: "100-commit blocks"
    generated_date: "2025-01-22"
    last_processed_commit: "abc123"
    current_block: 15

  evolution_blocks:
    - block_id: 1
      commit_range: "def456..abc123"
      commits: "1-100"
      summary: "Initial project setup with basic React components and routing infrastructure."
      key_changes:
        - "Set up React 18 project with TypeScript configuration"
        - "Implemented basic routing with React Router v6"
        - "Created initial component library structure"
    # ... more blocks
```

## How It Works

1. **Repository Scanning**: Scans your Git repository to count total commits
2. **Block Processing**: Divides commits into configurable blocks (default 100)
3. **AI Summarization**: For each block, sends commit diffs and messages to Claude for summarization
4. **Summary Generation**: Claude generates high-level summaries and key change lists
5. **YAML Output**: Structured results saved to timestamped files

## Tips for Best Results

- **Optimal Block Size**: 
  - 50-100 commits: Good balance of detail and overview
  - 25-50 commits: More detailed analysis for complex projects
  - 100+ commits: Higher-level summaries for large repositories

- **Resume Feature**: Use `--continue` to resume long summarizations that were interrupted

- **Multiple Runs**: Each run creates a new timestamped file, so you can experiment with different block sizes

## Performance and Cost Notes

- Summarization time depends on repository size and block size
- Each block requires an API call to Claude, so larger repositories take longer
- The script includes small delays to avoid overwhelming the API
