#!/usr/bin/env bash

set -euo pipefail

script_dir="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
launcher="$script_dir/xgrok"
skill_file="$(dirname -- "$script_dir")/SKILL.md"
playbook_file="$(dirname -- "$script_dir")/references/query-playbook.md"
regression_file="$(dirname -- "$script_dir")/references/synthesis-regressions.md"
protocol_file="$(dirname -- "$script_dir")/references/worker-protocol.md"
tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/test-xgrok.XXXXXX")"
fake_bin="$tmp_root/bin"
capture_file="$tmp_root/capture.txt"
prompt_capture="$tmp_root/prompt.md"
expected_prompt="$tmp_root/expected-prompt.md"
brief_file="$tmp_root/brief.md"
mkdir "$fake_bin"
# Hermetic account home: the launcher looks for a worker login at $GROK_HOME-xworker.
export GROK_HOME="$tmp_root/grok-home"

cleanup() {
  rm -f -- "$fake_bin/grok" "$capture_file" "$capture_file.env" "$prompt_capture" "$expected_prompt" "$brief_file"
  rm -rf -- "$tmp_root/grok-home-xworker" "$tmp_root/grok-home" "$tmp_root/stderr.txt"
  rm -rf -- "$tmp_root/wave-test"
  rmdir -- "$fake_bin" "$tmp_root" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

assert_file_prefix() {
  local expected_file="$1"
  local actual_file="$2"
  local expected_bytes
  expected_bytes="$(wc -c <"$expected_file" | tr -d '[:space:]')"
  cmp -s "$expected_file" <(head -c "$expected_bytes" "$actual_file")
}

assert_file_suffix() {
  local expected_file="$1"
  local actual_file="$2"
  local expected_bytes
  expected_bytes="$(wc -c <"$expected_file" | tr -d '[:space:]')"
  cmp -s "$expected_file" <(tail -c "$expected_bytes" "$actual_file")
}

assert_contains_file() {
  local expected_file="$1"
  local actual_file="$2"
  local expected actual
  expected="$(<"$expected_file")"
  actual="$(<"$actual_file")"
  [[ "$actual" == *"$expected"* ]]
}

cat >"$fake_bin/grok" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

prompt_file=""
printf '%s\n' "$@" >"$XGROK_TEST_CAPTURE"
env | grep -E '^(HOME|GROK_HOME|GROK_CLAUDE_SKILLS_ENABLED|GROK_CURSOR_MCPS_ENABLED)=' \
  | sort >"$XGROK_TEST_CAPTURE.env"
while (($#)); do
  if [[ "$1" == "--prompt-file" ]]; then
    prompt_file="$2"
    break
  fi
  shift
done

test -n "$prompt_file"
cp -- "$prompt_file" "$XGROK_TEST_PROMPT_CAPTURE"
printf '%s\n' '{"text":"stub result","stopReason":"EndTurn"}'
EOF
chmod +x "$fake_bin/grok"

for prose_file in "$skill_file" "$playbook_file" "$regression_file" "$protocol_file"; do
  if [[ ! -s "$prose_file" ]]; then
    printf 'required prose asset is missing or empty: %s\n' "$prose_file" >&2
    exit 1
  fi
done

printf '%s\n' 'unique harvest brief fixture' >"$brief_file"

PATH="$fake_bin:$PATH" \
  XGROK_TEST_CAPTURE="$capture_file" \
  XGROK_TEST_PROMPT_CAPTURE="$prompt_capture" \
  "$launcher" --mode harvest "$brief_file" >/dev/null

grep -Fqx -- "--model" "$capture_file"
grep -Fqx -- "grok-4.7" "$capture_file"
grep -A1 -Fx -- "--effort" "$capture_file" | grep -Fqx -- "medium"
grep -Fqx -- "--verbatim" "$capture_file"
grep -Fqx -- "--disable-web-search" "$capture_file"
grep -Fq -- "run_terminal_cmd,read_file,list_dir,grep,search_replace,write,web_search,web_fetch,kill_command_or_subagent," "$capture_file"
grep -Fq -- ",image_gen,image_edit,image_to_video,reference_to_video" "$capture_file"
grep -Fqx -- "--no-plan" "$capture_file"
worker_dir="${TMPDIR:-/tmp}/xgrok-worker-home"
grep -A1 -Fx -- "--cwd" "$capture_file" | grep -Fqx -- "$worker_dir"
grep -Fqx -- "HOME=$worker_dir" "$capture_file.env"
grep -Fqx -- "GROK_HOME=$GROK_HOME" "$capture_file.env"
grep -Fqx -- "GROK_CLAUDE_SKILLS_ENABLED=false" "$capture_file.env"
grep -Fqx -- "GROK_CURSOR_MCPS_ENABLED=false" "$capture_file.env"
if grep -Fqx -- "--system-prompt-override" "$capture_file"; then
  echo "system prompt override must be opt-in" >&2
  exit 1
fi

PATH="$fake_bin:$PATH" XGROK_TEST_CAPTURE="$capture_file" XGROK_TEST_PROMPT_CAPTURE="$prompt_capture" \
  XGROK_EFFORT=medium XGROK_MODEL=grok-4.6 XGROK_SYSTEM_PROMPT=lean "$launcher" "$brief_file" >/dev/null
grep -A1 -Fx -- "--effort" "$capture_file" | grep -Fqx -- "medium"
grep -A1 -Fx -- "--model" "$capture_file" | grep -Fqx -- "grok-4.6"
grep -Fqx -- "--system-prompt-override" "$capture_file"
grep -Fq -- "X-retrieval worker" "$capture_file"
# Low effort is refused: at low effort workers answered without searching.
for bad in "XGROK_EFFORT=max" "XGROK_EFFORT=low" "XGROK_SYSTEM_PROMPT=short"; do
  if env "$bad" PATH="$fake_bin:$PATH" "$launcher" "$brief_file" >/dev/null 2>&1; then
    echo "expected $bad to fail" >&2
    exit 1
  fi
done

# A worker home is used only once it holds a login to the account's own xAI user;
# setup never overwrites its config.
PATH="$fake_bin:$PATH" "$launcher" --setup-worker-home 2>/dev/null
worker_home="$GROK_HOME-xworker"
grep -Fq -- "ignore = [\"$worker_home/bundled\"]" "$worker_home/config.toml"
[[ "$(readlink "$worker_home/skills")" == "$GROK_HOME/skills" ]]
printf '# edited\n' >>"$worker_home/config.toml"
PATH="$fake_bin:$PATH" "$launcher" --setup-worker-home 2>/dev/null
tail -n 1 "$worker_home/config.toml" | grep -Fqx -- "# edited"
run_worker() {
  PATH="$fake_bin:$PATH" XGROK_TEST_CAPTURE="$capture_file" XGROK_TEST_PROMPT_CAPTURE="$prompt_capture" \
    "$launcher" "$brief_file" >/dev/null 2>"$tmp_root/stderr.txt"
}
login_as() {  # login_as HOME USER_ID
  printf '{"https://auth.x.ai::team": {"user_id": "%s", "key": "secret-token-value"}}\n' "$2" >"$1/auth.json"
}
run_worker
grep -Fqx -- "GROK_HOME=$GROK_HOME" "$capture_file.env"
mkdir -p "$GROK_HOME"
login_as "$GROK_HOME" user-a
login_as "$worker_home" user-a
run_worker
grep -Fqx -- "GROK_HOME=$worker_home" "$capture_file.env"
PATH="$fake_bin:$PATH" "$launcher" --setup-worker-home 2>/dev/null
XGROK_NO_WORKER_HOME=1 run_worker
grep -Fqx -- "GROK_HOME=$GROK_HOME" "$capture_file.env"
grep -Fq -- "XGROK_NO_WORKER_HOME=1" "$tmp_root/stderr.txt"
if XGROK_NO_WORKER_HOME=yes run_worker; then
  echo "expected XGROK_NO_WORKER_HOME=yes to fail" >&2
  exit 1
fi
# A worker home logged in as another user is refused, loudly, and no token is printed.
login_as "$worker_home" user-b
run_worker
grep -Fqx -- "GROK_HOME=$GROK_HOME" "$capture_file.env"
grep -Fq -- "WARNING $worker_home is logged in as a different xAI user" "$tmp_root/stderr.txt"
if PATH="$fake_bin:$PATH" "$launcher" --setup-worker-home 2>"$tmp_root/stderr.txt"; then
  echo "expected --setup-worker-home to reject a different user's login" >&2
  exit 1
fi
if grep -Fq -- "secret-token-value" "$tmp_root/stderr.txt" || grep -Fq -- "user-b" "$tmp_root/stderr.txt"; then
  echo "the login check must not print auth.json contents" >&2
  exit 1
fi
rm -f -- "$worker_home/auth.json" "$GROK_HOME/auth.json"
grep -Fqx -- "Bash" "$capture_file"
assert_file_prefix "$protocol_file" "$prompt_capture"
assert_contains_file "$brief_file" "$prompt_capture"

# Exceed Grok Build's offload threshold and preserve the entire composed prompt.
awk 'BEGIN {
  for (i = 1; i <= 1000; i++)
    printf "roster-%04d: alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron\n", i
}' >"$brief_file"
{
  cat "$protocol_file"
  printf '\n\n# Delegated retrieval brief\n\n'
  cat "$brief_file"
} >"$expected_prompt"
[[ "$(wc -c <"$expected_prompt")" -gt 84272 ]]

for input_kind in file stdin; do
  if [[ "$input_kind" == "file" ]]; then
    PATH="$fake_bin:$PATH" \
      XGROK_TEST_CAPTURE="$capture_file" \
      XGROK_TEST_PROMPT_CAPTURE="$prompt_capture" \
      "$launcher" "$brief_file" >/dev/null
  else
    PATH="$fake_bin:$PATH" \
      XGROK_TEST_CAPTURE="$capture_file" \
      XGROK_TEST_PROMPT_CAPTURE="$prompt_capture" \
      "$launcher" <"$brief_file" >/dev/null
  fi
  grep -Fqx -- "--verbatim" "$capture_file"
  cmp "$expected_prompt" "$prompt_capture"
done

for mode in whathappened list-summary macro dlresearch agents; do
  printf '%s\n' "unique $mode brief fixture" >"$brief_file"
  PATH="$fake_bin:$PATH" \
    XGROK_TEST_CAPTURE="$capture_file" \
    XGROK_TEST_PROMPT_CAPTURE="$prompt_capture" \
    "$launcher" --mode "$mode" "$brief_file" >/dev/null

  [[ "$(head -n 1 "$prompt_capture")" == "/$mode" ]]
  grep -Fqx -- "--verbatim" "$capture_file"
  grep -Fq -- "run_terminal_cmd,search_replace,write,web_search,web_fetch,kill_command_or_subagent," "$capture_file"
  assert_contains_file "$brief_file" "$prompt_capture"
  assert_file_suffix "$protocol_file" "$prompt_capture"
done

if PATH="$fake_bin:$PATH" "$launcher" --mode invalid </dev/null >/dev/null 2>&1; then
  echo "expected invalid mode to fail" >&2
  exit 1
fi

if PATH="$fake_bin:$PATH" "$launcher" </dev/null >/dev/null 2>&1; then
  echo "expected empty brief to fail" >&2
  exit 1
fi

wave_script="$script_dir/xgrok_wave.py"
if [[ ! -x "$wave_script" ]]; then
  echo "xgrok_wave.py is not executable" >&2
  exit 1
fi

wave_test_dir="$tmp_root/wave-test"
mkdir -p "$wave_test_dir/briefs"
cat >"$wave_test_dir/briefs/01-harvest.md" <<'EOF'
# Harvest Brief 1
Objective: Test harvest brief execution
EOF

cat >"$wave_test_dir/briefs/02-macro.md" <<'EOF'
---
mode: macro
---
# Macro Brief 2
Objective: Test macro brief execution
Delegated budget: the parent expands the /macro default to 20 receipts / 4,000 words.
EOF

wave_out="$wave_test_dir/out"

# Test dry run
PATH="$fake_bin:$PATH" \
  "$wave_script" --briefs-dir "$wave_test_dir/briefs" --output-dir "$wave_out" --dry-run >/dev/null

# A macro-mode brief without a Delegated budget line must be refused before launch.
mkdir -p "$wave_test_dir/bad-macro"
printf '%s\n' '# mode: macro' 'Objective: no budget expansion line' >"$wave_test_dir/bad-macro/03-macro.md"
if PATH="$fake_bin:$PATH" \
  "$wave_script" --briefs-dir "$wave_test_dir/bad-macro" --output-dir "$wave_test_dir/bad-out" --dry-run >/dev/null 2>"$wave_test_dir/bad-macro.err"; then
  echo "expected macro brief without Delegated budget line to fail" >&2
  exit 1
fi
grep -Fq "Delegated budget:" "$wave_test_dir/bad-macro.err"
test ! -e "$wave_test_dir/bad-out"

# A roster-plus-keyword query with more than four from: handles must be refused unless the lint is disabled.
mkdir -p "$wave_test_dir/bad-query"
cat >"$wave_test_dir/bad-query/04-harvest.md" <<'EOF'
Objective: close prints
4. Keyword Latest: `("2-year" OR "10-year") (yield OR yields)` from:FirstSquawk OR from:LiveSquawk OR from:DeItaone OR from:KobeissiLetter OR from:Convertbond OR from:dampedspring.
EOF
if PATH="$fake_bin:$PATH" \
  "$wave_script" --briefs-dir "$wave_test_dir/bad-query" --dry-run >/dev/null 2>"$wave_test_dir/bad-query.err"; then
  echo "expected long roster-plus-keyword query to fail lint" >&2
  exit 1
fi
grep -Fq "6 from: handles combined with keyword terms" "$wave_test_dir/bad-query.err"
PATH="$fake_bin:$PATH" \
  "$wave_script" --briefs-dir "$wave_test_dir/bad-query" --dry-run --no-query-lint >/dev/null

# Test live run with stub grok
PATH="$fake_bin:$PATH" \
  XGROK_TEST_CAPTURE="$capture_file" \
  XGROK_TEST_PROMPT_CAPTURE="$prompt_capture" \
  "$wave_script" --briefs-dir "$wave_test_dir/briefs" --output-dir "$wave_out" --max-workers 2 >/dev/null

test -f "$wave_out/manifest.json"
test -f "$wave_out/01-harvest.log"
test -f "$wave_out/01-harvest-raw.json"
test -f "$wave_out/01-harvest-packet.md"
test -f "$wave_out/02-macro.log"
test -f "$wave_out/02-macro-raw.json"
test -f "$wave_out/02-macro-packet.md"

grep -Fq '"status": "success"' "$wave_out/manifest.json"
grep -Fq '"total_briefs": 2' "$wave_out/manifest.json"
grep -Fq '"succeeded": 2' "$wave_out/manifest.json"
grep -Fq '"common_tail": null' "$wave_out/manifest.json"
grep -Fq 'stub result' "$wave_out/01-harvest-packet.md"

# --common-tail appends the tail to every brief, launches the composed copy, and records the tail hash.
tail_file="$wave_test_dir/common-tail.md"
printf '%s\n' 'Window: 2026-09-21 12:30 PDT through 16:10 PDT.' 'Return: a compact evidence packet.' >"$tail_file"
tail_sha="$(shasum -a 256 "$tail_file" | cut -d' ' -f1)"
wave_out_tail="$wave_test_dir/out-tail"
PATH="$fake_bin:$PATH" \
  XGROK_TEST_CAPTURE="$capture_file" \
  XGROK_TEST_PROMPT_CAPTURE="$prompt_capture" \
  "$wave_script" --briefs-dir "$wave_test_dir/briefs" --output-dir "$wave_out_tail" --common-tail "$tail_file" --max-workers 1 >/dev/null
test -f "$wave_out_tail/composed/01-harvest.md"
assert_file_prefix "$wave_test_dir/briefs/01-harvest.md" "$wave_out_tail/composed/01-harvest.md"
assert_file_suffix "$tail_file" "$wave_out_tail/composed/01-harvest.md"
assert_contains_file "$tail_file" "$prompt_capture"
grep -Fq "\"sha256\": \"$tail_sha\"" "$wave_out_tail/manifest.json"
grep -Fq "composed/02-macro.md" "$wave_out_tail/manifest.json"
grep -Eq "COMMAND: .*composed/01-harvest.md" "$wave_out_tail/01-harvest.log"

python3 "$script_dir/test_xgrok_wave.py" >/dev/null 2>"$wave_test_dir/unit.err" || {
  cat "$wave_test_dir/unit.err" >&2
  exit 1
}

python3 "$script_dir/test_xgrok_usage.py" >/dev/null 2>"$wave_test_dir/usage.err" || {
  cat "$wave_test_dir/usage.err" >&2
  exit 1
}

echo "xgrok launcher, wave, roster, quota, and unit tests passed"
