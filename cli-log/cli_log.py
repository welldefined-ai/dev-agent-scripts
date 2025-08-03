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

def strip_ansi_codes(text):
    """Remove ANSI escape sequences from text."""
    # Comprehensive pattern that matches various ANSI escape sequences
    patterns = [
        # CSI sequences (most common - colors, cursor movement, etc.)
        r'\x1B\[[0-?]*[ -/]*[@-~]',
        # OSC sequences (terminal title, etc.)
        r'\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)',
        # Two-character sequences (character sets, etc.)
        r'\x1B[()][A-Z0-9]',
        # SS3 sequences (function keys like F1-F4: ESC O P, ESC O Q, etc.)
        r'\x1BO[A-Z0-9]',
        # Single character sequences
        r'\x1B[>=MNOPVXcmno78]',
        # DCS, PM, APC sequences
        r'\x1B[PX^_][^\x1B]*\x1B\\',
        # RIS (Reset to Initial State)
        r'\x1Bc',
    ]

    # Combine all patterns
    combined_pattern = '|'.join(patterns)
    ansi_pattern = re.compile(combined_pattern)
    return ansi_pattern.sub('', text)

def clean_user_input(text, input_context):
    """Clean user input by removing control characters and navigation keys."""
    # First strip ANSI codes
    cleaned = strip_ansi_codes(text)
    
    # Remove common control characters that shouldn't be logged
    control_chars_to_remove = [
        '\x7f',     # DEL (backspace)
        '\x08',     # BS (backspace)
        '\x1b',     # ESC (escape sequences start)
        '\x00',     # NUL
        '\x01',     # SOH
        '\x02',     # STX
        '\x03',     # ETX (Ctrl+C, but we handle this elsewhere)
        '\x04',     # EOT (Ctrl+D)
        '\x05',     # ENQ
        '\x06',     # ACK
        '\x07',     # BEL
        '\x0b',     # VT
        '\x0c',     # FF
        '\x0e',     # SO
        '\x0f',     # SI
        '\x10',     # DLE
        '\x11',     # DC1
        '\x12',     # DC2
        '\x13',     # DC3
        '\x14',     # DC4
        '\x15',     # NAK
        '\x16',     # SYN
        '\x17',     # ETB
        '\x18',     # CAN
        '\x19',     # EM
        '\x1a',     # SUB
        '\x1c',     # FS
        '\x1d',     # GS
        '\x1e',     # RS
        '\x1f',     # US
    ]
    
    for char in control_chars_to_remove:
        cleaned = cleaned.replace(char, '')
    
    # ANSI stripping should handle all escape sequences
    # No need for additional navigation pattern removal since proper sequences
    # like \x1b[A are already handled by strip_ansi_codes()
    
    # With proper escape sequence handling, we shouldn't need aggressive ABCD filtering
    # The ANSI stripping should handle all legitimate arrow keys: \x1b[A, \x1b[B, etc.
    # Any remaining A, B, C, D characters are likely legitimate user input
    
    return cleaned

def read_and_relay_output(master_fd, log_file, output_buffer, current_input_line):
    """Read output from master_fd, display to terminal, and log without ANSI codes."""
    try:
        data = os.read(master_fd, 1024)
        if data:
            # Display original output with ANSI codes to terminal
            os.write(sys.stdout.fileno(), data)
            sys.stdout.flush()
            # Strip ANSI codes when logging output
            clean_output = strip_ansi_codes(data.decode('utf-8', errors='replace'))
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
                                # Buffer raw input to handle fragmented escape sequences
                                decoded_data = data.decode('utf-8', errors='replace')
                                raw_input_buffer += decoded_data
                                
                                # Check if we have incomplete escape sequences to preserve
                                def is_incomplete_sequence(text):
                                    # Just ESC at end
                                    if text.endswith('\x1b'):
                                        return True
                                    # CSI sequences: ESC [ followed by digits/semicolons but no final char
                                    if re.search(r'\x1b\[[0-9;]*$', text):
                                        return True
                                    # SS3 sequences: ESC O (but not complete like ESC O A)
                                    if re.search(r'\x1bO$', text):
                                        return True
                                    # OSC sequences: ESC ] but no terminator
                                    if re.search(r'\x1b\][^\x07\x1b]*$', text) and not text.endswith('\x07'):
                                        return True
                                    return False
                                
                                if is_incomplete_sequence(raw_input_buffer):
                                    # Add safety: don't buffer forever
                                    if len(raw_input_buffer) < 50:  # Reasonable limit
                                        continue
                                    # If buffer too long, probably not an escape sequence
                                
                                # Process complete sequences from the buffer
                                processed_input = strip_ansi_codes(raw_input_buffer)
                                clean_input = clean_user_input(processed_input, input_buffer)
                                
                                # Only add to buffer if it's not filtered out
                                if clean_input:
                                    input_buffer += clean_input
                                    current_input_line['data'] += clean_input
                                
                                # Clear the raw buffer after processing
                                raw_input_buffer = ""
                                
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
