#!/usr/bin/env bash
# Build a blind judge packet from a council run directory, or fail loudly.
# Usage: judge-packet.sh RUN_DIR PREAMBLE_FILE
# Reads RUN/TASK.md, RUN/parent/<L>.md (sealed parent candidate), the newest
# RUN/panel-<n>/<L>.out per letter (n = 1..9) and, when roles are on,
# RUN/lanes.tsv (letter<TAB>lane<TAB>complete-answer|contributing).
# Writes RUN/judge/packet.md and RUN/judge/excluded.txt; prints one line per
# letter and the packet size.
set -euo pipefail
run="${1:?usage: judge-packet.sh RUN_DIR PREAMBLE_FILE}" preamble="${2:?usage: judge-packet.sh RUN_DIR PREAMBLE_FILE}"
max_bytes=400000
fail() { echo "judge-packet: $*" >&2; exit 1; }
[[ -s $run/TASK.md && -s $preamble ]] || fail "missing TASK.md or preamble"
lanes="$run/lanes.tsv"
if [[ -e $lanes ]]; then
  bad=$(awk -F'\t' 'NF != 3 || $1 !~ /^[A-Z]$/ || $2 !~ /^[a-z0-9-]+$/ || ($3 != "complete-answer" && $3 != "contributing") || seen[$1]++ { printf " %d", NR }' "$lanes")
  [[ -z $bad ]] || fail "lanes.tsv line(s)$bad must be LETTER<TAB>lane<TAB>complete-answer|contributing, one row per letter"
fi
lane_of() { awk -F'\t' -v id="$1" '$1 == id { print $2 " (" $3 ")" }' "$lanes"; }
shopt -s nullglob
mkdir -p "$run/judge"
letters=$(for f in "$run"/parent/*.md "$run"/panel-[1-9]/*.task; do basename "${f%.*}"; done | sort -u)
[[ -n $letters ]] || fail "no candidates in $run"
excluded="$run/judge/excluded.txt" body="$run/judge/candidates.tmp"
: >"$excluded"; : >"$body"
external=0 total=0
for id in $letters; do
  [[ $id =~ ^[A-Z]$ ]] || fail "candidate name '$id' is not a single capital letter"
  tasks=("$run"/panel-[1-9]/"$id".task)
  if [[ -f $run/parent/$id.md ]]; then
    (( ${#tasks[@]} == 0 )) || fail "letter $id is both the sealed parent and a panel worker"
    f="$run/parent/$id.md"
    if ! grep -q '^STATUS:' "$f" || ! grep -q '^FINDINGS:' "$f"; then
      fail "parent/$id.md must use the panel's STATUS/FINDINGS/EVIDENCE/BLOCKERS headings"
    fi
  else
    f="${tasks[${#tasks[@]}-1]%.task}.out" status="${tasks[${#tasks[@]}-1]%.task}.status" reason=""
    if [[ ! -f $status ]]; then reason="no status (still running or lost)"
    elif [[ $(<"$status") != 0 ]]; then reason="exit $(<"$status")"
    elif [[ ! -s $f ]]; then reason="empty output"
    elif grep -qiE '^[^[:alnum:]]*STATUS[^[:alnum:]]*blocked' "$f"; then reason="STATUS blocked"
    fi
    if [[ -n $reason ]]; then echo "$id excluded: $reason (${f#"$run"/})" | tee -a "$excluded"; continue; fi
    external=$((external + 1))
  fi
  lane=""
  if [[ -e $lanes ]]; then
    lane=$(lane_of "$id")
    [[ -n $lane ]] || fail "roles are on but lanes.tsv has no row for candidate $id"
  fi
  { printf '\n## Candidate %s\n\n' "$id"
    [[ -z $lane ]] || printf 'Lane: %s\n\n' "$lane"
    cat "$f"; printf '\n'; } >>"$body"
  total=$((total + 1)); echo "$id included (${f#"$run"/})${lane:+, lane $lane}"
done
(( external >= 2 )) || { rm -f "$body"; fail "only $external usable external candidates; need 2"; }
{ cat "$preamble"; printf '\n# ORIGINAL TASK\n\n'; cat "$run/TASK.md"; printf '\n# CANDIDATE ANSWERS\n'; cat "$body"; } >"$run/judge/packet.md"
rm -f "$body"
bytes=$(wc -c <"$run/judge/packet.md" | tr -d ' ')
(( bytes <= max_bytes )) || fail "packet is $bytes bytes (> $max_bytes); trim candidates before judging"
echo "packet: judge/packet.md, $total candidates, $bytes bytes"
