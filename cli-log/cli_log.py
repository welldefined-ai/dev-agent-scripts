#!/usr/bin/env python3
import sys
import select
import os
from datetime import datetime
import termios
import tty
import pty
import signal
import fcntl
import struct
import re

def strip_ansi_codes_for_output(text):
    """Remove ANSI escape sequences from OUTPUT text for clean logging."""
    # For output, we want to remove colors and formatting but keep the text content
    patterns = [
        # CSI sequences (colors, cursor movement, etc.)
        r'\x1B\[[0-?]*[ -/]*[@-~]',
        # OSC sequences (terminal title, etc.)
        r'\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)',
        # Two-character sequences (character sets, etc.)
        r'\x1B[()][A-Z0-9]',
        # SS3 sequences (function keys)
        r'\x1BO[A-Z0-9]',
        # Single character sequences
        r'\x1B[>=MNOPVXcmno78]',
        # DCS, PM, APC sequences
        r'\x1B[PX^_][^\x1B]*\x1B\\',
        # RIS (Reset to Initial State)
        r'\x1Bc',
    ]

    combined_pattern = '|'.join(patterns)
    ansi_pattern = re.compile(combined_pattern)
    return ansi_pattern.sub('', text)

def format_input_for_logging(text):
    """Format user input for logging, preserving navigation keys but making them readable."""
    # Convert escape sequences to readable format for logging
    formatted = text
    
    # Replace common escape sequences with readable names
    replacements = [
        # CSI format arrows (ESC [ X)
        ('\x1b[A', '[UP]'),
        ('\x1b[B', '[DOWN]'),
        ('\x1b[C', '[RIGHT]'),
        ('\x1b[D', '[LEFT]'),
        # SS3 format arrows (ESC O X) - common in application mode
        ('\x1bOA', '[UP]'),
        ('\x1bOB', '[DOWN]'),
        ('\x1bOC', '[RIGHT]'),
        ('\x1bOD', '[LEFT]'),
        # Navigation keys
        ('\x1b[H', '[HOME]'),
        ('\x1b[F', '[END]'),
        ('\x1bOH', '[HOME]'),     # Alternative SS3 format
        ('\x1bOF', '[END]'),      # Alternative SS3 format
        ('\x1b[3~', '[DELETE]'),
        ('\x1b[2~', '[INSERT]'),
        ('\x1b[5~', '[PAGE_UP]'),
        ('\x1b[6~', '[PAGE_DOWN]'),
        # Function keys (SS3 format)
        ('\x1bOP', '[F1]'),
        ('\x1bOQ', '[F2]'),
        ('\x1bOR', '[F3]'),
        ('\x1bOS', '[F4]'),
        # Editing keys
        ('\x7f', '[BACKSPACE]'),
        ('\x08', '[BACKSPACE]'),
        ('\x1b', '[ESC]'),
    ]
    
    for escape_seq, readable in replacements:
        formatted = formatted.replace(escape_seq, readable)
    
    # Remove other control characters that aren't useful for logging
    control_chars_to_remove = [
        '\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',
        '\x0b', '\x0c', '\x0e', '\x0f', '\x10', '\x11', '\x12', '\x13',
        '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1a', '\x1c',
        '\x1d', '\x1e', '\x1f'
    ]
    
    for char in control_chars_to_remove:
        formatted = formatted.replace(char, '')
    
    return formatted

def clean_user_input(text, input_context):
    """Format user input for logging, preserving navigation operations."""
    # Use the new formatting function that preserves but formats navigation keys
    return format_input_for_logging(text)

def read_and_relay_output(master_fd, log_file, output_buffer, current_input_line):
    """Read output from master_fd, display to terminal, and log without ANSI codes."""
    try:
        data = os.read(master_fd, 1024)
        if data:
            # Display original output with ANSI codes to terminal
            os.write(sys.stdout.fileno(), data)
            sys.stdout.flush()
            # Strip ANSI codes when logging output
            clean_output = strip_ansi_codes_for_output(data.decode('utf-8', errors='replace'))
            output_buffer['data'] += clean_output
            
            # Log complete lines, but filter out echo of user input
            if '\n' in output_buffer['data'] or '\r' in output_buffer['data']:
                lines = output_buffer['data'].replace('\r', '\n').split('\n')
                for line in lines[:-1]:  # All complete lines
                    stripped_line = line.strip()
                    if stripped_line and not is_echo_of_input(stripped_line, current_input_line['data']):
                        log_file.write(f"[OUTPUT] {stripped_line}\n")
                output_buffer['data'] = lines[-1]  # Keep incomplete line in buffer
                log_file.flush()
            return True
        return False
    except OSError:
        return False


def is_echo_of_input(output_line, current_input):
    """Check if the output line is likely an echo of user input."""
    # Check for multiple prompts in one line (character-by-character echo)
    prompt_count = output_line.count('>>>')
    if prompt_count > 1:
        return True
    
    # Check for incremental typing patterns like ">>> p>>> pr>>> pri"
    if '>>>' in output_line:
        # Extract everything after the last prompt
        last_prompt_idx = output_line.rfind('>>>')
        if last_prompt_idx != -1:
            after_prompt = output_line[last_prompt_idx + 3:].strip()
            # If it's a short fragment and contains incremental text, it's likely echo
            if len(after_prompt) < 100 and ('>>>' in output_line[:last_prompt_idx]):
                return True
    
    # Check for shell prompts with similar patterns
    for prompt in ['$ ', '# ', '> ']:
        if prompt in output_line and output_line.count(prompt) > 1:
            return True
    
    # Check if it's just echoing what the user is typing
    cleaned_output = output_line
    for prompt in ['>>> ', '... ', '$ ', '# ', '> ']:
        cleaned_output = cleaned_output.replace(prompt, ' ')
    
    if current_input and len(current_input.strip()) > 0:
        # Check if the cleaned output contains partial matches of current input
        clean_input = current_input.strip()
        if clean_input in cleaned_output or cleaned_output.strip() in clean_input:
            return True
    
    return False

def main():
    if len(sys.argv) < 2:
        print("Usage: cli-log <command> [args...]", file=sys.stderr)
        sys.exit(1)
    
    # Get command and its arguments
    command = sys.argv[1]
    command_args = sys.argv[1:]
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_filename = f"{command}-{timestamp}.log"
    
    # Open log file
    with open(log_filename, 'w', encoding='utf-8') as log_file:
        log_file.write(f"CLI Log Session: {' '.join(command_args)}\n")
        log_file.write(f"Started at: {datetime.now().isoformat()}\n")
        log_file.write("="*80 + "\n\n")
        log_file.flush()
        
        # Create a pseudo-terminal
        master_fd, slave_fd = pty.openpty()
        
        # Fork a child process
        pid = os.fork()
        
        if pid == 0:  # Child process
            os.close(master_fd)
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)
            
            # Execute the command
            try:
                os.execvp(command, command_args)
            except OSError as e:
                print(f"Error executing {command}: {e}", file=sys.stderr)
                sys.exit(1)
        
        else:  # Parent process
            os.close(slave_fd)
            
            # Save original terminal settings
            old_tty = None
            if sys.stdin.isatty():
                old_tty = termios.tcgetattr(sys.stdin)
            child_exit_status = None
            input_buffer = ""
            output_buffer = {"data": ""}
            current_input_line = {"data": ""}
            raw_input_buffer = ""  # Buffer for handling fragmented escape sequences
            try:
                # Set stdin to raw mode if it's a tty
                if sys.stdin.isatty():
                    tty.setraw(sys.stdin.fileno())
                
                # Handle window size changes
                def handle_winch(_signum, _frame):
                    if sys.stdin.isatty():
                        rows, cols = os.popen('stty size', 'r').read().split()
                        fcntl.ioctl(master_fd, termios.TIOCSWINSZ,
                                  struct.pack('HHHH', int(rows), int(cols), 0, 0))
                
                signal.signal(signal.SIGWINCH, handle_winch)
                
                # Relay I/O between user and subprocess
                while True:
                    try:
                        # Check if there's data to read
                        r, _, _ = select.select([sys.stdin, master_fd], [], [], 0.01)
                        
                        if sys.stdin in r:
                            # Read from user input
                            data = os.read(sys.stdin.fileno(), 1024)
                            if data:
                                os.write(master_fd, data)
                                # Process input for logging (preserves navigation keys as readable text)
                                decoded_data = data.decode('utf-8', errors='replace')
                                formatted_input = clean_user_input(decoded_data, input_buffer)
                                
                                # Add to buffer if there's content
                                if formatted_input:
                                    input_buffer += formatted_input
                                    current_input_line['data'] += formatted_input
                                
                                # Check for line completion (Enter pressed)
                                if '\n' in decoded_data or '\r' in decoded_data:
                                    # When Enter is pressed, we want to capture what was actually on the line
                                    # This handles cases where history navigation populated the command
                                    lines = input_buffer.replace('\r', '\n').split('\n')
                                    for line in lines[:-1]:  # All complete lines
                                        if line.strip():  # Only log non-empty lines
                                            log_file.write(f"[USER INPUT] {line}\n")
                                    input_buffer = lines[-1]  # Keep incomplete line in buffer
                                    current_input_line['data'] = input_buffer  # Reset current line tracker
                                    log_file.flush()
                        
                        if master_fd in r:
                            # Read from subprocess output
                            if not read_and_relay_output(master_fd, log_file, output_buffer, current_input_line):
                                break
                        
                        # Check if child process has exited
                        pid_result, status = os.waitpid(pid, os.WNOHANG)
                        if pid_result != 0:
                            # Read any remaining output
                            while read_and_relay_output(master_fd, log_file, output_buffer, current_input_line):
                                pass
                            child_exit_status = status
                            break
                            
                    except KeyboardInterrupt:
                        os.kill(pid, signal.SIGINT)
                        continue
                    except Exception:
                        break
                
            finally:
                # Restore terminal settings
                if old_tty is not None:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty)
                os.close(master_fd)
                
                # Wait for child to exit if we haven't already
                if child_exit_status is None:
                    _, child_exit_status = os.waitpid(pid, 0)
                
                exit_code = os.WEXITSTATUS(child_exit_status) if os.WIFEXITED(child_exit_status) else 1
                
                # Flush any remaining buffered data
                if input_buffer.strip():
                    log_file.write(f"[USER INPUT] {input_buffer}\n")
                if output_buffer["data"].strip():
                    log_file.write(f"[OUTPUT] {output_buffer['data']}\n")
                
                log_file.write(f"\n\nSession ended at: {datetime.now().isoformat()}\n")
                log_file.write(f"Exit code: {exit_code}\n")
                
                sys.exit(exit_code)

if __name__ == "__main__":
    main()
