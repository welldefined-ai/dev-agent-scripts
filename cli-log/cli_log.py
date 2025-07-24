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

def read_and_relay_output(master_fd, log_file):
    """Read output from master_fd, display to terminal, and log without ANSI codes."""
    try:
        data = os.read(master_fd, 1024)
        if data:
            # Display original output with ANSI codes to terminal
            os.write(sys.stdout.fileno(), data)
            sys.stdout.flush()
            # Strip ANSI codes when logging output
            clean_output = strip_ansi_codes(data.decode('utf-8', errors='replace'))
            log_file.write(f"[OUTPUT] {clean_output}")
            log_file.flush()
            return True
        return False
    except OSError:
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
            old_tty = termios.tcgetattr(sys.stdin)
            child_exit_status = None
            try:
                # Set stdin to raw mode
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
                                # Strip ANSI codes when logging user input
                                clean_input = strip_ansi_codes(data.decode('utf-8', errors='replace'))
                                log_file.write(f"[USER INPUT] {clean_input}")
                                log_file.flush()
                        
                        if master_fd in r:
                            # Read from subprocess output
                            if not read_and_relay_output(master_fd, log_file):
                                break
                        
                        # Check if child process has exited
                        pid_result, status = os.waitpid(pid, os.WNOHANG)
                        if pid_result != 0:
                            # Read any remaining output
                            while read_and_relay_output(master_fd, log_file):
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
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty)
                os.close(master_fd)
                
                # Wait for child to exit if we haven't already
                if child_exit_status is None:
                    _, child_exit_status = os.waitpid(pid, 0)
                
                exit_code = os.WEXITSTATUS(child_exit_status) if os.WIFEXITED(child_exit_status) else 1
                
                log_file.write(f"\n\nSession ended at: {datetime.now().isoformat()}\n")
                log_file.write(f"Exit code: {exit_code}\n")
                
                sys.exit(exit_code)

if __name__ == "__main__":
    main()
