# Git helpers dispatcher: g help / g <cmd> / g ? / g find
# Source this file (it sources functions.bash and defines g + short names).

_GH_DIR="${_GH_DIR:-$HOME/.git-helpers}"
_GH_REGISTRY="${_GH_REGISTRY:-$_GH_DIR/registry.tsv}"
_GH_IMPL="${_GH_IMPL:-$_GH_DIR/functions.bash}"

if [ ! -f "$_GH_REGISTRY" ]; then
  echo "git-helpers: registry not found: $_GH_REGISTRY" >&2
  return 1 2>/dev/null || exit 1
fi

# shellcheck source=functions.bash
. "$_GH_IMPL"

_gh_registry_rows() {
  # Skip comments/blank lines
  awk -F'|' '!/^#/ && NF>=1 && $1!="" {print}' "$_GH_REGISTRY"
}

_gh_field() {
  # usage: _gh_field <line> <1-based-index>
  printf '%s\n' "$1" | awk -F'|' -v n="$2" '{print $n}'
}

_gh_command_exists() {
  declare -F "$1" >/dev/null 2>&1
}

_gh_resolve_name() {
  # Exact function name, or g+prefix (bs -> gbs), else unique name prefix.
  local want="$1" line name
  local -a matches=()
  if _gh_command_exists "$want"; then
    printf '%s\n' "$want"
    return 0
  fi
  if _gh_command_exists "g$want"; then
    printf '%s\n' "g$want"
    return 0
  fi
  while IFS= read -r line; do
    name=$(_gh_field "$line" 1)
    if [[ "$name" == "$want"* ]]; then
      matches+=("$name")
    fi
  done < <(_gh_registry_rows)
  if [ ${#matches[@]} -eq 1 ]; then
    printf '%s\n' "${matches[0]}"
    return 0
  fi
  if [ ${#matches[@]} -gt 1 ]; then
    echo "Ambiguous: $want → ${matches[*]}" >&2
  fi
  return 1
}

_gh_lookup_row() {
  local want="$1" line name
  while IFS= read -r line; do
    name=$(_gh_field "$line" 1)
    if [ "$name" = "$want" ]; then
      printf '%s\n' "$line"
      return 0
    fi
  done < <(_gh_registry_rows)
  return 1
}

_gh_print_row_brief() {
  local line="$1"
  local name tags summary usage risk
  name=$(_gh_field "$line" 1)
  tags=$(_gh_field "$line" 2)
  summary=$(_gh_field "$line" 3)
  usage=$(_gh_field "$line" 4)
  risk=$(_gh_field "$line" 6)
  if [ -n "$risk" ]; then
    printf '  %-8s %-22s %s  [%s]\n' "$name" "$tags" "$summary" "$risk"
  else
    printf '  %-8s %-22s %s\n' "$name" "$tags" "$summary"
  fi
}

_gh_print_row_detail() {
  local line="$1"
  local name tags summary usage example risk
  name=$(_gh_field "$line" 1)
  tags=$(_gh_field "$line" 2)
  summary=$(_gh_field "$line" 3)
  usage=$(_gh_field "$line" 4)
  example=$(_gh_field "$line" 5)
  risk=$(_gh_field "$line" 6)
  printf '%s — %s\n' "$name" "$summary"
  printf '  tags:    %s\n' "$tags"
  printf '  usage:   %s\n' "$usage"
  [ -n "$example" ] && printf '  example: %s\n' "$example"
  [ -n "$risk" ] && printf '  risk:    %s\n' "$risk"
  printf '  run:     %s\n  help:    g help %s\n' "$name" "$name"
}

_gh_primary_group() {
  # Map the first tag to a catalog section (mutually exclusive).
  local tags="$1"
  local first="${tags%% *}"
  case "$first" in
    commit|push) echo "Commit & push" ;;
    branch|merge|rebase) echo "Branches" ;;
    log|file|files|filter) echo "Log & history" ;;
    diag) echo "Diagnostics" ;;
    navigation) echo "Code navigation" ;;
    *) echo "Other" ;;
  esac
}

_gh_help_catalog() {
  echo "git helpers — g <cmd> [args] · g help [cmd] · g ? <query> · g find"
  echo
  local line tags group
  local groups=("Commit & push" "Branches" "Log & history" "Code navigation" "Diagnostics" "Other")
  local gi
  for gi in "${groups[@]}"; do
    local any=0
    while IFS= read -r line; do
      tags=$(_gh_field "$line" 2)
      group=$(_gh_primary_group "$tags")
      if [ "$group" = "$gi" ]; then
        if [ "$any" -eq 0 ]; then
          [ "$gi" = "Commit & push" ] || printf '\n'
          printf '%s\n' "$gi"
          any=1
        fi
        _gh_print_row_brief "$line"
      fi
    done < <(_gh_registry_rows)
  done
  echo
  echo "Search: g ? delete branch    Picker: g find (requires fzf)"
  echo "Short names (gac, glo, ...) still work directly."
}

_gh_word_match() {
  # Word-boundary match of term against text (term is already lowercase).
  # Avoids "delete" matching "deleted".
  printf '%s\n' "$2" | grep -qi -w -- "$1"
}

_gh_score_row() {
  # Print "score\tline" for row given query terms in "$@"
  local line="$1"; shift
  local name tags summary usage example risk
  name=$(_gh_field "$line" 1)
  tags=$(_gh_field "$line" 2)
  summary=$(_gh_field "$line" 3)
  usage=$(_gh_field "$line" 4)
  example=$(_gh_field "$line" 5)
  risk=$(_gh_field "$line" 6)
  local score=0 term lower_name
  lower_name=$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')
  for term in "$@"; do
    term=$(printf '%s' "$term" | tr '[:upper:]' '[:lower:]')
    [ -z "$term" ] && continue
    if [ "$lower_name" = "$term" ]; then
      score=$((score + 100))
    elif [[ "$lower_name" == *"$term"* ]]; then
      score=$((score + 50))
    fi
    if _gh_word_match "$term" "$tags"; then
      score=$((score + 30))
    fi
    if _gh_word_match "$term" "$risk"; then
      score=$((score + 20))
    fi
    if _gh_word_match "$term" "$summary"; then
      score=$((score + 10))
    fi
    if _gh_word_match "$term" "$usage"; then
      score=$((score + 5))
    fi
    if _gh_word_match "$term" "$example"; then
      score=$((score + 5))
    fi
  done
  printf '%d\t%s\n' "$score" "$line"
}

_gh_search() {
  if [ $# -eq 0 ]; then
    echo "Usage: g ? <query terms...>   (or: g search <query>)" >&2
    return 1
  fi
  local results line score
  results=$(_gh_registry_rows | while IFS= read -r line; do
    _gh_score_row "$line" "$@"
  done | sort -t$'\t' -k1,1nr)
  if [ -z "$results" ]; then
    echo "No matches." >&2
    return 1
  fi
  # Drop zero-score rows unless everything is zero (then show catalog hint)
  local filtered
  filtered=$(printf '%s\n' "$results" | awk -F'\t' '$1+0>0')
  if [ -z "$filtered" ]; then
    echo "No matches for: $*" >&2
    echo "Try: g   (full catalog)" >&2
    return 1
  fi
  printf 'Matches for: %s\n\n' "$*"
  local shown=0
  while IFS=$'\t' read -r score line; do
    [ -z "$line" ] && continue
    _gh_print_row_brief "$line"
    shown=$((shown + 1))
    [ "$shown" -ge 8 ] && break
  done <<< "$filtered"
  echo
  echo "Detail: g help <name>   Run: g <name> [args]   Picker: g find"
}

_gh_needs_args() {
  # Heuristic: usage contains a required <arg> placeholder
  local usage="$1"
  [[ "$usage" == *"<"* ]]
}

_gh_find() {
  if ! command -v fzf >/dev/null 2>&1 || [ ! -t 0 ]; then
    if ! command -v fzf >/dev/null 2>&1; then
      echo "fzf not found; falling back to ranked search." >&2
    fi
    if [ $# -gt 0 ]; then
      _gh_search "$@"
    else
      _gh_help_catalog
    fi
    return
  fi
  local query="${1:-}"
  local selected line name usage extra_args
  selected=$(_gh_registry_rows | fzf \
    --query "$query" \
    --delimiter='|' \
    --with-nth=1,2,3 \
    --prompt='git helper> ' \
    --header='Enter: run · Ctrl-H: help · name | tags | summary' \
    --preview-window=down,60%,wrap \
    --preview 'line={}; name=$(printf "%s" "$line" | cut -d"|" -f1); tags=$(printf "%s" "$line" | cut -d"|" -f2); summary=$(printf "%s" "$line" | cut -d"|" -f3); usage=$(printf "%s" "$line" | cut -d"|" -f4); example=$(printf "%s" "$line" | cut -d"|" -f5); risk=$(printf "%s" "$line" | cut -d"|" -f6); printf "%s\n\ntags:    %s\nusage:   %s\n" "$summary" "$tags" "$usage"; [ -n "$example" ] && printf "example: %s\n" "$example"; [ -n "$risk" ] && printf "risk:    %s\n" "$risk"; printf "\nrun: %s\nhelp: g help %s\n" "$name" "$name"' \
    --expect=enter,ctrl-h) || return 130
  # fzf --expect: first line is key, rest is selection
  local key
  key=$(printf '%s\n' "$selected" | head -n1)
  line=$(printf '%s\n' "$selected" | tail -n +2)
  [ -z "$line" ] && return 0
  name=$(_gh_field "$line" 1)
  usage=$(_gh_field "$line" 4)
  if [ "$key" = "ctrl-h" ]; then
    _gh_print_row_detail "$line"
    return 0
  fi
  if _gh_needs_args "$usage"; then
    printf '%s\n' "$(_gh_print_row_detail "$line")"
    printf 'Arguments (usage: %s): ' "$usage"
    read -r extra_args
    if ! command -v python3 >/dev/null 2>&1; then
      printf 'Quoted picker arguments require python3; run %s directly.\n' "$name" >&2
      return 2
    fi
    local args_file arg
    local -a parsed_args=()
    args_file=$(mktemp "${TMPDIR:-/tmp}/git-helper-args.XXXXXX") || return
    if ! python3 -c '
import os, shlex, sys
try:
    args = shlex.split(sys.argv[1])
except ValueError as exc:
    print("Arguments: " + str(exc), file=sys.stderr)
    sys.exit(2)
for arg in args:
    sys.stdout.buffer.write(os.fsencode(arg) + b"\0")
' "$extra_args" > "$args_file"; then
      rm -f -- "$args_file"
      return 2
    fi
    while IFS= read -r -d '' arg; do parsed_args+=("$arg"); done < "$args_file"
    rm -f -- "$args_file"
    g "$name" "${parsed_args[@]}"
  else
    g "$name"
  fi
}

g() {
  if [ $# -eq 0 ]; then
    _gh_help_catalog
    return 0
  fi
  local cmd="$1"
  shift
  case "$cmd" in
    help|h|-h|--help)
      if [ $# -eq 0 ]; then
        _gh_help_catalog
        return 0
      fi
      local row resolved_help
      if ! resolved_help=$(_gh_resolve_name "$1"); then
        echo "Unknown helper: $1" >&2
        echo "Try: g   (catalog) or g ? $1" >&2
        return 1
      fi
      if ! row=$(_gh_lookup_row "$resolved_help"); then
        echo "Unknown helper: $1" >&2
        echo "Try: g   (catalog) or g ? $1" >&2
        return 1
      fi
      _gh_print_row_detail "$row"
      ;;
    \?|search|find-query)
      if [ "$cmd" = "find-query" ]; then
        _gh_find "$@"
      else
        _gh_search "$@"
      fi
      ;;
    find|fzf)
      _gh_find "$@"
      ;;
    list|ls)
      _gh_help_catalog
      ;;
    *)
      local resolved
      if resolved=$(_gh_resolve_name "$cmd"); then
        "$resolved" "$@"
      else
        echo "Unknown helper: $cmd" >&2
        _gh_search "$cmd" || true
        return 1
      fi
      ;;
  esac
}
