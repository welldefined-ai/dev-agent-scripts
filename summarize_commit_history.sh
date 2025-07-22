#!/bin/bash

# Git History Analysis Script using Claude Code CLI
# Analyzes commit history in configurable blocks and generates evolution summary

set -euo pipefail

# Default values
COMMIT_INTERVAL=100
BASE_HISTORY_FILE="history_summary"
TIMESTAMP=""

# Function to print output without colors
print_info() {
    echo "[INFO] $1"
}

print_success() {
    echo "[SUCCESS] $1"
}

print_warning() {
    echo "[WARNING] $1"
}

print_error() {
    echo "[ERROR] $1"
}

# Function to generate or get timestamp
get_timestamp() {
    local timestamp_file=".git_history_timestamp"
    local continue_session=$1
    
    if [[ "$continue_session" == "true" && -f "$timestamp_file" ]]; then
        cat "$timestamp_file"
    else
        local ts=$(date +"%Y%m%d_%H%M%S")
        echo "$ts" > "$timestamp_file"
        echo "$ts"
    fi
}

# Function to display usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Analyze Git commit history in blocks and generate evolution summary using Claude Code CLI.

OPTIONS:
    -i, --interval INTERVAL     Number of commits per analysis block (default: 100)
    -f, --file FILE            Base output history file name (default: history_summary)
    -c, --continue             Continue from existing history analysis with same timestamp
    -h, --help                 Display this help message

EXAMPLES:
    $0                         # Use defaults (100 commits per block)
    $0 -i 50                   # Analyze in blocks of 50 commits
    $0 -i 10 -f my_summary     # Use 10 commits per block, custom base file name
    $0 --continue              # Resume from existing history analysis

NOTE:
    Files are automatically timestamped (e.g., history_summary_20250122_143022.yml)
    to ensure each full analysis run has a unique identifier.

REQUIREMENTS:
    - Git repository with commit history
    - Claude Code CLI installed and configured
    - Internet connection for Claude API

EOF
}

# Function to check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites..."
    
    # Check if we're in a git repository
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        print_error "Not in a Git repository. Please run this script from within a Git repository."
        exit 1
    fi
    
    # Check if claude CLI is available
    if ! command -v claude &> /dev/null; then
        print_error "Claude Code CLI not found. Please install it first:"
        print_error "  npm install -g @anthropic-ai/claude-cli"
        print_error "Or visit: https://docs.anthropic.com/en/docs/claude-code/quickstart"
        exit 1
    fi
    
    # Note: Authentication will be checked naturally when Claude is first called
    
    print_success "Prerequisites check passed"
}

# Function to initialize or continue session  
initialize_session() {
    local continue_session=$1
    
    # Get timestamp and set file/session names - output them so they can be captured
    local timestamp=$(get_timestamp "$continue_session")
    local history_file="${BASE_HISTORY_FILE}_${timestamp}.yml"
    
    if [[ "$continue_session" == "true" ]]; then
        if [[ -f "$history_file" ]]; then
            # Extract last processed commit and current block from existing file
            if grep -q "last_processed_commit:" "$history_file"; then
                local last_commit=$(grep "last_processed_commit:" "$history_file" | head -1 | cut -d'"' -f2)
                local current_block=$(grep "current_block:" "$history_file" | head -1 | awk '{print $2}')
                # Output format: timestamp:history_file:last_commit:current_block
                echo "$timestamp:$history_file:$last_commit:$current_block"
                return
            fi
        fi
    fi
    
    # Start fresh analysis - output format: timestamp:history_file:FRESH:0
    echo "$timestamp:$history_file:FRESH:0"
}

# Function to print session initialization info (called after session_info is parsed)
print_session_info() {
    local continue_session=$1
    local last_commit=$2
    local start_block=$3
    
    if [[ "$continue_session" == "true" && "$last_commit" != "FRESH" ]]; then
        print_info "Continuing from existing history file: $HISTORY_FILE"
        print_info "Last processed commit: $last_commit"
        print_info "Current block: $start_block"
    else
        print_info "Starting fresh Git history analysis with timestamp: $TIMESTAMP"
        print_info "History file: $HISTORY_FILE"
    fi
}

# Function to get total commit count
get_total_commits() {
    git log --oneline | wc -l | tr -d ' '
}

# Function to get commit range
get_commit_range() {
    local start_index=$1
    local end_index=$2
    
    local start_commit=$(git log --oneline --reverse | sed -n "${start_index}p" | cut -d' ' -f1)
    local end_commit=$(git log --oneline --reverse | sed -n "${end_index}p" | cut -d' ' -f1)
    
    if [[ -n "$start_commit" && -n "$end_commit" ]]; then
        echo "$start_commit..$end_commit"
    else
        echo ""
    fi
}

# Function to create initial history file
create_initial_history() {
    local total_commits=$1
    local current_date=$(date +"%Y-%m-%d")
    
    cat > "$HISTORY_FILE" << EOF
project_evolution_summary:
  metadata:
    total_commits: $total_commits
    analysis_method: "${COMMIT_INTERVAL}-commit blocks"
    generated_date: "$current_date"
    last_processed_commit: ""
    current_block: 0

  evolution_blocks:
EOF
    
    print_success "Created initial history file: $HISTORY_FILE"
}

# Function to analyze commit block using Claude Code CLI
analyze_commit_block() {
    local block_id=$1
    local start_index=$2
    local end_index=$3
    local total_commits=$4
    
    local commit_range=$(get_commit_range $start_index $end_index)
    
    if [[ -z "$commit_range" ]]; then
        print_error "No commits found in range $start_index-$end_index - this may indicate git log parsing failed"
        print_error "Total commits: $total_commits, Start: $start_index, End: $end_index"
        return 1
    fi
    
    print_info "Analyzing block $block_id: commits $start_index-$end_index ($commit_range)"
    
    # Get commit list for this block
    local commit_list=$(git log --oneline --reverse | sed -n "${start_index},${end_index}p")
    
    # Get code changes summary
    local start_commit=$(echo "$commit_range" | cut -d'.' -f1)
    local end_commit=$(echo "$commit_range" | cut -d'.' -f3)
    local code_changes=$(git diff "$start_commit".."$end_commit" --stat 2>/dev/null || echo "No changes detected")
    
    # Create prompt for Claude - only ask for analysis content, not file operations
    local prompt="# Git History Analysis Task

Analyze this block of commits and provide the content for a YAML history entry.

## Commit Block Details
- **Block ID**: $block_id  
- **Commit Range**: $commit_range
- **Position**: Commits ${start_index}-${end_index} of $total_commits total
- **End Commit Hash**: $end_commit

## Commits in This Block
\`\`\`
$commit_list
\`\`\`

## Code Changes Summary  
\`\`\`
$code_changes
\`\`\`

## Analysis Guidelines
- Focus on major architectural changes and design evolution
- Identify key functional additions or modifications  
- Note important refactoring or structural improvements
- Highlight significant technology adoption or framework changes
- Write a concise 2-3 sentence summary of the main changes
- Avoid low-level implementation details

## Required Output Format
Please provide ONLY the analysis content in this exact format:

SUMMARY: [Your 2-3 sentence high-level summary here]
KEY_CHANGES:
- [Key change 1]
- [Key change 2] 
- [Key change 3]
- [Additional changes as needed]

Do not include any other text, explanations, or YAML formatting - just the summary and key changes as specified above."

    # Call Claude Code CLI with session continuity
    print_info "Sending analysis request to Claude Code CLI..."
    
    # Save prompt to temporary file for debugging
    local prompt_file="/tmp/claude_prompt_block_${block_id}.txt"
    echo "$prompt" > "$prompt_file"
    print_info "Prompt saved to: $prompt_file"
    
    # Call Claude CLI and get analysis content
    print_info "Getting analysis from Claude CLI..."
    local claude_output
    if ! claude_output=$(echo "$prompt" | claude -p 2>/dev/null); then
        print_error "Failed to get analysis from Claude for block $block_id"
        return 1
    fi
    
    # Parse Claude's response to extract summary and key changes
    local summary=$(echo "$claude_output" | grep "SUMMARY:" | sed 's/SUMMARY: //')
    local key_changes_section=$(echo "$claude_output" | sed -n '/KEY_CHANGES:/,/^$/p' | tail -n +2)
    
    # Validate that we got content
    if [[ -z "$summary" ]]; then
        print_error "Failed to extract summary from Claude response for block $block_id"
        print_error "Claude output: $claude_output"
        return 1
    fi
    
    print_info "Analysis received from Claude"
    
    # Add the new block to the history file using bash
    print_info "Adding block $block_id to history file..."
    
    # Create the YAML block entry
    local yaml_block="  - block_id: $block_id
    commit_range: \"$commit_range\"
    commits: \"${start_index}-${end_index}\"
    summary: \"$summary\""
    
    # Add key changes if we have them
    if [[ -n "$key_changes_section" ]]; then
        yaml_block="$yaml_block
    key_changes:"
        while IFS= read -r line; do
            if [[ -n "$line" && "$line" =~ ^-\ .+ ]]; then
                yaml_block="$yaml_block
      \"$(echo "$line" | sed 's/^- //')\""
            fi
        done <<< "$key_changes_section"
    fi
    
    # Append the block to the evolution_blocks section
    echo "$yaml_block" >> "$HISTORY_FILE"
    
    # Update the metadata in the file
    print_info "Updating metadata in history file..."
    
    # Create temporary file for atomic update
    local temp_file="${HISTORY_FILE}.tmp"
    
    # Update last_processed_commit and current_block in metadata
    sed "s/last_processed_commit: .*/last_processed_commit: \"$end_commit\"/" "$HISTORY_FILE" | \
    sed "s/current_block: .*/current_block: $block_id/" > "$temp_file"
    
    # Replace original file
    mv "$temp_file" "$HISTORY_FILE"
    
    print_success "Completed analysis for block $block_id"
    return 0
}

# Main analysis function
run_analysis() {
    local continue_session=$1
    
    print_info "Starting Git history analysis with $COMMIT_INTERVAL commits per block"
    
    # Initialize session and get starting point
    local session_info=$(initialize_session "$continue_session")
    TIMESTAMP=$(echo "$session_info" | cut -d':' -f1)
    HISTORY_FILE=$(echo "$session_info" | cut -d':' -f2)
    local last_commit=$(echo "$session_info" | cut -d':' -f3)
    local start_block=$(echo "$session_info" | cut -d':' -f4)
    
    # Ensure start_block is numeric (default to 0 if not)
    if ! [[ "$start_block" =~ ^[0-9]+$ ]]; then
        print_warning "Non-numeric start block value detected, defaulting to 0"
        start_block=0
    fi
    
    # Print session information
    print_session_info "$continue_session" "$last_commit" "$start_block"
    
    # Get total commits
    local total_commits=$(get_total_commits)
    print_info "Repository has $total_commits total commits"
    
    # Create or verify history file
    if [[ "$last_commit" == "FRESH" ]]; then
        create_initial_history "$total_commits"
        local start_index=1
        local current_block=1
    else
        # Find starting index from last processed commit
        # start_block contains the last completed block number
        local start_index=$((start_block * COMMIT_INTERVAL + 1))
        local current_block=$((start_block + 1))
        print_info "Resuming from block $current_block (commit index $start_index)"
    fi
    
    # Initialize Claude session for this analysis run  
    print_info "Preparing Claude Code CLI for analysis"
    print_info "Each block will be processed independently with file context"
    
    # Process blocks
    local block_errors=0
    
    while [[ $start_index -le $total_commits ]]; do
        local end_index=$((start_index + COMMIT_INTERVAL - 1))
        if [[ $end_index -gt $total_commits ]]; then
            end_index=$total_commits
        fi
        
        print_info "Processing block $current_block: commits $start_index-$end_index"
        
        if analyze_commit_block "$current_block" "$start_index" "$end_index" "$total_commits"; then
            print_success "Block $current_block completed successfully"
        else
            print_error "Failed to process block $current_block"
            ((block_errors++))
            
            if [[ $block_errors -ge 3 ]]; then
                print_error "Too many consecutive errors. Stopping analysis."
                break
            fi
            
            print_warning "Continuing with next block..."
        fi
        
        start_index=$((end_index + 1))
        ((current_block++))
        
        # Small delay to avoid overwhelming the API
        sleep 1
    done
    
    # Check if we actually have a complete analysis by counting blocks in file
    local blocks_in_file=0
    if [[ -f "$HISTORY_FILE" ]]; then
        blocks_in_file=$(grep -c "block_id:" "$HISTORY_FILE" 2>/dev/null || echo "0")
    fi
    
    if [[ $blocks_in_file -gt 0 && $block_errors -eq 0 ]]; then
        print_success "Git history analysis completed successfully!"
        print_success "Results saved to: $HISTORY_FILE"
        print_info "Total blocks processed: $blocks_in_file"
    elif [[ $blocks_in_file -gt 0 ]]; then
        # We have blocks but some errors occurred - check if it's just verification issues
        print_success "Git history analysis completed with $blocks_in_file blocks processed"
        print_warning "There were $block_errors processing errors, but results may still be complete"
        print_info "Results saved to: $HISTORY_FILE"
    else
        print_error "Analysis failed - no blocks were successfully processed"
        print_info "Check $HISTORY_FILE for any partial results"
    fi
}

# Parse command line arguments
CONTINUE_SESSION=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--interval)
            COMMIT_INTERVAL="$2"
            shift 2
            ;;
        -f|--file)
            BASE_HISTORY_FILE="$2"
            shift 2
            ;;
        -c|--continue)
            CONTINUE_SESSION=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate commit interval
if ! [[ "$COMMIT_INTERVAL" =~ ^[0-9]+$ ]] || [[ "$COMMIT_INTERVAL" -le 0 ]]; then
    print_error "Commit interval must be a positive integer"
    exit 1
fi

# Main execution
main() {
    print_info "Git History Analysis Script"
    print_info "============================="
    print_info "Commit interval: $COMMIT_INTERVAL"
    print_info "Base history file: $BASE_HISTORY_FILE"
    print_info "Continue mode: $CONTINUE_SESSION"
    echo
    
    check_prerequisites
    run_analysis "$CONTINUE_SESSION"
}

# Run main function
main "$@"
