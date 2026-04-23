#!/usr/bin/env python3
"""Agent Watchdog - Monitors agent terminals and auto-sends 'continue' when paused."""

from __future__ import annotations

import os
import sys
import re
import time
import signal
import logging
import atexit
from typing import Optional, Pattern, List
from dataclasses import dataclass

try:
    import ptyprocess

    HAS_PTYPROCESS = True
except ImportError:
    HAS_PTYPROCESS = False

# Try to import built-in pty as fallback
try:
    import pty
    import termios
    import tty

    HAS_BUILTIN_PTY = True
except ImportError:
    HAS_BUILTIN_PTY = False

logger = logging.getLogger(__name__)


@dataclass
class WatchdogConfig:
    """Configuration for the watchdog utility."""

    # Patterns to detect when agent is waiting/paused
    continue_patterns: List[str]
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


class AgentWatchdog:
    """Watches an agent's terminal and auto-sends 'continue' when it stops."""

    def __init__(self, command: List[str], config: WatchdogConfig):
        self.command = command
        self.config = config
        self.process: Optional[ptyprocess.PtyProcessUnicode] = None
        self.running = False
        self.last_output_time = 0.0
        self.auto_continue_count = 0
        self.compiled_patterns: List[Pattern] = []
        self._debounce_until: float = (
            0.0  # Timestamp until which to ignore pattern matches
        )

        self._setup_logging()
        self._compile_patterns()

    def _setup_logging(self):
        """Configure logging."""
        log_level = logging.INFO
        if self.config.log_file:
            logging.basicConfig(
                filename=self.config.log_file,
                level=log_level,
                format="%(asctime)s - %(levelname)s - %(message)s",
            )
        else:
            logging.basicConfig(level=log_level)

    def _compile_patterns(self):
        """Compile regex patterns for matching continue prompts."""
        for pattern in self.config.continue_patterns:
            # Case insensitive, multiline
            self.compiled_patterns.append(
                re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            )

    def _match_pattern(self, text: str) -> bool:
        """Check if text matches any continue pattern."""
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                return True
        return False

    def _cleanup(self):
        """Cleanup on exit."""
        if self.process and self.process.isalive():
            logger.info("Terminating agent process...")
            try:
                self.process.terminate()
                time.sleep(0.5)
                if self.process.isalive():
                    self.process.kill()
            except Exception as e:
                logger.error(f"Error terminating process: {e}")

    def _signal_handler(self, signum, frame):
        """Handle termination signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        self._cleanup()
        sys.exit(0)

    def run(self):
        """Main watchdog loop."""
        if not HAS_PTYPROCESS:
            raise RuntimeError(
                "ptyprocess is required. Install with: pip install ptyprocess"
            )

        logger.info(f"Starting agent: {' '.join(self.command)}")
        logger.info(f"Watching for patterns: {self.config.continue_patterns}")

        # Register cleanup handlers
        atexit.register(self._cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            # Start the process in a PTY
            self.process = ptyprocess.PtyProcessUnicode.spawn(self.command, echo=True)
            self.running = True
            self.last_output_time = time.time()

            # Main monitoring loop
            buffer = ""

            while self.running and self.process.isalive():
                try:
                    # Check if we're in a debounce period
                    current_time = time.time()
                    if self._debounce_until > 0:
                        if current_time < self._debounce_until:
                            # Still in debounce period - read but don't pattern match
                            # Still need to read to prevent buffer overflow
                            try:
                                chunk = self.process.read(1024, timeout=0.1)
                                if chunk:
                                    buffer += chunk
                                    self.last_output_time = time.time()
                                    if self.config.echo:
                                        sys.stdout.write(chunk)
                                        sys.stdout.flush()
                            except ptyprocess.ptyprocess.TimeoutExpectation:
                                pass
                            except Exception as e:
                                logger.error(f"Error reading from process: {e}")
                                break
                            # Skip pattern matching during debounce
                            continue
                        else:
                            # Debounce period ended - clear buffer and reset
                            logger.debug("Debounce period ended, clearing buffer")
                            buffer = ""
                            self._debounce_until = 0.0

                    # Check if there's output to read
                    if self.process.isalive():
                        # Read available output with timeout
                            try:
                                chunk = self.process.read(1024, timeout=0.1)
                                if chunk:
                                    buffer += chunk
                                    self.last_output_time = time.time()

                                    # Enforce maximum buffer size
                                    if len(buffer) > self.config.max_buffer_size:
                                        buffer = buffer[-self.config.max_buffer_size:]

                                    # Echo to stdout if needed
                                    if self.config.echo:
                                        sys.stdout.write(chunk)
                                        sys.stdout.flush()

                                    # Check for continue prompts
                                    if self._match_pattern(buffer):
                                        logger.info("Continue prompt detected")
                                        self._handle_continue_prompt()
                                        buffer = ""  # Clear buffer after handling
                            except ptyprocess.ptyprocess.TimeoutExpectation:
                                # No data available, continue checking
                                pass
                            except Exception as e:
                                logger.error(f"Error reading from process: {e}")
                                break

                    # Check for inactivity timeout
                    if self.config.inactivity_timeout > 0:
                        idle_time = time.time() - self.last_output_time
                        if idle_time > self.config.inactivity_timeout:
                            logger.warning(
                                f"No output for {idle_time:.1f}s, agent may be stuck"
                            )
                            # Try to send newline to wake it up
                            self._send_input("\n")
                            time.sleep(self.config.debounce_period)

                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received")
                    self.running = False
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in watchdog loop: {e}")
                    break

        finally:
            self._cleanup()
            atexit.unregister(self._cleanup)

    def _handle_continue_prompt(self):
        """Handle detected continue prompt."""
        # Check if we've exceeded auto-continue limit
        if (
            self.config.max_auto_continues > 0
            and self.auto_continue_count >= self.config.max_auto_continues
        ):
            logger.error(
                f"Exceeded maximum auto-continues ({self.config.max_auto_continues}). "
                "Manual intervention required."
            )
            self.running = False
            return

        self.auto_continue_count += 1
        logger.info(f"Sending 'continue' (count: {self.auto_continue_count})")

        # Send the continue command
        self._send_input("continue\n")

        # Set debounce period - ignore further pattern matches for this duration
        self._debounce_until = time.time() + self.config.debounce_period

    def _send_input(self, text: str):
        """Send input to the agent process."""
        try:
            if self.process and self.process.isalive():
                self.process.write(text)
                logger.debug(f"Sent: {text.strip()}")
        except Exception as e:
            logger.error(f"Error sending input: {e}")


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Watchdog utility for monitoring agent terminals. "
        "Automatically sends 'continue' when the agent pauses."
    )
    parser.add_argument(
        "command",
        nargs="+",
        help='Agent command to run (e.g., "python agent.py" or just "agent")',
    )
    parser.add_argument(
        "--patterns",
        "-p",
        nargs="+",
        default=[
            r"type\s+['\"]continue['\"]",  # type 'continue' or type "continue"
            r"press\s+.*\bcontinue\b",    # press any key to continue
            r"enter\s+.*\bcontinue\b",    # press enter to continue
            r"\bcontinue\b.*to\s+proceed",# continue to proceed
            r"\[.*\bcontinue\b.*\]",      # [continue] or [press continue]
            r"\bstopped\b",                # stopped (whole word)
            r"\bpaused\b",                 # paused (whole word)
            r"Completed in \d+m \d+s",    # Completed in Xm Ys
        ],
        help="Regex patterns to match continue prompts",
    )
    parser.add_argument(
        "--inactivity-timeout",
        type=float,
        default=30.0,
        help="Seconds of no output before considering agent stuck (0 to disable)",
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=2.0,
        help="Wait time after sending continue before checking again",
    )
    parser.add_argument(
        "--max-auto-continues",
        type=int,
        default=100,
        help="Maximum consecutive auto-continues before stopping (0 for unlimited)",
    )
    parser.add_argument(
        "--max-buffer-size",
        type=int,
        default=8192,
        help="Maximum output buffer size in characters (default: 8192)",
    )
    parser.add_argument("--log-file", "-l", type=str, help="Path to log file")
    parser.add_argument(
        "--no-echo", action="store_true", help="Don't echo agent output to stdout"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create configuration
    config = WatchdogConfig(
        continue_patterns=args.patterns,
        inactivity_timeout=args.inactivity_timeout,
        debounce_period=args.debounce,
        max_auto_continues=args.max_auto_continues,
        max_buffer_size=args.max_buffer_size,
        log_file=args.log_file,
        echo=not args.no_echo,
    )

    # Create and run watchdog
    watchdog = AgentWatchdog(args.command, config)

    try:
        watchdog.run()
    except KeyboardInterrupt:
        print("\nWatchdog stopped by user")
    except Exception as e:
        logger.error(f"Watchdog failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
