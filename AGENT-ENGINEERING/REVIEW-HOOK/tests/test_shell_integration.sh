#!/usr/bin/env bash
set -euo pipefail

review_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=../shell/review-after-commit.bash
source "${review_root}/shell/review-after-commit.bash"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

expect_failure() {
  if "$@" 2>/dev/null; then
    fail "command unexpectedly succeeded: $*"
  fi
}

declare -A selection=()
declare -a forwarded=()

review_after_commit_parse codex selection forwarded --model gpt-test -- foo
[[ "${selection[enabled]}" == "0" ]] || fail "plain launch became active"
[[ "${forwarded[*]}" == "--model gpt-test -- foo" ]] || fail "plain args changed"

review_after_commit_parse codex selection forwarded \
  --review-mode cadence \
  --review-standard-every 2 \
  --review-branch-every=6 \
  --model gpt-test
[[ "${selection[enabled]}" == "1" ]] || fail "cadence was not enabled"
[[ "${selection[mode]}" == "cadence" ]] || fail "wrong cadence mode"
[[ "${selection[standard_every]}" == "2" ]] || fail "wrong standard interval"
[[ "${selection[branch_every]}" == "6" ]] || fail "wrong branch interval"
[[ "${forwarded[*]}" == "--model gpt-test" ]] || fail "review args leaked"

review_after_commit_parse kimi selection forwarded \
  --hook review-after-commit \
  --hook-option branch-every=5 \
  --yolo
[[ "${selection[mode]}" == "cadence" ]] || fail "legacy spelling changed mode"
[[ "${selection[branch_every]}" == "5" ]] || fail "legacy interval changed"
[[ "${forwarded[*]}" == "--yolo" ]] || fail "legacy parsing changed args"

expect_failure review_after_commit_parse codex selection forwarded \
  --review-mode cadence --review-mode auto
expect_failure review_after_commit_parse codex selection forwarded \
  --review-mode auto --review-standard-every 2
expect_failure review_after_commit_parse codex selection forwarded \
  --review-mode calibrate
expect_failure review_after_commit_parse codex selection forwarded \
  --review-mode= --model gpt-test
expect_failure review_after_commit_parse codex selection forwarded \
  --review-standard-every 2
expect_failure review_after_commit_parse codex selection forwarded \
  --review-mode cadence --profile another
expect_failure review_after_commit_parse kimi selection forwarded \
  --review-mode cadence --prompt hello

review_after_commit_parse codex selection forwarded -- --review-mode auto
[[ "${selection[enabled]}" == "0" ]] || fail "arguments after -- activated review"
[[ "${forwarded[*]}" == "-- --review-mode auto" ]] || fail "-- boundary changed"

review_after_commit_parse codex selection forwarded \
  --review-mode cadence --review-standard-every 3 --review-branch-every 9
selected_home="${TMPDIR:-/tmp}/review-hook-shell-test-home"
export KIMI_HOOK_REVIEW_AFTER_COMMIT_ENABLED=1
review_after_commit_export_environment codex "$selected_home" selection
[[ "$REVIEW_AFTER_COMMIT_MODE" == "cadence" ]] || fail "mode export missing"
[[ "$CODEX_HOOK_STATE_DIR" == "${selected_home}/hook-state/review-after-commit" ]] || fail "Codex state root changed"
[[ "$CODEX_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY" == "3" ]] || fail "standard export missing"
[[ "$CODEX_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY" == "9" ]] || fail "branch export missing"
[[ -z "${KIMI_HOOK_REVIEW_AFTER_COMMIT_ENABLED:-}" ]] || fail "foreign host env survived"

review_after_commit_parse kimi selection forwarded --review-mode cadence
review_after_commit_export_environment kimi "$selected_home" selection
[[ "$KIMI_HOOK_REVIEW_AFTER_COMMIT_ENABLED" == "1" ]] || fail "Kimi enable missing"
[[ "$KIMI_HOOK_STATE_DIR" == "${selected_home}/hook-state/review-after-commit" ]] || fail "Kimi state root changed"
[[ -z "${CODEX_HOOK_STATE_DIR:-}" ]] || fail "foreign Codex env survived"

review_after_commit_parse codex selection forwarded --review-mode auto
review_after_commit_export_environment codex "$selected_home" selection
[[ "$REVIEW_AFTER_COMMIT_MODE" == "auto" ]] || fail "auto mode export missing"
[[ -z "${CODEX_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY:-}" ]] || fail "auto inherited a standard interval"
[[ -z "${CODEX_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY:-}" ]] || fail "auto inherited a branch interval"

review_after_commit_parse antigravity selection forwarded --review-mode cadence
review_after_commit_export_environment antigravity "$selected_home" selection
[[ "$ANTIGRAVITY_HOOK_STATE_DIR" == "${selected_home}/hook-state/review-after-commit" ]] || fail "Antigravity state root changed"
[[ "$REVIEW_AFTER_COMMIT_MODE" == "cadence" ]] || fail "Antigravity mode export missing"
[[ -z "${CODEX_HOOK_STATE_DIR:-}" && -z "${KIMI_HOOK_STATE_DIR:-}" ]] || fail "foreign host env survived"

canonical_home="${TMPDIR:-/tmp}/review-hook-canonical"
bundle=$(review_after_commit_dispatch bundle-path codex "$canonical_home")
[[ "$bundle" == "${canonical_home}/hooks/review-after-commit" ]] || fail "bundle path changed"
bundle=$(review_after_commit_dispatch bundle-path antigravity "$canonical_home")
[[ "$bundle" == "${canonical_home}/plugins/review-after-commit" ]] || fail "Antigravity bundle path changed"

kimi_config=$(review_after_commit_dispatch append-kimi-config)
[[ "$kimi_config" == *'event = "PreToolUse"'* ]] || fail "Kimi PreToolUse config missing"
[[ "$kimi_config" == *'event = "Stop"'* ]] || fail "Kimi Stop config missing"
[[ "$kimi_config" == *'/usr/bin/python3 -B'* ]] || fail "Kimi bytecode suppression missing"
[[ "$kimi_config" == *'hosts/kimi/adapter.py'* ]] || fail "Kimi adapter path changed"
[[ "$kimi_config" != *'kimi_hook.py'* ]] || fail "legacy Kimi adapter path survived"

printf 'review-after-commit shell integration: ok\n'
