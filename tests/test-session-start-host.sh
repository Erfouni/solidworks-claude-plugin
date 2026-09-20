#!/usr/bin/env bash
# Asserts the SessionStart hook honours the SW_KB_HOST user config.
#
# Claude Code exports plugin userConfig values to hook processes as
# CLAUDE_PLUGIN_OPTION_<KEY>. A hook that reads only $SW_KB_HOST silently keeps
# the built-in default, so a self-hoster's session feedback -- macros included --
# would still be sent to the public server.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="${REPO_ROOT}/hooks/session-start"
DEFAULT_HOST="https://sw-plugin.ideep.org"

failures=0

run_hook() {
    # Args: VAR=value ...  Runs the hook with a clean slate for both host vars.
    env -u SW_KB_HOST -u CLAUDE_PLUGIN_OPTION_SW_KB_HOST \
        CLAUDE_PLUGIN_ROOT="$REPO_ROOT" "$@" bash "$HOOK" 2>/dev/null
}

check() {
    local name="$1" output="$2" expected="$3" unexpected="${4:-}"
    if ! printf '%s' "$output" | grep -qF -- "$expected"; then
        printf 'FAIL: %s\n  expected to find: %s\n' "$name" "$expected" >&2
        failures=$((failures + 1))
        return
    fi
    if [ -n "$unexpected" ] && printf '%s' "$output" | grep -qF -- "$unexpected"; then
        printf 'FAIL: %s\n  should not contain: %s\n' "$name" "$unexpected" >&2
        failures=$((failures + 1))
        return
    fi
    printf 'ok: %s\n' "$name"
}

CONFIGURED="https://kb.example.test"

# 1. The variable Claude Code actually exports must win.
out=$(run_hook CLAUDE_PLUGIN_OPTION_SW_KB_HOST="$CONFIGURED")
check "CLAUDE_PLUGIN_OPTION_SW_KB_HOST is honoured" "$out" "KB: ${CONFIGURED}" "$DEFAULT_HOST"

# 2. The feedback endpoint the model is told to POST to must follow it too --
#    this is the one that carries session content off the machine.
check "feedback endpoint follows the configured host" "$out" \
    "POST to ${CONFIGURED}/api/feedback" "${DEFAULT_HOST}/api/feedback"

# 3. A plain exported SW_KB_HOST keeps working.
out=$(run_hook SW_KB_HOST="$CONFIGURED")
check "plain SW_KB_HOST still honoured" "$out" "KB: ${CONFIGURED}" "$DEFAULT_HOST"

# 4. The exported option takes precedence over a stale shell variable.
out=$(run_hook SW_KB_HOST="https://stale.example.test" \
               CLAUDE_PLUGIN_OPTION_SW_KB_HOST="$CONFIGURED")
check "exported option beats a stale SW_KB_HOST" "$out" "KB: ${CONFIGURED}" "stale.example.test"

# 5. With nothing configured, the public default still applies.
out=$(run_hook)
check "default host when nothing is configured" "$out" "KB: ${DEFAULT_HOST}"

# 6. The hook must still emit valid JSON in the Claude Code shape.
out=$(run_hook CLAUDE_PLUGIN_OPTION_SW_KB_HOST="$CONFIGURED")
if printf '%s' "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["hookSpecificOutput"]["hookEventName"]=="SessionStart"; assert d["hookSpecificOutput"]["additionalContext"]' 2>/dev/null; then
    printf 'ok: hook emits valid SessionStart JSON\n'
else
    printf 'FAIL: hook did not emit valid SessionStart JSON\n' >&2
    failures=$((failures + 1))
fi

# 7. No skill or agent may hard-code the public host; the documented
#    ${user_config.SW_KB_HOST} substitution is what makes self-hosting work.
hardcoded=$(grep -rln -- "$DEFAULT_HOST" "${REPO_ROOT}/skills" "${REPO_ROOT}/agents" 2>/dev/null || true)
if [ -n "$hardcoded" ]; then
    printf 'FAIL: public host hard-coded in skill/agent content:\n%s\n' "$hardcoded" >&2
    failures=$((failures + 1))
else
    printf 'ok: no hard-coded host in skill/agent content\n'
fi

if [ "$failures" -ne 0 ]; then
    printf '\n%d check(s) failed\n' "$failures" >&2
    exit 1
fi
printf '\nAll checks passed\n'
