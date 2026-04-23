#!/usr/bin/env python3
"""Agent Watchdog - Uses tmux monitoring to auto-send 'continue' when agents pause."""

from __future__ import annotations

import os
import sys
import re
import time
import signal
import logging
import atexit
import subprocess
import tempfile
from typing import Optional, Pattern, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WatchdogConfig:
    """Configuration for the tmux-based watchdog utility."""

    # Silence timeout in seconds - alert after this many seconds of no activity
    silence_timeout: int = 30
    # Maximum consecutive auto-continues before stopping
    max_auto_continues: int = 10
    # Log file path
    log_file: Optional[str] = None


class AgentWatchdog:
    """Uses tmux monitoring to auto-send 'continue' when agents pause."""

    def __init__(self, command: List[str], config: WatchdogConfig):
        self.command = command
        self.config = config
        self.session_name = f"watchdog-{os.getpid()}"
        self.auto_continue_count = 0
        self.running = False

        self._setup_logging()

    def _setup_logging(self):
        """Configure logging."""
        log_level = logging.INFO
        if self.config.log_file:
            # Log to file
            logging.basicConfig(
                level=log_level,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                filename=self.config.log_file,
                filemode='a'
            )
        else:
            # Log to console
            logging.basicConfig(
                level=log_level,
                format='%(asctime)s - %(name)s - %(levelname)s'
            )

    def _run_tmux_command(self, args: List[str]) -> subprocess.CompletedProcess:
        """Run a tmux command and return the result."""
        cmd = ['tmux'] + args
        logger.debug(f"Running: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True)

    def _create_tmux_session(self):
        """Create a new tmux session with the agent command."""
        # Create the session in detached mode
        result = self._run_tmux_command([
            'new-session', '-d', '-s', self.session_name,
            ' '.join(self.command)
        ])

        if result.returncode != 0:
            raise RuntimeError(f"Failed to create tmux session: {result.stderr}")

        logger.info(f"Created tmux session '{self.session_name}' with agent: {' '.join(self.command)}")

    def _configure_tmux_monitoring(self):
        """Configure tmux silence monitoring and hooks."""
        # Set silence monitoring timeout
        result = self._run_tmux_command([
            'set-option', '-t', self.session_name, 'monitor-silence', str(self.config.silence_timeout)
        ])
        if result.returncode != 0:
            logger.warning(f"Failed to set silence monitoring: {result.stderr}")

        # Set hook to send "continue" when silence alert triggers
        result = self._run_tmux_command([
            'set-hook', '-t', self.session_name, 'alert-silence',
            'send-keys "continue" Enter'
        ])
        if result.returncode != 0:
            logger.warning(f"Failed to set alert-silence hook: {result.stderr}")

        logger.info(f"Configured silence monitoring ({self.config.silence_timeout}s) with auto-continue hook")

    def _attach_tmux_session(self):
        """Attach to the tmux session."""
        logger.info("Attaching to tmux session (Ctrl+B D to detach, Ctrl+C to exit)")

        # Attach to the session
        result = self._run_tmux_command(['attach-session', '-t', self.session_name])

        # This will block until the user detaches or the session ends
        if result.returncode != 0:
            logger.error(f"Failed to attach to tmux session: {result.stderr}")

    def _cleanup(self):
        """Cleanup tmux session."""
        if hasattr(self, 'session_name'):
            logger.info(f"Cleaning up tmux session '{self.session_name}'")
            result = self._run_tmux_command(['kill-session', '-t', self.session_name])
            if result.returncode != 0:
                logger.warning(f"Failed to kill tmux session: {result.stderr}")

    def run(self):
        """Main watchdog loop using tmux monitoring."""
        logger.info(f"Starting agent with tmux monitoring: {' '.join(self.command)}")
        logger.info(f"Silence timeout: {self.config.silence_timeout}s")

        # Register cleanup handlers
        atexit.register(self._cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            # Create tmux session with the agent
            self._create_tmux_session()

            # Configure tmux monitoring
            self._configure_tmux_monitoring()

            # Attach to the tmux session (this blocks until user exits)
            self._attach_tmux_session()

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

    parser = argparse.ArgumentParser(description="Tmux-based agent watchdog")
    parser.add_argument("command", nargs="+", help="Agent command to run")
    parser.add_argument("--silence-timeout", type=int, default=30,
                       help="Silence timeout in seconds (default: 30)")
    parser.add_argument("--max-auto-continues", type=int, default=10,
                       help="Maximum auto-continues before stopping (default: 10)")
    parser.add_argument("--log-file", help="Log file path")

    args = parser.parse_args()

    config = WatchdogConfig(
        silence_timeout=args.silence_timeout,
        max_auto_continues=args.max_auto_continues,
        log_file=args.log_file
    )

    watchdog = AgentWatchdog(args.command, config)
    watchdog.run()


if __name__ == "__main__":
    main()
