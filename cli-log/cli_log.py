#!/usr/bin/env python3
import sys
import subprocess
import select
import os
import time
from datetime import datetime
import threading
import termios
import tty
import pty
import signal
import fcntl
import struct

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
            try:
                # Set stdin to raw mode
                tty.setraw(sys.stdin.fileno())
                
                # Handle window size changes
                def handle_winch(signum, frame):
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
                                log_file.write(f"[USER INPUT] {data.decode('utf-8', errors='replace')}")
                                log_file.flush()
                        
                        if master_fd in r:
                            # Read from subprocess output
                            try:
                                data = os.read(master_fd, 1024)
                                if data:
                                    os.write(sys.stdout.fileno(), data)
                                    sys.stdout.flush()
                                    log_file.write(f"[OUTPUT] {data.decode('utf-8', errors='replace')}")
                                    log_file.flush()
                                else:
                                    break
                            except OSError:
                                break
                        
                        # Check if child process has exited
                        pid_result, status = os.waitpid(pid, os.WNOHANG)
                        if pid_result != 0:
                            # Read any remaining output
                            while True:
                                try:
                                    data = os.read(master_fd, 1024)
                                    if data:
                                        os.write(sys.stdout.fileno(), data)
                                        sys.stdout.flush()
                                        log_file.write(f"[OUTPUT] {data.decode('utf-8', errors='replace')}")
                                        log_file.flush()
                                    else:
                                        break
                                except OSError:
                                    break
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
                
                # Wait for child to exit and get exit code
                _, status = os.waitpid(pid, 0)
                exit_code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else 1
                
                log_file.write(f"\n\nSession ended at: {datetime.now().isoformat()}\n")
                log_file.write(f"Exit code: {exit_code}\n")
                
                sys.exit(exit_code)

if __name__ == "__main__":
    main()
