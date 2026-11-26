#!/usr/bin/env bash
# Bash 3.2: monitor mode owns one process group per adapter, without setsid.
set -o pipefail
export LC_ALL=C
umask 077

usage() {
  printf '%s\n' 'Usage: run-wave.sh --wave PATH --jobs-dir DIR [--jobs N] [--timeout SECS] [--dry-run]' \
    'Compose independent assignments; default jobs: 4, no timeout. DIR must be fresh.' \
    'Dry run writes tasks only. Read references/wave-runner.md before use.'
}
fail() { printf 'delegate wave: %s\n' "$*" >&2; exit 2; }
manifest_error() { fail "manifest line $line_number: $*"; }

wave='' jobs_dir='' jobs=4 timeout='' dry_run=0 options=' '
while (( $# )); do
  [[ $options != *" $1 "* ]] || fail "repeated option: $1"
  options="$options$1 "
  case $1 in
    --wave|--jobs-dir|--jobs|--timeout)
      (( $# >= 2 )) && [[ -n $2 && $2 != --* ]] || fail "$1 requires a value"
      case $1 in
        --wave) wave=$2 ;;
        --jobs-dir) jobs_dir=$2 ;;
        --jobs) jobs=$2 ;;
        --timeout) timeout=$2 ;;
      esac
      shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    --help) (( $# == 1 )) && [[ $options == ' --help ' ]] || fail '--help must be used alone'
      usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done
[[ -n $wave && -n $jobs_dir ]] || fail '--wave and --jobs-dir are required'
[[ $jobs =~ ^[0-9]+$ && $jobs == *[1-9]* ]] || fail '--jobs must be a positive integer'
[[ -z $timeout || $timeout =~ ^[1-9][0-9]{0,6}$ ]] || fail '--timeout must be whole seconds from 1 to 9999999'
[[ $wave == /* ]] || wave="$PWD/$wave"
[[ $jobs_dir == /* ]] || jobs_dir="$PWD/$jobs_dir"
[[ -f $wave && -r $wave ]] || fail "unreadable manifest: $wave"
# Capture once, including trailing newlines, and check read errors before parsing.
manifest=$(cat -- "$wave" && printf '\001') || fail "cannot read manifest: $wave"
manifest=${manifest%$'\001'}
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P) || fail 'cannot locate sibling adapter'
# The adapter sources the wrappers; Kimi Code uses their managed K3.1 Pro default.
adapter="$script_dir/run-worker.sh"
[[ -f $adapter && -x $adapter ]] || fail "missing executable sibling adapter: $adapter"
# Space-separated launcher=account pairs: launchers on one row of the table share an
# allowance (wave-usage reads the same table); the account is harness or harness:account.
routes_file="$script_dir/launcher-routes.tsv" routes=' '
{
  IFS= read -r route_line && [[ $route_line == $'harness\taccount\tlaunchers' ]] || fail "launcher routes lack their header: $routes_file"
  while IFS=$'\t' read -r harness account members || [[ -n $harness ]]; do
    read -ra listed <<<"$members"
    [[ $harness =~ ^[a-z]+$ && $account =~ ^([a-z0-9]+|-)$ && ${#listed[@]} -gt 0 ]] || fail "bad launcher routes row: $harness"
    [[ $account == - ]] && account=$harness || account="$harness:$account"
    for member in "${listed[@]}"; do routes="$routes$member=$account "; done
  done
} < "$routes_file" || fail "cannot read launcher routes: $routes_file"

names=() launchers=() bodies=() folded_names=' '
common='' common_seen=' ' seen=' ' field='' value='' role='' workspace=''
line_number=0 section=-2
finish_field() {
  [[ -n $field ]] || return 0
  [[ -n ${value//[[:space:]]/} ]] || manifest_error "empty $field"
  if (( section == -1 )); then
    case $field in
      ROLE) role=${value# }; [[ $role =~ ^(implement|analyze|review|verify)$ ]] || manifest_error 'invalid ROLE' ;;
      WORKSPACE) workspace=${value# }; [[ $workspace == /* && -d $workspace ]] || manifest_error 'WORKSPACE must be an existing absolute directory' ;;
    esac
  fi
}
finish_section() {
  finish_field
  local required
  if (( section == -1 )); then
    for required in ROLE WORKSPACE CONTEXT CONSTRAINTS; do
      [[ $seen == *" $required "* ]] || manifest_error "COMMON missing $required"
    done
    common_seen=$seen
  elif (( section >= 0 )); then
    for required in OBJECTIVE SCOPE VERIFY; do
      [[ $seen == *" $required "* || $common_seen == *" $required "* ]] || manifest_error "worker ${names[$section]} missing $required"
    done
  fi
}
header_pattern='^@@ launcher=([A-Za-z0-9]+|cdxk:[A-Za-z0-9-]+|agk:[A-Za-z0-9-]+|cmd:[A-Za-z0-9._/:+-]+) name=([A-Za-z0-9][A-Za-z0-9_-]*)$'
field_pattern='^([A-Z]+):(.*)$'
while IFS= read -r line || [[ -n $line ]]; do
  line_number=$((line_number + 1))
  line=${line%$'\r'}
  if (( section == -2 )); then
    [[ -n ${line//[[:space:]]/} ]] || continue
    [[ $line == COMMON: ]] || manifest_error 'first nonblank line must be COMMON:'
    section=-1
    continue
  fi
  [[ $line != COMMON: ]] || manifest_error 'repeated COMMON:'
  if [[ $line == @@* ]]; then
    [[ $line =~ $header_pattern ]] || manifest_error 'expected @@ launcher=<known> name=<id>'
    launcher=${BASH_REMATCH[1]} name=${BASH_REMATCH[2]}
    case $launcher in
      cdxk|cdxk:*|agk|agk:*) ;;
      agg|aggbs|aggb|aggbbs|agom|agoh|argm|argh|aghh|aghhb|aghx|aghxb|agcm|agcmb|agch|agchb|agnm|agnmb|agnh|agnhb|agnx|agnxb|agg2|aggbs2|aggb2|aggbbs2|agom2|agoh2|argm2|argh2|aghh2|aghhb2|aghx2|aghxb2|agcm2|agcmb2|agch2|agchb2|agnm2|agnmb2|agnh2|agnhb2|agnx2|agnxb2|kimm|kimb|kimbs|dglm|dswe|dargh|dopmm|doph|dopx|dopm|grok|grokxh|grok2|grok2xh|grok3|grok3xh|clm|clmb|clme|clmbe|clm2|clmb2|clme2|clmbe2|ctx|ctxb|ctx2|ctxb2|ctm|ctmb|ctm2|ctmb2|cdx|cdxb|cdxe|cdxbe|cdx2|cdxb2|cdxe2|cdxbe2|cdm|cdmb|cdme|cdmbe|cdm2|cdmb2|cdme2|cdmbe2|cam|camb|cax|caxb|camm|cammb|cah|cahb|cam2|camb2|cax2|caxb2|camm2|cammb2|cah2|cahb2|cdmM|cdxX|camM|caxX|cdmM2|cdxX2|camM2|caxX2|ocs|ommp|ocargh|ochy|ocq4h|ocq4x|ocmm26|ochy4flash|oclongcat|ociceman|cmg|cmds|cmm26p|cmqh|cmqx|cms|cmhy|cmdglyph|cmdflint|pihy4flash|pilongcat|piiceman|csm|csu|csx|cshh|csmm|csbm|csbu|csbx|csbh|csbmm|chm|chu|chx|chh|chmm|chbm|chbu|chbx|chbh|chbmm|ccx|ccbx|ccm|ccbm|ccmm|ccfh|ccbfh|ccfx|ccbfx|ccmM|ccxX|cck|cckm|ccku|cckx|cckh|cckmm|cckbm|cckbu|cckbx|cckbh|cckbmm|cckfm|cckfu|cckfx|cckfh|cckfmm|cckbfm|cckbfu|cckbfx|cckbfh|cckbfmm) ;;
      cmd:?*) ;;
      *) manifest_error "unsupported launcher: $launcher" ;;
    esac
    folded=$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]') || fail 'cannot fold worker name'
    [[ $folded_names != *" $folded "* ]] || manifest_error "duplicate worker name: $name"
    folded_names="$folded_names$folded "
    finish_section
    section=${#names[@]}
    names+=("$name") launchers+=("$launcher") bodies+=('')
    seen=' ' field='' value=''
    continue
  fi
  if [[ $line =~ $field_pattern ]]; then
    next_field=${BASH_REMATCH[1]} next_value=${BASH_REMATCH[2]}
    finish_field
    case $next_field in
      OBJECTIVE|SCOPE|VERIFY) ;;
      ROLE|WORKSPACE|CONTEXT|CONSTRAINTS) (( section == -1 )) || manifest_error "worker cannot supply $next_field" ;;
      *) manifest_error "unknown or reserved field: $next_field" ;;
    esac
    [[ $seen != *" $next_field "* && ( $section == -1 || $common_seen != *" $next_field "* ) ]] || manifest_error "duplicate $next_field (no overrides)"
    seen="$seen$next_field " field=$next_field value=$next_value
  elif [[ -n ${line//[[:space:]]/} ]]; then
    [[ $line == [[:blank:]]* && -n $field ]] || manifest_error 'expected a field or indented continuation'
    value="$value"$'\n'"$line"
  fi
  if (( section == -1 )); then common="$common$line"$'\n'
  else bodies[section]="${bodies[$section]}$line"$'\n'; fi
done < <(printf '%s' "$manifest")
finish_section
(( ${#names[@]} )) || manifest_error 'at least one worker is required'
# Compare decimal strings before arithmetic to avoid overflow for large caps.
while [[ $jobs == 0* ]]; do jobs=${jobs#0}; done
count=${#names[@]}
# shellcheck disable=SC2071
if (( ${#jobs} > ${#count} )) || { (( ${#jobs} == ${#count} )) && [[ $jobs > $count ]]; }; then jobs=$count; fi
accounts=()
for (( i=0; i<count; i++ )); do
  account=${routes#* "${launchers[$i]}"=}
  if [[ ${launchers[$i]} == cmd:* ]]; then account=cmd
  elif [[ ${launchers[$i]} == cdxk ]]; then account=codex:key
  elif [[ ${launchers[$i]} == cdxk:* ]]; then
    [[ $account != "$routes" ]] || fail "unsupported cdxk target: ${launchers[$i]#cdxk:}"
    account=${account%% *}
    [[ $account == codex:key ]] || fail "unsupported cdxk target: ${launchers[$i]#cdxk:}"
  elif [[ ${launchers[$i]} == agk ]]; then account=antigravity:key
  elif [[ ${launchers[$i]} == agk:* ]]; then
    [[ $account != "$routes" ]] || fail "unsupported agk target: ${launchers[$i]#agk:}"
    account=${account%% *}
    [[ $account == antigravity:key ]] || fail "unsupported agk target: ${launchers[$i]#agk:}"
  elif [[ $account == "$routes" ]]; then fail "no launcher routes row names ${launchers[$i]}: $routes_file"
  else account=${account%% *}; fi
  accounts+=("$account")
done
parent=$(cd -- "$(dirname -- "$jobs_dir")" && pwd -P) || fail 'jobs directory parent must exist'
base=$(basename -- "$jobs_dir") || fail 'invalid jobs directory'
jobs_dir="$parent/$base"
mkdir -- "$jobs_dir" || fail "jobs directory must be fresh: $jobs_dir"
footer='Preserve unrelated changes. Do not commit, push, switch branches, alter workspace configuration, deploy, perform destructive operations or unrelated external writes, or delegate again unless the user explicitly authorized that action. Wave execution grants no additional authority.'
if [[ $role == implement ]]; then
  returns='RETURN: STATUS, CHANGED, VERIFICATION, BLOCKERS'
else
  footer="$footer"$'\n''This assignment is read-only; checks must not alter tracked or other owned work.'
  returns='RETURN: STATUS, FINDINGS, EVIDENCE, BLOCKERS'
fi
for (( i=0; i<count; i++ )); do
  printf '%s\n%s\n%s\n%s\n' "$common" "${bodies[$i]}" "$footer" "$returns" > "$jobs_dir/${names[$i]}.task" || fail 'cannot write all task artifacts; no workers launched'
done
if (( dry_run )); then
  for (( i=0; i<count; i++ )); do
    printf '\n--- %s (%s) ---\n' "${names[$i]}" "${launchers[$i]}" && cat -- "$jobs_dir/${names[$i]}.task" || exit 1
  done
  exit 0
fi
# The launch record, readable while the wave runs; SUMMARY.tsv comes at the end.
write_wave() {
  local index
  printf 'name\tlauncher\n' || return 1
  for (( index=0; index<count; index++ )); do
    printf '%s\t%s\n' "${names[$index]}" "${launchers[$index]}" || return 1
  done
}
write_wave > "$jobs_dir/WAVE.tsv" || fail 'cannot write WAVE.tsv; no workers launched'

pids=() statuses=() groups=() started=() stopping=() killed=()
next=0 active=0 result=0 interrupted=0 runner_failed=0
# Space-separated launcher=kind pairs: a launcher that refused a worker for quota
# or a non-retryable reason starts no more of this wave's workers; @account=kind
# pairs do the same for every launcher on an account whose quota a worker exhausted.
barred=' '
trap 'interrupted=130' INT
trap 'interrupted=143' TERM
# Background jobs become group leaders; the subshell exec preserves its PID.
set -m
write_status() {
  printf '%s\n' "${statuses[$1]}" > "$jobs_dir/${names[$1]}.status" || {
    printf 'delegate wave: cannot write status for %s\n' "${names[$1]}" >&2
    runner_failed=1
  }
}
# run-worker.sh ends a failed run's stderr with its failure class. Exhaustion of the
# account, named for this launcher's own harness, bars the account; any other
# refusal bars the launcher.
bar_refused() {
  local launcher=${launchers[$1]} account=${accounts[$1]} last
  [[ $2 != 0 && $2 != timeout ]] || return 0
  last=$(tail -n 1 -- "$jobs_dir/${names[$1]}.stderr" 2>/dev/null) || return 0
  if [[ $last =~ ^'delegate worker: failure class: rate-limited: account quota exhausted on '([a-z]+)(' '|$) &&
    ${BASH_REMATCH[1]} == "${account%%:*}" ]]; then
    [[ $barred != *" @$account="* ]] || return 0
    barred="$barred@$account=rate-limited "
    printf 'delegate wave: %s exhausted account %s (%s); queued workers on its launchers will not start\n' "$launcher" "$account" "${names[$1]}" >&2
    return 0
  fi
  [[ $barred != *" $launcher="* ]] || return 0
  [[ $last =~ ^'delegate worker: failure class: '(rate-limited|quarantined):' ' ]] || return 0
  barred="$barred$launcher=${BASH_REMATCH[1]} "
  printf 'delegate wave: %s was %s (%s); its queued workers will not start\n' "$launcher" "${BASH_REMATCH[1]}" "${names[$1]}" >&2
}
reap_finished() {
  local index status
  for (( index=0; index<next; index++ )); do
    [[ -z ${statuses[$index]} ]] || continue
    if ! kill -0 "${pids[$index]}" 2>/dev/null; then
      wait "${pids[$index]}"; status=$?
      [[ -z ${stopping[$index]} ]] || status=timeout
      statuses[index]=$status
      active=$((active - 1))
      [[ $status == 0 ]] || result=1
      write_status "$index"
      bar_refused "$index" "$status"
      if kill -0 -- "-${groups[$index]}" 2>/dev/null; then
        # Leftovers (for example an orphaned MCP server) have not released the
        # worker's scope; stop_groups ends them and keeps the adapter's status.
        # Interrupt and failure cleanup stop every group themselves.
        if (( interrupted == 0 && runner_failed == 0 )) && [[ -z ${stopping[$index]} ]]; then
          printf 'delegate wave: %s returned with live process group %s; stopping its remaining processes\n' "${names[$index]}" "${groups[$index]}" >&2
          kill -TERM -- "-${groups[$index]}" 2>/dev/null || :
          stopping[index]=$SECONDS
        fi
      else
        # Stop owning a vanished group; its numeric ID may later be reused.
        groups[index]=''
      fi
    fi
  done
}
# A worker past its timeout, or a returned worker's leftover processes, get
# SIGTERM to the group, then SIGKILL after five seconds; a group still alive two
# seconds after that SIGKILL fails the runner into full cleanup. SECONDS is
# wall-clock, so one late pass can span the whole window: check liveness first,
# and time the failure from the SIGKILL actually sent. Returns nonzero while a
# returned worker's group still has live processes.
stop_groups() {
  local index lingering=0
  for (( index=0; index<next; index++ )); do
    [[ -n ${groups[$index]} ]] || continue
    if ! kill -0 -- "-${groups[$index]}" 2>/dev/null; then
      # Stop owning a vanished group once reaped; its numeric ID may be reused.
      [[ -z ${statuses[$index]} ]] || groups[index]=''
      continue
    fi
    if [[ -z ${stopping[$index]} ]]; then
      # A leader that already exited is left for reap_finished to record.
      if [[ -z $timeout || -n ${statuses[$index]} ]] || (( SECONDS - started[index] < timeout )) ||
        ! kill -0 "${pids[$index]}" 2>/dev/null; then continue; fi
      printf 'delegate wave: %s exceeded %ss; stopping process group %s\n' "${names[$index]}" "$timeout" "${groups[$index]}" >&2
      kill -TERM -- "-${groups[$index]}" 2>/dev/null || :
      stopping[index]=$SECONDS
    elif [[ -z ${killed[$index]} ]]; then
      if (( SECONDS - stopping[index] >= 5 )); then
        kill -KILL -- "-${groups[$index]}" 2>/dev/null || :
        killed[index]=$SECONDS
      fi
    elif (( SECONDS - killed[index] >= 2 )); then
      if (( runner_failed == 0 )); then
        printf 'delegate wave: %s process group %s survived SIGKILL; stopping dispatch\n' "${names[$index]}" "${groups[$index]}" >&2
      fi
      runner_failed=1
    fi
    [[ -z ${statuses[$index]} ]] || lingering=1
  done
  (( lingering == 0 ))
}
lingering=0
while (( next < count || active > 0 || lingering )); do
  reap_finished
  if stop_groups; then lingering=0; else lingering=1; fi
  (( interrupted == 0 && runner_failed == 0 )) || break
  while (( next < count && active < jobs && interrupted == 0 && runner_failed == 0 )); do
    name=${names[$next]} refused=${barred#* "${launchers[$next]}"=} scope=${launchers[$next]}
    if [[ $refused == "$barred" ]]; then
      refused=${barred#* "@${accounts[$next]}"=} scope="account ${accounts[$next]}"
    fi
    if [[ $refused != "$barred" ]]; then
      statuses[next]="not-started (${refused%% *} on $scope)" pids[next]='' groups[next]=''
      write_status "$next"
      next=$((next + 1))
      continue
    fi
    # Open evidence in the parent: redirection failure must stop dispatch.
    if ! { exec 3>"$jobs_dir/$name.out" 4>"$jobs_dir/$name.stderr"; }; then
      runner_failed=1; break
    fi
    ( cd -- "$workspace" && exec "$adapter" "${launchers[$next]}" --task-file "$jobs_dir/$name.task" ) < /dev/null >&3 2>&4 3>&- 4>&- &
    pids[next]=$! groups[next]=$! statuses[next]='' started[next]=$SECONDS stopping[next]='' killed[next]=''
    exec 3>&- 4>&-
    next=$((next + 1)) active=$((active + 1))
  done
  (( interrupted == 0 && runner_failed == 0 )) || break
  if (( active > 0 || lingering )) && ! sleep 0.05; then runner_failed=1; break; fi
done
# A returned adapter with a live local descendant has not released its scope.
for group in "${groups[@]}"; do
  if [[ -n $group ]] && kill -0 -- "-$group" 2>/dev/null; then runner_failed=1; fi
done
if (( interrupted || runner_failed )); then
  trap '' INT TERM
  for group in "${groups[@]}"; do
    [[ -z $group ]] || kill -TERM -- "-$group" 2>/dev/null || :
  done
  deadline=$((SECONDS + 5))
  while (( SECONDS < deadline )); do
    reap_finished
    remaining=0
    for group in "${groups[@]}"; do
      if [[ -n $group ]] && kill -0 -- "-$group" 2>/dev/null; then remaining=1; fi
    done
    (( remaining )) || break
    sleep 0.05
  done
  for group in "${groups[@]}"; do
    [[ -z $group ]] || kill -KILL -- "-$group" 2>/dev/null || :
  done
  deadline=$((SECONDS + 1))
  while (( SECONDS < deadline )); do
    reap_finished
    remaining=0
    for group in "${groups[@]}"; do
      if [[ -n $group ]] && kill -0 -- "-$group" 2>/dev/null; then remaining=1; fi
    done
    (( remaining )) || break
    sleep 0.05
  done
  for (( i=0; i<next; i++ )); do
    if { [[ -n ${groups[$i]} ]] && kill -0 -- "-${groups[$i]}" 2>/dev/null; } || [[ -z ${statuses[$i]} ]]; then
      printf 'delegate wave: cleanup unconfirmed: %s pid/pgid=%s; inspect before reusing scope\n' "${names[$i]}" "${groups[$i]}" >&2
      statuses[i]=unconfirmed
    fi
    write_status "$i"
  done
  result=1
fi
for (( i=next; i<count; i++ )); do statuses[i]=not-started; write_status "$i"; done
write_summary() {
  local index bytes
  printf 'name\tlauncher\texit\tout-bytes\n' || return 1
  for (( index=0; index<count; index++ )); do
    bytes=0
    if [[ -f $jobs_dir/${names[$index]}.out ]]; then
      bytes=$(wc -c < "$jobs_dir/${names[$index]}.out") || return 1
      bytes=${bytes//[[:space:]]/}
    fi
    printf '%s\t%s\t%s\t%s\n' "${names[$index]}" "${launchers[$index]}" "${statuses[$index]}" "$bytes" || return 1
  done
}
if ! write_summary > "$jobs_dir/SUMMARY.tsv"; then
  printf 'delegate wave: cannot write SUMMARY.tsv; evidence is incomplete\n' >&2
  runner_failed=1
fi
(( interrupted == 0 )) || exit "$interrupted"
(( runner_failed == 0 )) || exit 1
exit "$result"
