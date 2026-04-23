#!/usr/bin/env python3
"""Agent Watchdog - Monitors agents directly and auto-sends 'continue' when they pause."""

from __future__ import annotations

import os
import sys
import re
import time
import signal
import logging
import atexit
import select
import fcntl
import struct
import tty
import termios
from typing import Optional, Pattern, List
from dataclasses import dataclass

try:
    import pty

    HAS_PTY = True
except ImportError:
    HAS_PTY = False

logger = logging.getLogger(__name__)


@dataclass
class WatchdogConfig:
    """Configuration for the watchdog utility."""

    # Patterns to detect when agent is waiting/paused
    continue_patterns: List[str] = None
    # Timeout in seconds - if no output for this long, consider agent stuck
    inactivity_timeout: float = 30.0
    # Debounce period - wait this long after sending continue before checking again
    debounce_period: float = 2.0
    # Maximum consecutive auto-continues before requiring manual intervention
    max_auto_continues: int = 10
    # Maximum buffer size (characters) to retain for pattern matching
    max_buffer_size: int = 8192
    # Log file path
    log_file: Optional[str] = None
    # Echo output to stdout
    echo: bool = True

    def __post_init__(self):
        if self.continue_patterns is None:
            self.continue_patterns = [
                r'type\s+[\'\\"]continue[\'\\"]',
                r"press\s+.*\bcontinue\b",
                r"enter\s+.*\bcontinue\b",
                r"\bcontinue\b.*to\s+proceed",
                r"\[.*\bcontinue\b.*\]",
                r"\bstopped\b",
                r"\bpaused\b",
                r"Completed in \d+m \d+s",
            ]


class AgentWatchdog:
    """Monitors agents directly and auto-sends 'continue' when they pause."""

    def __init__(self, command: List[str], config: WatchdogConfig):
        self.command = command
        self.config = config
        self.pid = None  # Child process PID
        self.fd = None  # PTY file descriptor
        self.running = False
        self.last_output_time = 0.0
        self.auto_continue_count = 0
        self.compiled_patterns: List[Pattern] = []
        self._debounce_until: float = (
            0.0  # Timestamp until which to ignore pattern matches
        )
        self._old_termios = None  # Save original terminal settings

        self._setup_logging()
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for matching."""
        self.compiled_patterns = []
        for pattern in self.config.continue_patterns:
            try:
                compiled = re.compile(pattern, re.MULTILINE | re.DOTALL)
                self.compiled_patterns.append(compiled)
            except re.error as e:
                logger.warning(f"Invalid regex pattern '{pattern}': {e}")

    def _setup_logging(self):
        """Configure logging."""
        log_level = logging.INFO
        if self.config.log_file:
            # Log to file
            logging.basicConfig(
                level=log_level,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                filename=self.config.log_file,
                filemode="a",
            )
        else:
            # Log to console
            logging.basicConfig(
                level=log_level, format="%(asctime)s - %(name)s - %(levelname)s"
            )

    def _match_pattern(self, text: str) -> bool:
        """Check if text contains any continue patterns."""
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return True
        return False

    def _handle_continue_prompt(self):
        """Handle detected continue prompt by sending continue command."""
        if self.auto_continue_count >= self.config.max_auto_continues:
            logger.error(
                f"Exceeded maximum auto-continues ({self.config.max_auto_continues}). "
                "Manual intervention required."
            )
            self.running = False
            return

        self.auto_continue_count += 1
        logger.info(
            f"Sending 'continue' (attempt {self.auto_continue_count}/{self.config.max_auto_continues})"
        )

        self._send_input("continue\n")
        time.sleep(self.config.debounce_period)

    def _set_pty_size(self):
        """Set PTY window size to match current terminal size."""
        if self.fd is None:
            return

        try:
            # Get current terminal size
            size = os.get_terminal_size()
            rows, cols = size.lines, size.columns

            # Set PTY window size using ioctl
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)

            logger.debug(f"Set PTY size to {cols}x{rows}")
        except Exception as e:
            logger.warning(f"Could not set PTY size: {e}")

    def _send_input(self, text: str):
        """Send input to the agent process."""
        self._send_input_to_pty(self.fd, text)

    def _send_input_to_pty(self, fd, text: str):
        """Send input to the PTY."""
        if fd is None:
            return
        try:
            os.write(fd, text.encode("utf-8"))
            logger.debug(f"Sent: {text.strip()}")
        except Exception as e:
            logger.error(f"Error sending input: {e}")

    def _window_resize_handler(self, signum, frame):
        """Handle window resize signals."""
        if self.fd is not None:
            self._set_pty_size()

    def _cleanup(self):
        """Cleanup PTY and process."""
        # Restore terminal settings
        if self._old_termios is not None:
            try:
                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSADRAIN, self._old_termios
                )
            except Exception as e:
                logger.error(f"Error restoring terminal settings: {e}")

        # Close PTY file descriptor
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception as e:
                logger.error(f"Error closing PTY: {e}")

        # Terminate child process
        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGTERM)
                time.sleep(0.5)
                try:
                    os.kill(self.pid, 0)  # Check if still alive
                    os.kill(self.pid, signal.SIGKILL)  # Force kill if still running
                except OSError:
                    pass  # Process already exited
            except Exception as e:
                logger.error(f"Error terminating process: {e}")

    def run(self):
        """Main watchdog loop using direct PTY control for reliable monitoring."""
        if not HAS_PTY:
            raise RuntimeError("pty module is required for terminal monitoring")

        logger.info(f"Starting agent: {' '.join(self.command)}")
        logger.info(
            f"Watching for patterns: {[p.pattern for p in self.compiled_patterns]}"
        )

        # Register cleanup handlers
        atexit.register(self._cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGWINCH, self._window_resize_handler)

        # Save original terminal settings and set raw mode
        try:
            self._old_termios = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())
        except Exception as e:
            logger.warning(f"Could not set raw mode: {e}")

        try:
            # Use pty.fork() for direct PTY control
            pid, fd = pty.fork()

            if pid == 0:
                # Child process: execute the agent command
                try:
                    os.execvp(self.command[0], self.command)
                except Exception as e:
                    logger.error(f"Failed to execute command: {e}")
                    sys.exit(1)

            # Parent process: monitor the PTY
            self.running = True
            self.last_output_time = time.time()
            self.pid = pid
            self.fd = fd

            # Set PTY window size to match current terminal
            self._set_pty_size()

            # Main monitoring loop with direct select-based I/O
            buffer = ""

            while self.running:
                try:
                    # Use select to monitor PTY and stdin
                    rlist, _, _ = select.select([fd, sys.stdin.fileno()], [], [], 0.1)

                    # Handle PTY output (agent output)
                    if fd in rlist:
                        try:
                            data = os.read(fd, 4096)
                            if data:
                                # Decode and process output
                                output = data.decode("utf-8", errors="ignore")
                                buffer += output
                                self.last_output_time = time.time()

                                # Enforce buffer size limit
                                if len(buffer) > self.config.max_buffer_size:
                                    buffer = buffer[-self.config.max_buffer_size :]

                                # Echo to stdout
                                if self.config.echo:
                                    sys.stdout.write(output)
                                    sys.stdout.flush()

                                # Check for continue patterns
                                if self._match_pattern(buffer):
                                    logger.info("Continue prompt detected")
                                    self._handle_continue_prompt()
                                    buffer = ""  # Clear buffer after handling
                            else:
                                # EOF from PTY - process exited
                                break
                        except OSError:
                            # PTY closed
                            break

                    # Handle stdin input (user input)
                    if sys.stdin.fileno() in rlist:
                        try:
                            user_input = os.read(sys.stdin.fileno(), 1024)
                            if user_input:
                                # Forward to PTY
                                os.write(fd, user_input)
                        except EOFError:
                            # User pressed Ctrl+D
                            logger.info("EOF on stdin, shutting down...")
                            self.running = False
                            break

                    # Check for inactivity timeout
                    current_time = time.time()
                    if (
                        self.config.inactivity_timeout > 0
                        and current_time - self.last_output_time
                        > self.config.inactivity_timeout
                    ):
                        logger.warning(
                            f"No output for {current_time - self.last_output_time:.1f}s, agent may be stuck"
                        )
                        # Try to send newline to wake it up
                        self._send_input_to_pty(fd, "\n")
                        time.sleep(self.config.debounce_period)

                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received")
                    self.running = False
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in watchdog loop: {e}")
                    break

            # Wait for child process to finish
            try:
                os.waitpid(pid, 0)
            except OSError:
                pass  # Process already exited

        finally:
            self._cleanup()
            atexit.unregister(self._cleanup)

    def _signal_handler(self, signum, frame):
        """Handle termination signals."""
        logger.info(f"Received signal {signum}")
        self.running = False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Agent watchdog with continue automation"
    )
    parser.add_argument("command", nargs="+", help="Agent command to run")
    parser.add_argument(
        "--inactivity-timeout",
        type=float,
        default=30.0,
        help="Inactivity timeout in seconds (default: 30.0)",
    )
    parser.add_argument(
        "--debounce-period",
        type=float,
        default=2.0,
        help="Debounce period after sending continue (default: 2.0)",
    )
    parser.add_argument(
        "--max-auto-continues",
        type=int,
        default=10,
        help="Maximum auto-continues before stopping (default: 10)",
    )
    parser.add_argument(
        "--max-buffer-size",
        type=int,
        default=8192,
        help="Maximum buffer size for pattern matching (default: 8192)",
    )
    parser.add_argument("--log-file", help="Log file path")
    parser.add_argument(
        "--no-echo",
        action="store_true",
        help="Disable echoing output to stdout",
    )

    args = parser.parse_args()

    config = WatchdogConfig(
        inactivity_timeout=args.inactivity_timeout,
        debounce_period=args.debounce_period,
        max_auto_continues=args.max_auto_continues,
        max_buffer_size=args.max_buffer_size,
        log_file=args.log_file,
        echo=not args.no_echo,
    )

    watchdog = AgentWatchdog(args.command, config)
    watchdog.run()


if __name__ == "__main__":
    main()
