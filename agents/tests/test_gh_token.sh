#!/usr/bin/env bash
# Tests for agents/agents-cli GitHub remote-URL credential parsing.
#
# The host's gh auth (~/.config/gh) is intentionally NOT mounted into the
# container, so agents-cli extracts an embedded token from the git remote URL.
# These tests cover the three handled URL shapes.
#
# Run:  bash agents/tests/test_gh_token.sh
#
# Exits non-zero on any failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI="$SCRIPT_DIR/../agents-cli"

PASS=0
FAIL=0

run_case() {
    local name="$1" expected="$2" url="$3"
    # agents-cli __parse_only__ <url>  ->  "token|host"
    local out
    out="$("$CLI" __parse_only__ "$url" 2>/dev/null)"
    if [[ "$out" == "$expected" ]]; then
        PASS=$((PASS+1))
        # printf '.' >&2  # quiet on success
    else
        FAIL=$((FAIL+1))
        printf 'FAIL: %s\n  url:      %s\n  expected: %s\n  got:      %s\n' \
            "$name" "$url" "$expected" "$out" >&2
    fi
}

# 1) HTTPS with embedded credential: token between ':' and '@'
run_case "https-with-token" \
    "shh_token_abc|github.com" \
    "https://oauth2:shh_token_abc@github.com/owner/repo.git"

# 2) SSH remote: no token, host only
run_case "ssh-remote" \
    "|github.com" \
    "git@github.com:owner/repo.git"

# 3) Plain HTTPS URL (no credential): no token, host only
run_case "plain-https" \
    "|github.com" \
    "https://github.com/owner/repo.git"

# 4) SSH to a non-github host (host extracted, no token)
run_case "ssh-other-host" \
    "|gitlab.com" \
    "git@gitlab.com:owner/repo.git"

# 5) HTTPS with token on a different host
run_case "https-token-other-host" \
    "tok123|gitlab.example.com" \
    "https://user:tok123@gitlab.example.com/owner/repo"

# ── log() must write only to stderr (so stdout stays clean for data) ───────────
# Guards the stdout-pollution bug from 1301f5d (log() wrote to stdout,
# breaking the __parse_only__ data contract).
run_log_stderr_test() {
    # Use an SSH remote: parse_github_remote_url() calls log() for this branch
    # (the HTTPS-with-token branch does not), so this proves log() goes to
    # stderr and that the log line never leaks onto stdout.
    local url="git@github.com:owner/repo.git"
    local out err
    out="$(bash agents/agents-cli __parse_only__ "$url" 2>/tmp/logerr_$$)" || true
    err="$(cat /tmp/logerr_$$)"
    rm -f /tmp/logerr_$$
    # stdout must be EXACTLY the data line — no log() output leaked onto stdout.
    if [[ "$out" != "|github.com" ]]; then
        printf 'FAIL: log-stderr stdout\n  expected "|github.com", got: %s\n' "$out" >&2
        FAIL=$((FAIL+1))
        return
    fi
    # stderr should carry the log line (proves log() goes to stderr, not stdout).
    if [[ -z "$err" ]]; then
        printf 'FAIL: log-stderr stderr\n  expected a log line on stderr, got empty\n' >&2
        FAIL=$((FAIL+1))
        return
    fi
    PASS=$((PASS+1))
}
run_log_stderr_test

# ── HTTPS-with-token: stdout clean, no log() emitted for this branch ─────────
# The original bug (log() on stdout) would have contaminated the data line
# here too; assert stdout is exactly the data line and stderr is empty, so
# the contract is pinned per-branch rather than only for the SSH branch.
run_https_token_stdout_test() {
    local url="https://oauth2:abc123def456@github.com/owner/repo.git"
    local out err
    out="$(bash agents/agents-cli __parse_only__ "$url" 2>/tmp/logerr_$$)" || true
    err="$(cat /tmp/logerr_$$)"
    rm -f /tmp/logerr_$$
    if [[ "$out" != "abc123def456|github.com" ]]; then
        printf 'FAIL: https-token stdout\n  expected "abc123def456|github.com", got: %s\n' "$out" >&2
        FAIL=$((FAIL+1))
        return
    fi
    # HTTPS-with-token branch does not call log(), so stderr must be empty.
    if [[ -n "$err" ]]; then
        printf 'FAIL: https-token stderr\n  expected empty stderr, got: %s\n' "$err" >&2
        FAIL=$((FAIL+1))
        return
    fi
    PASS=$((PASS+1))
}
run_https_token_stdout_test

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
exit "$([ "$FAIL" -eq 0 ] && echo 0 || echo 1)"
