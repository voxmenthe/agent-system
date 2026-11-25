# Read-only navigation; keep the directory-stack action in the calling shell.
_gh_navigation() {
  local arg syntax=0
  if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'git-helpers: navigation requires Python 3.10+' >&2
    return 2
  fi
  for arg in "$@"; do
    [ "$arg" = '--' ] && break
    [ "$arg" = '--syntax' ] && syntax=1
  done
  if [ -t 1 ] && [ "$syntax" -eq 0 ] && command -v delta >/dev/null 2>&1 &&
     [[ "$1" = focus || "$1" = line || "$1" = range ]]; then
    python3 -B "$_GH_DIR/navigation.py" "$@" | delta --paging=auto
    return "${PIPESTATUS[0]}"
  fi
  python3 -B "$_GH_DIR/navigation.py" "$@"
}

gmap()     { _gh_navigation map "$@"; }
gfocus()   { _gh_navigation focus "$@"; }
gwhy()     { _gh_navigation why "$@"; }
goutline() { _gh_navigation outline "$@"; }
gline()    { _gh_navigation line "$@"; }
gimpact()  { _gh_navigation impact "$@"; }
gshape()   { _gh_navigation shape "$@"; }
ghot()     { _gh_navigation hot "$@"; }
grange()   { _gh_navigation range "$@"; }
gdoctor()  { _gh_navigation doctor "$@"; }

gpeek() {
  local arg dirs=0 output target status
  for arg in "$@"; do
    [ "$arg" = '--' ] && break
    [ "$arg" = '--dirs' ] && dirs=1
  done
  if [ "$dirs" -eq 0 ]; then
    _gh_navigation peek "$@"
    return
  fi
  output=$(mktemp "${TMPDIR:-/tmp}/git-nav-directory.XXXXXX") || return
  _gh_navigation peek --directory-output "$output" "$@"
  status=$?
  if [ "$status" -eq 0 ] && IFS= read -r -d '' target < "$output"; then
    pushd -- "$target"
    status=$?
  fi
  rm -f -- "$output"
  return "$status"
}
