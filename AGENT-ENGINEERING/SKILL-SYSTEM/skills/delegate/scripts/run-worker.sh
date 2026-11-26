#!/usr/bin/env bash
set -eo pipefail

delegate_worker_usage() {
  printf '%s\n' \
    'Usage: run-worker.sh <launcher> [--task-file PATH]' \
    '' \
    'Reads the task from stdin unless --task-file is provided.' \
    'Supported launchers:' \
    '  agg aggbs aggb aggbbs agom agoh argm argh aghh aghhb aghx aghxb agcm agcmb agch agchb agnm agnmb agnh agnhb agnx agnxb (Antigravity; final-only headless; either account)' \
    '  agg2 aggbs2 aggb2 aggbbs2 agom2 agoh2 argm2 argh2 aghh2 aghhb2 aghx2 aghxb2 agcm2 agcmb2 agch2 agchb2 agnm2 agnmb2 agnh2 agnhb2 agnx2 agnxb2 (Antigravity second account)' \
    '  agk [ag*] agk:<primary-gemini-launcher> (Antigravity GEMINI_API_KEY mode; user-requested only)' \
    '  kimm kimb kimbs (Kimi Code K3.1 Pro; stream-json final text)' \
    '  dglm dswe dargh dopmm doph dopx dopm' \
    '  grok grokxh grok2 grok2xh grok3 grok3xh' \
    '  clm clmb clme clmbe' \
    '  clm2 clmb2 clme2 clmbe2 (Luna secondary account; user-requested only)' \
    '  ctx ctxb ctm ctmb (Terra xhigh/max; -p final-only; user-requested only)' \
    '  ctx2 ctxb2 ctm2 ctmb2 (Terra secondary account; user-requested only)' \
    '  cdx cdxb cdxe cdxbe cdm cdmb cdme cdmbe' \
    '  cdx2 cdxb2 cdxe2 cdxbe2 cdm2 cdmb2 cdme2 cdmbe2 (Sol secondary account; user-requested only)' \
    '  cam camb cax caxb camm cammb cah cahb (Astra; -p final-only)' \
    '  cam2 camb2 cax2 caxb2 camm2 cammb2 cah2 cahb2 (Astra secondary account; -p final-only; user-requested only)' \
    '  cdmM cdxX camM caxX cdmM2 cdxX2 camM2 caxX2 (Codex boost; user-requested only)' \
    '  cdxk [c*] cdxk:<primary-codex-launcher> (OpenAI API-key account; user-requested only)' \
    '  ocs ommp ocargh ochy ocq4h ocq4x ocmm26 ochy4flash oclongcat ociceman (OpenCode; JSON final message; user-requested only)' \
    '  cmg cmds cmm26p cmqh cmqx cms cmhy cmdglyph cmdflint (Command Code; terminal JSON result; user-requested only)' \
    '  cmd:<native-id> (an exact Command Code model through am; user-requested only)' \
    '  pihy4flash pilongcat piiceman (Pi; final assistant text; user-requested only)' \
    '  csm csu csx cshh csmm csbm csbu csbx csbh csbmm (Claude Sonnet; JSON result)' \
    '  chm chu chx chh chmm chbm chbu chbx chbh chbmm (Claude Haiku; JSON result)' \
    '  ccx ccbx ccm ccbm ccmm ccmM ccxX (Claude Opus; JSON result)' \
    '  ccfh ccbfh ccfx ccbfx (Claude Fable; JSON result)' \
    '  cck cckm ccku cckx cckh cckmm cckbm cckbu cckbx cckbh cckbmm (Claude Opus API-key; JSON result; user-requested only)' \
    '  cckfm cckfu cckfx cckfh cckfmm cckbfm cckbfu cckbfx cckbfh cckbfmm (Claude Fable API-key; JSON result; user-requested only)' \
    'Explicit-user routes are documented in SKILL.md; eligibility is not a routing recommendation.'
}

delegate_worker_fail() {
  printf 'delegate worker: %s\n' "$*" >&2
  exit 1
}

launcher="${1:-}"
if [[ "$launcher" == "-h" || "$launcher" == "--help" ]]; then
  delegate_worker_usage
  exit 0
fi
[[ -n "$launcher" ]] || {
  delegate_worker_usage >&2
  delegate_worker_fail 'a launcher name is required'
}
shift

requested_launcher="$launcher"
codex_api=0
if [[ "$launcher" == "cdxk" ]]; then
  codex_api=1
  if (( $# > 0 )) && [[ "$1" != -* ]]; then
    requested_launcher="cdxk:$1"
    shift
  else
    requested_launcher="cdxk:cdx"
  fi
  launcher="${requested_launcher#cdxk:}"
elif [[ "$launcher" == cdxk:* ]]; then
  codex_api=1
  launcher="${launcher#cdxk:}"
fi
if (( codex_api )); then
  case "${requested_launcher#cdxk:}" in
    ctx|ctxb|ctm|ctmb|cdu|cdub|cduf|cdm|cdmM|cdmb|cdmf|cdx|cdxX|cdx-fresh|cdxb|cdxf|cdh|cdhb|cdhf|cdmm|cdmmb|cdxmf|cdxl|clu|club|clm|clmb|clx|clxb|cau|caub|cam|camM|camb|cax|caxX|caxb|cah|cahb|camm|cammb|cdal|cdalb|cdxe|cdxe-fresh|cdme|clme|cdube|cdmbe|clmbe|cdxbe|cdhbe|cdmmbe|cdlbe) ;;
    *) delegate_worker_fail "unsupported cdxk target: $launcher (expected a supported primary Codex launcher)" ;;
  esac
fi
agy_api=0
if [[ "$launcher" == "agk" ]]; then
  agy_api=1
  if (( $# > 0 )) && [[ "$1" != -* ]]; then
    requested_launcher="agk:$1"
    shift
  else
    requested_launcher="agk:aghh"
  fi
  launcher="${requested_launcher#agk:}"
elif [[ "$launcher" == agk:* ]]; then
  agy_api=1
  launcher="${launcher#agk:}"
fi
if (( agy_api )); then
  case "${requested_launcher#agk:}" in
    agg|aggbs|aggb|aggbbs|argm|argh|aghh|aghhb|aghx|aghxb|agcm|agcmb|agch|agchb|agnm|agnmb|agnh|agnhb|agnx|agnxb) ;;
    *) delegate_worker_fail "unsupported agk target: $launcher (expected a supported primary Gemini Antigravity launcher)" ;;
  esac
fi

task_file=""
while (( $# > 0 )); do
  case "$1" in
    --task-file)
      (( $# >= 2 )) || delegate_worker_fail '--task-file requires a path'
      task_file="$2"
      shift 2
      ;;
    -h|--help)
      delegate_worker_usage
      exit 0
      ;;
    *)
      delegate_worker_fail "unknown option: $1"
      ;;
  esac
done

if [[ -n "$task_file" ]]; then
  [[ -f "$task_file" ]] || delegate_worker_fail "task file not found: $task_file"
  prompt="$(<"$task_file")"
elif [[ ! -t 0 ]]; then
  prompt="$(command cat)"
else
  delegate_worker_fail 'task text is required on stdin or through --task-file'
fi
[[ -n "${prompt//[[:space:]]/}" ]] || delegate_worker_fail 'task text must not be empty'

# hist links the worker to the launching session by this line, on every host.
# With both session variables set, or neither, the parent is unknown.
if [[ -n "${CLAUDE_CODE_SESSION_ID:-}" && -z "${CODEX_THREAD_ID:-}" ]]; then
  prompt+=$'\n\n'"[hist-parent claude:${CLAUDE_CODE_SESSION_ID}]"
elif [[ -n "${CODEX_THREAD_ID:-}" && -z "${CLAUDE_CODE_SESSION_ID:-}" ]]; then
  prompt+=$'\n\n'"[hist-parent codex:${CODEX_THREAD_ID}]"
fi

bash_agents_file="${BASH_AGENTS_FILE:-$HOME/.bash_agents}"
[[ -r "$bash_agents_file" ]] || delegate_worker_fail "launcher definitions are not readable: $bash_agents_file"

# shellcheck source=/dev/null
source "$bash_agents_file"

mode=""
resolved_launcher="$launcher"
case "$launcher" in
  agg|aggbs|aggb|aggbbs|agom|agoh|argm|argh|aghh|aghhb|aghx|aghxb|agcm|agcmb|agch|agchb|agnm|agnmb|agnh|agnhb|agnx|agnxb)
    # The shell launchers reconstruct only the terminal completed response
    # from AGY's event stream. Native print/JSON both include progress text.
    mode="antigravity-final"
    if (( ! agy_api )); then
      # A plain name runs on whichever signed-in account has more of its model's quota left.
      agy_account="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/agy-account.py"
      if picked="$(python3 "$agy_account" pick "$launcher")"; then
        resolved_launcher="$picked"
      else
        printf 'delegate worker: could not compare the Antigravity accounts; running %s\n' "$launcher" >&2
      fi
    fi
    ;;
  agg2|aggbs2|aggb2|aggbbs2|agom2|agoh2|argm2|argh2|aghh2|aghhb2|aghx2|aghxb2|agcm2|agcmb2|agch2|agchb2|agnm2|agnmb2|agnh2|agnhb2|agnx2|agnxb2)
    mode="antigravity-final"
    ;;
  kimm|kimb|kimbs)
    mode="kimi-json"
    ;;
  dglm|dswe|dargh|dopmm|doph|dopx|dopm)
    mode="devin-final"
    ;;
  grok|grokxh|grok2|grok2xh|grok3|grok3xh)
    mode="grok-json"
    ;;
  clm)
    mode="codex-final"
    resolved_launcher="clme"
    ;;
  clmb)
    mode="codex-final"
    resolved_launcher="clmbe"
    ;;
  clm2)
    mode="codex-final"
    resolved_launcher="clme2"
    ;;
  clmb2)
    mode="codex-final"
    resolved_launcher="clmbe2"
    ;;
  clme|clmbe|clme2|clmbe2)
    mode="codex-final"
    ;;
  cdx)
    mode="codex-final"
    resolved_launcher="cdxe"
    ;;
  cdxb)
    mode="codex-final"
    resolved_launcher="cdxbe"
    ;;
  cdx2)
    mode="codex-final"
    resolved_launcher="cdxe2"
    ;;
  cdxb2)
    mode="codex-final"
    resolved_launcher="cdxbe2"
    ;;
  cdm)
    mode="codex-final"
    resolved_launcher="cdme"
    ;;
  cdmb)
    mode="codex-final"
    resolved_launcher="cdmbe"
    ;;
  cdm2)
    mode="codex-final"
    resolved_launcher="cdme2"
    ;;
  cdmb2)
    mode="codex-final"
    resolved_launcher="cdmbe2"
    ;;
  cdxe|cdxbe|cdxe2|cdxbe2|cdme|cdmbe|cdme2|cdmbe2)
    mode="codex-final"
    ;;
  ctx|ctxb|ctx2|ctxb2|ctm|ctmb|ctm2|ctmb2|cam|camb|cax|caxb|camm|cammb|cah|cahb|cam2|camb2|cax2|caxb2|camm2|cammb2|cah2|cahb2|cdmM|cdxX|camM|caxX|cdmM2|cdxX2|camM2|caxX2)
    # Keep model, account and boost options while selecting final-only output.
    mode="codex-final-print"
    ;;
  ocs|ommp|ocargh|ochy|ocq4h|ocq4x|ocmm26|ochy4flash|oclongcat|ociceman)
    mode="opencode-json"
    ;;
  cmg|cmds|cmm26p|cmqh|cmqx|cms|cmhy|cmdglyph|cmdflint)
    mode="command-json"
    ;;
  pihy4flash|pilongcat|piiceman)
    # Pi's text print mode writes only the last assistant message's text.
    mode="pi-final"
    ;;
  cmd:?*)
    # An exact model the user named: am resolves and revalidates it, so it never becomes another model.
    mode="command-route"
    resolved_launcher="am"
    ;;
  csm|csu|csx|cshh|csmm|csbm|csbu|csbx|csbh|csbmm|chm|chu|chx|chh|chmm|chbm|chbu|chbx|chbh|chbmm|ccx|ccbx|ccm|ccbm|ccmm|ccfh|ccbfh|ccfx|ccbfx|ccmM|ccxX|cck|cckm|ccku|cckx|cckh|cckmm|cckbm|cckbu|cckbx|cckbh|cckbmm|cckfm|cckfu|cckfx|cckfh|cckfmm|cckbfm|cckbfu|cckbfx|cckbfh|cckbfmm)
    mode="claude-json"
    ;;
  *)
    if (( codex_api )); then
      mode="codex-final-print"
      if [[ "$launcher" == "cdxe-fresh" || "$launcher" == "cdube" || "$launcher" == "cdhbe" || "$launcher" == "cdmmbe" || "$launcher" == "cdlbe" ]]; then
        mode="codex-final"
      fi
    else
      delegate_worker_usage >&2
      delegate_worker_fail "unsupported launcher: $launcher"
    fi
    ;;
esac

# Command Code returns a run's last message: a worker that ends on a progress note returns no answer.
if [[ "$mode" == command-json || "$mode" == command-route ]]; then
  prompt+=$'\n\n'"Delivery: never send a progress note as a message; your final message holds the complete answer."
fi

if (( codex_api )); then
  declare -F cdxk >/dev/null ||
    delegate_worker_fail "launcher wrapper is not defined after sourcing $bash_agents_file: cdxk"
fi
if (( agy_api )); then
  declare -F agk >/dev/null ||
    delegate_worker_fail "launcher wrapper is not defined after sourcing $bash_agents_file: agk"
fi
declare -F "$resolved_launcher" >/dev/null ||
  delegate_worker_fail "launcher wrapper is not defined after sourcing $bash_agents_file: $resolved_launcher"

output_file="$(mktemp "${TMPDIR:-/tmp}/delegate-worker-output.XXXXXX")" ||
  delegate_worker_fail 'could not create an output file'
error_file="$(mktemp "${TMPDIR:-/tmp}/delegate-worker-error.XXXXXX")" || {
  rm -f -- "$output_file"
  delegate_worker_fail 'could not create an error file'
}
refusals="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/refusals.py"
cleanup() {
  local status=$?
  # probe-launcher reads the CLI's own output for the model it names. Silent, and first: nothing may follow
  # the failure-class line.
  [[ -z "${DELEGATE_WORKER_RAW:-}" ]] || command cp -- "$output_file" "$DELEGATE_WORKER_RAW" 2>/dev/null || true
  # A failed run's last stderr line is its failure class; run-wave.sh and wave-status read it.
  # It starts a line of its own: the diagnostics before it need not end in a newline.
  if (( status != 0 )) && [[ -n "${worker_status:-}" ]]; then
    printf '\ndelegate worker: failure class: %s\n' \
      "$(python3 "$refusals" --launcher "$requested_launcher" "$error_file" "$output_file" || printf unclassified)" >&2
  fi
  rm -f -- "$output_file" "$error_file"
  [[ -z "${devin_prompt_file:-}" ]] || rm -f -- "$devin_prompt_file"
}
trap cleanup EXIT

run_captured() {
  set +e
  "$@" >"$output_file" 2>"$error_file"
  worker_status=$?
  set -e
}

case "$mode" in
  antigravity-final)
    if (( agy_api )); then
      run_captured agk "$resolved_launcher" -p "$prompt"
    else
      run_captured "$resolved_launcher" -p "$prompt"
    fi
    # A picked run that its account's quota stopped moves once to the account with quota left.
    if [[ -n "${agy_account:-}" ]] && (( worker_status != 0 )); then
      overflow="$(python3 "$agy_account" overflow "$resolved_launcher" || printf other)"
      if [[ "$overflow" == "retry "* ]]; then
        printf 'delegate worker: %s ran out of quota; moving the task to %s\n' "$resolved_launcher" "${overflow#retry }" >&2
        resolved_launcher="${overflow#retry }"
        run_captured "$resolved_launcher" -p "$prompt"
        (( worker_status == 0 )) || overflow="$(python3 "$agy_account" overflow "$resolved_launcher" || printf other)"
      fi
      if [[ "$overflow" == "exhausted "* ]]; then
        printf 'delegate worker: Antigravity quota exhausted on every signed-in account (%s)\n' "${overflow#exhausted }" >>"$error_file"
      fi
    fi
    ;;
  devin-final)
    command -v python3 >/dev/null 2>&1 || delegate_worker_fail 'Python 3 is required for Devin final output'
    devin_prompt_file="$(mktemp "${TMPDIR:-/tmp}/delegate-devin-prompt.XXXXXX")" || delegate_worker_fail 'could not capture Devin task'
    # Extraction finds this run's session by its exact prompt, so concurrent
    # same-task workers (waves, judges) each need a unique one.
    prompt+=$'\n\n'"Delegate task id: ${devin_prompt_file##*.}-$$"
    printf '%s' "$prompt" >"$devin_prompt_file"
    devin_started="$(python3 -c 'import time; print(int(time.time()))')"
    run_captured "$resolved_launcher" -p "$prompt"
    ;;
  kimi-json)
    command -v jq >/dev/null 2>&1 || delegate_worker_fail 'jq is required for clean Kimi output'
    run_captured "$resolved_launcher" --output-format stream-json -p "$prompt"
    ;;
  grok-json)
    command -v jq >/dev/null 2>&1 || delegate_worker_fail 'jq is required for clean Grok output'
    run_captured "$resolved_launcher" --output-format json -p "$prompt"
    ;;
  claude-json)
    command -v jq >/dev/null 2>&1 || delegate_worker_fail 'jq is required for clean Claude output'
    run_captured "$resolved_launcher" --output-format json -p "$prompt"
    ;;
  command-json)
    command -v jq >/dev/null 2>&1 || delegate_worker_fail 'jq is required for clean Command Code output'
    run_captured "$resolved_launcher" --no-auto-update --output-format json -p "$prompt"
    ;;
  command-route)
    command -v jq >/dev/null 2>&1 || delegate_worker_fail 'jq is required for clean Command Code output'
    run_captured am "$launcher" -- --no-auto-update --output-format json -p "$prompt"
    ;;
  codex-final)
    if (( codex_api )); then
      run_captured cdxk "$resolved_launcher" "$prompt"
    else
      run_captured "$resolved_launcher" "$prompt"
    fi
    ;;
  codex-final-print)
    if (( codex_api )); then
      run_captured cdxk "$resolved_launcher" -p "$prompt"
    else
      run_captured "$resolved_launcher" -p "$prompt"
    fi
    ;;
  opencode-json)
    command -v jq >/dev/null 2>&1 || delegate_worker_fail 'jq is required for clean OpenCode output'
    run_captured "$resolved_launcher" run --format json "$prompt"
    ;;
  pi-final)
    run_captured "$resolved_launcher" -p "$prompt"
    ;;
esac

if (( worker_status != 0 )); then
  printf 'delegate worker: %s failed with status %s\n' "$resolved_launcher" "$worker_status" >&2
  [[ ! -s "$error_file" ]] || command cat "$error_file" >&2
  # Never replay a partial AGY response on failure; diagnostics are on stderr.
  if [[ "$mode" != "antigravity-final" && -s "$output_file" ]]; then
    command cat "$output_file" >&2
  fi
  exit "$worker_status"
fi

case "$mode" in
  devin-final)
    [[ ! -s "$error_file" ]] || command cat "$error_file" >&2
    python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/devin-final-output.py" \
      "$HOME/.local/share/devin/cli/sessions.db" "$output_file" "$devin_prompt_file" "$(pwd -P)" "$devin_started"
    ;;
  kimi-json)
    if ! final_text="$(jq -ers '
      [.[]
        | select(.role == "assistant")
        | .content?
        | select(type == "string" and length > 0)]
      | last
    ' "$output_file" 2>/dev/null)"; then
      printf 'delegate worker: Kimi returned no parseable final assistant message\n' >&2
      [[ ! -s "$error_file" ]] || command cat "$error_file" >&2
      command cat "$output_file" >&2
      exit 1
    fi
    printf '%s\n' "$final_text"
    ;;
  grok-json)
    if ! final_text="$(jq -er '.text | select(type == "string" and length > 0)' "$output_file" 2>/dev/null)"; then
      printf 'delegate worker: Grok returned no parseable final text\n' >&2
      [[ ! -s "$error_file" ]] || command cat "$error_file" >&2
      command cat "$output_file" >&2
      exit 1
    fi
    printf '%s\n' "$final_text"
    ;;
  claude-json)
    # Claude prints one result object, or an event array when verbose is on.
    if ! final_text="$(jq -er '
      (if type == "array" then map(select(.type? == "result")) | last else . end)
      | select(.is_error == false)
      | .result | select(type == "string" and length > 0)
    ' "$output_file" 2>/dev/null)"; then
      printf 'delegate worker: Claude returned no successful final result\n' >&2
      [[ ! -s "$error_file" ]] || command cat "$error_file" >&2
      command cat "$output_file" >&2
      exit 1
    fi
    printf '%s\n' "$final_text"
    ;;
  command-json|command-route)
    if ! final_text="$(jq -ers '
      last | select(.type == "result" and .subtype == "success")
      | .finalText | select(type == "string" and length > 0)
    ' "$output_file" 2>/dev/null)"; then
      printf 'delegate worker: Command Code returned no successful final result\n' >&2
      [[ ! -s "$error_file" ]] || command cat "$error_file" >&2
      command cat "$output_file" >&2
      exit 1
    fi
    printf '%s\n' "$final_text"
    ;;
  opencode-json)
    if ! final_text="$(jq -ers '
      [.[] | select(.type == "text" and (.part.text | type == "string" and length > 0))]
      | if length == 0 then empty
        else (last as $last | $last.part.messageID as $mid | [.[] | select(.part.messageID == $mid) | .part.text] | join(""))
        end
    ' "$output_file" 2>/dev/null)"; then
      printf 'delegate worker: OpenCode returned no parseable final text\n' >&2
      [[ ! -s "$error_file" ]] || command cat "$error_file" >&2
      command cat "$output_file" >&2
      exit 1
    fi
    printf '%s\n' "$final_text"
    ;;
  *)
    if [[ ! -s "$output_file" ]]; then
      printf 'delegate worker: %s returned an empty response\n' "$resolved_launcher" >&2
      [[ ! -s "$error_file" ]] || command cat "$error_file" >&2
      exit 1
    fi
    command cat "$output_file"
    ;;
esac
