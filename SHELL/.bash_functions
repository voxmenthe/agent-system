# ~~~ Shell Functions (Non-Git) ~~~

open-in-chrome() {
    # Usage: ls -1t "$PWD"/X-RESULTS/INTEGRATED/*.md | head | open-in-chrome
    local path=""
    local -a files=()

    while IFS= read -r path || [[ -n "$path" ]]; do
        [[ -n "$path" ]] || continue
        files+=("$path")
    done

    if [[ ${#files[@]} -gt 0 ]]; then
        command open -g -a "Google Chrome" -- "${files[@]}"
    fi
}

ag() {
  local app="Antigravity"
  local target="${1:-.}"
  local dir="$target" pair
  local -a pairs

  # Shortcuts first: AG_SHORTCUTS holds "name=path" pairs, set in shell.local.sh
  read -r -a pairs <<<"${AG_SHORTCUTS:-}"
  for pair in ${pairs[@]+"${pairs[@]}"}; do
    if [[ "${pair%%=*}" == "$target" ]]; then
      dir="${pair#*=}"
      break
    fi
  done

  # Expand "~"
  dir="${dir/#\~/$HOME}"

  # Validate
  [[ -d "$dir" ]] || { echo "ag: not a directory: $dir" >&2; return 2; }

  # Key fix: directory goes BEFORE --args
  open -a "$app" "$dir" --args \
    --enable-gpu-rasterization \
    --enable-zero-copy \
    --ignore-gpu-blocklist
}

copy-recent() {
    local count=$1
    local src_dir=$2
    local dest_dir=$3

    # Validate arguments
    if [[ -z "$count" || -z "$src_dir" || -z "$dest_dir" ]]; then
        echo "Usage: copy-recent <count> <src_dir> <dest_dir>"
        return 1
    fi

    # Create destination if it doesn't exist
    mkdir -p "$dest_dir"
    
    # Resolve dest_dir to an absolute path so it remains valid after we cd into src_dir
    local abs_dest_dir
    abs_dest_dir=$(cd "$dest_dir" && pwd)

    # Use a subshell to avoid changing the current directory
    (
        cd "$src_dir" || return
        # ls -tp: list by time, add trailing / to dirs
        # grep -v '/$': remove lines ending in / (directories)
        # head -n: take top N
        ls -tp | grep -v '/$' | head -n "$count" | while IFS= read -r file; do
             # Strip all whitespace (spaces, tabs, newlines) from the filename
             clean_name=$(echo "$file" | tr -d '[:space:]')
             
             # Copy from source to destination with the clean name
             cp "$file" "${abs_dest_dir}/${clean_name}"
        done
    )
}

ls-lt() {
    : '
    ls-lt - list files newest-first by mtime.

    Usage:
      ls-lt [FILE|DIR|GLOB]... [-n N] [find predicates...]

    Existing files are listed literally; directories are searched recursively.
    An unexpanded bare glob like "*.html" is a name filter applied to every
    directory in scope (explicit dirs plus the parents of file args), and
    multiple globs are OR-ed, not AND-ed. Quote globs to stop the shell from
    expanding them in the wrong directory:
      ls-lt JOB/COMPANIES/LABELBOX "*.md" "*.html" -n 10
    A glob containing "/" that the shell left alone is expanded here; if only
    its directory part exists it becomes a name filter on that directory.
    -n N keeps the N newest entries (the legacy "ls-lt DIR N" form still works).
    Other find predicates (-mtime, -size, -name X, ...) pass through to find.
    '

    local -a file_args=() dir_args=() exprs=() bare_pats=() search_dirs=()
    local -A scoped_pats=() seen_dir=() explicit_dir=()
    local limit="" arg="" last_arg="" d="" f=""

    if [[ $# -eq 0 ]]; then
        dir_args+=(".")
    elif [[ $# -eq 2 && -e "$1" && "$2" =~ ^[0-9]+$ ]]; then
        if [[ -d "$1" ]]; then dir_args+=("$1"); else file_args+=("$1"); fi
        limit="$2"
    else
        for arg in "$@"; do
            case "$last_arg" in
                -n)
                    limit="$arg"
                    last_arg=""
                    continue
                    ;;
                -name|-iname|-path|-ipath|-mtime|-mmin|-size|-type|-maxdepth|-mindepth)
                    exprs+=("$arg")
                    last_arg=""
                    continue
                    ;;
            esac

            if [[ -e "$arg" ]]; then
                if [[ -d "$arg" ]]; then dir_args+=("$arg"); else file_args+=("$arg"); fi
                last_arg=""
            elif [[ "$arg" == -* ]]; then
                case "$arg" in
                    -n|-name|-iname|-path|-ipath|-mtime|-mmin|-size|-type|-maxdepth|-mindepth)
                        last_arg="$arg"
                        ;;
                    *)
                        last_arg=""
                        ;;
                esac
                [[ "$arg" == "-n" ]] || exprs+=("$arg")
            elif [[ "$arg" == *"*"* || "$arg" == *"?"* || "$arg" == *"["* ]]; then
                if [[ "$arg" == */* ]]; then
                    local -a matches=()
                    while IFS= read -r f; do matches+=("$f"); done < <(compgen -G "$arg")
                    if ((${#matches[@]})); then
                        for f in "${matches[@]}"; do
                            if [[ -d "$f" ]]; then dir_args+=("$f"); else file_args+=("$f"); fi
                        done
                    elif [[ -d "${arg%/*}" ]]; then
                        scoped_pats["${arg%/*}"]+="${arg##*/}"$'\n'
                    else
                        printf "ls-lt: no matches: %s\n" "$arg" >&2
                    fi
                else
                    bare_pats+=("$arg")
                fi
                last_arg=""
            else
                exprs+=("$arg")
                last_arg=""
            fi
        done
    fi

    if [[ "$last_arg" == "-n" ]]; then
        echo "ls-lt: -n requires a value" >&2
        return 2
    fi

    if [[ -n "$limit" && ! "$limit" =~ ^[0-9]+$ ]]; then
        printf "ls-lt: -n expects a non-negative integer, got: %s\n" "$limit" >&2
        return 2
    fi

    for d in "${dir_args[@]}"; do
        if [[ -z "${seen_dir[$d]+x}" ]]; then
            seen_dir[$d]=1; explicit_dir[$d]=1; search_dirs+=("$d")
        fi
    done
    for d in "${!scoped_pats[@]}"; do
        [[ -z "${seen_dir[$d]+x}" ]] && { seen_dir[$d]=1; search_dirs+=("$d"); }
    done
    if ((${#bare_pats[@]})); then
        for f in "${file_args[@]}"; do
            d="${f%/*}"
            [[ "$d" == "$f" ]] && d="."
            [[ -z "${seen_dir[$d]+x}" ]] && { seen_dir[$d]=1; search_dirs+=("$d"); }
        done
    fi
    if ((${#search_dirs[@]} == 0 && ${#file_args[@]} == 0)); then
        search_dirs+=(".")
        explicit_dir["."]=1
    fi

    {
        if ((${#file_args[@]})); then
            find "${file_args[@]}" "${exprs[@]}" -type f \
                -exec stat -f "%m %Sm %N" -t "%Y-%m-%d %H:%M:%S" {} +
        fi
        for d in "${search_dirs[@]}"; do
            local -a pats=("${bare_pats[@]}")
            if [[ -n "${scoped_pats[$d]+x}" ]]; then
                while IFS= read -r f; do
                    [[ -n "$f" ]] && pats+=("$f")
                done <<< "${scoped_pats[$d]}"
            fi
            if ((${#pats[@]})); then
                local -a name_expr=()
                for f in "${pats[@]}"; do name_expr+=(-o -name "$f"); done
                find "$d" "${exprs[@]}" \( "${name_expr[@]:1}" \) -type f \
                    -exec stat -f "%m %Sm %N" -t "%Y-%m-%d %H:%M:%S" {} +
            elif [[ -n "${explicit_dir[$d]+x}" ]]; then
                find "$d" "${exprs[@]}" -type f \
                    -exec stat -f "%m %Sm %N" -t "%Y-%m-%d %H:%M:%S" {} +
            fi
        done
    } | sort -rn | awk '!seen[$0]++' | cut -d' ' -f2- \
        | { if [[ -n "$limit" ]]; then head -n "$limit"; else cat; fi }
}

file_set_ops() {
  : '
  file_set_ops - perform set operations between filenames in two directories
  
  Usage:
    file_set_ops <dir1> <dir2>
  
  Exports environment variables:
    - set1: sorted filenames from dir1
    - set2: sorted filenames from dir2
    - only_in_dir1: filenames present only in dir1
    - only_in_dir2: filenames present only in dir2
    - dir1_dir2_union: combined unique filenames from both directories
  
  Prints formatted results:
    - Intersection (files in both directories)
    - Files only in dir1 (dir1 \ dir2)
    - Files only in dir2 (dir2 \ dir1)
    - Union (all unique files)
  '
  
  if (( $# != 2 )); then
    echo "Usage: file_set_ops <dir1> <dir2>" >&2
    return 1
  fi
  
  local dir1="$1" dir2="$2"
  
  if [[ ! -d "$dir1" ]]; then
    echo "Error: directory '$dir1' does not exist" >&2
    return 1
  fi
  
  if [[ ! -d "$dir2" ]]; then
    echo "Error: directory '$dir2' does not exist" >&2
    return 1
  fi
  
  local tmp1 tmp2
  tmp1=$(mktemp 2>/dev/null) || { echo "Error: unable to allocate temp file" >&2; return 1; }
  tmp2=$(mktemp 2>/dev/null) || { rm -f "$tmp1"; echo "Error: unable to allocate temp file" >&2; return 1; }

  # Collect filenames (non-recursive) and sort them in a portable way
  if ! find "$dir1" -mindepth 1 -maxdepth 1 -type f -print | sed 's|^.*/||' | LC_ALL=C sort >"$tmp1"; then
    rm -f "$tmp1" "$tmp2"
    echo "Error: failed to enumerate files in '$dir1'" >&2
    return 1
  fi

  if ! find "$dir2" -mindepth 1 -maxdepth 1 -type f -print | sed 's|^.*/||' | LC_ALL=C sort >"$tmp2"; then
    rm -f "$tmp1" "$tmp2"
    echo "Error: failed to enumerate files in '$dir2'" >&2
    return 1
  fi

  local set1_content set2_content
  set1_content=$(<"$tmp1")
  set2_content=$(<"$tmp2")

  export set1="$set1_content"
  export set2="$set2_content"

  local count1 count2
  count1=$(wc -l <"$tmp1" | tr -d '[:space:]')
  count2=$(wc -l <"$tmp2" | tr -d '[:space:]')

  echo "✓ Set operations completed for directories:"
  printf '  dir1: %s (%s files)\n' "$dir1" "$count1"
  printf '  dir2: %s (%s files)\n' "$dir2" "$count2"
  echo "  Environment variables set1, set2, only_in_dir1, only_in_dir2, dir1_dir2_union exported"
  echo

  local intersection diff1 diff2 union
  intersection=$(comm -12 "$tmp1" "$tmp2")
  diff1=$(comm -23 "$tmp1" "$tmp2")
  diff2=$(comm -13 "$tmp1" "$tmp2")
  union=$(LC_ALL=C sort -u "$tmp1" "$tmp2")

  export only_in_dir1="$diff1"
  export only_in_dir2="$diff2"
  export dir1_dir2_union="$union"

  rm -f "$tmp1" "$tmp2"

  _file_set_ops_count() {
    awk 'NF{c++} END{print c+0}' <<<"$1"
  }

  _file_set_ops_print_section() {
    local title="$1" data="$2" lines_shown=0 total
    total=$(_file_set_ops_count "$data")
    printf "│ %-57s │\n" "$title ($total files):"
    if [[ -n "$data" ]]; then
      while IFS= read -r line && (( lines_shown < 10 )); do
        printf "│ %-57s │\n" "  $line"
        ((lines_shown++))
      done <<<"$data"
      if (( total > lines_shown )); then
        printf "│ %-57s │\n" "  ... and $((total - lines_shown)) more"
      fi
    else
      printf "│ %-57s │\n" "  (none)"
    fi
  }

  echo "📊 Set Operations Results:"
  echo "┌─────────────────────────────────────────────────────────────┐"
  _file_set_ops_print_section "Intersection" "$intersection"
  echo "├─────────────────────────────────────────────────────────────┤"
  _file_set_ops_print_section "Only in dir1" "$diff1"
  echo "├─────────────────────────────────────────────────────────────┤"
  _file_set_ops_print_section "Only in dir2" "$diff2"
  echo "├─────────────────────────────────────────────────────────────┤"
  _file_set_ops_print_section "Union" "$union"
  echo "└─────────────────────────────────────────────────────────────┘"
}

__fdiff_matches_any() {
  local file="$1" basename="${file##*/}"
  shift

  local pat
  for pat in "$@"; do
    if [[ "$pat" == */* ]]; then
      [[ "$file" == $pat ]] && return 0
    else
      [[ "$basename" == $pat ]] && return 0
    fi
  done

  return 1
}

fdiff() {
  : '
  fdiff - compare files of a given type between the current branch and another branch.

  Usage:
    fdiff <other-branch> <folder> [--include|-i <glob ...>] [--exclude|-e <glob ...>]

  If --include is omitted, every tracked file under <folder> is considered.
  Globs without a slash are matched against the basename; patterns containing
  a slash are matched against the path relative to the repository root.
  --exclude/-e takes the same glob semantics and removes matches after
  inclusion is evaluated. When the target folder is untracked on the current
  branch, fdiff falls back to the working tree so newly created files are
  still compared.
  '

  if (( $# < 2 )); then
    echo "Usage: fdiff <other-branch> <folder> [--include|-i <glob ...>] [--exclude|-e <glob ...>]" >&2
    return 1
  fi

  local other_branch="" target_path="" parse_mode=""
  local include_flag_used=0 exclude_flag_used=0
  local -a include_patterns=() exclude_patterns=()

  local arg
  for arg in "$@"; do
    case "$arg" in
      --include|-i)
        if [[ -z "$other_branch" || -z "$target_path" ]]; then
          echo "fdiff: specify <other-branch> and <folder> before --include/-i" >&2
          return 1
        fi
        parse_mode="include"
        include_flag_used=1
        continue
        ;;
      --exclude|-e)
        if [[ -z "$other_branch" || -z "$target_path" ]]; then
          echo "fdiff: specify <other-branch> and <folder> before --exclude/-e" >&2
          return 1
        fi
        parse_mode="exclude"
        exclude_flag_used=1
        continue
        ;;
      --)
        parse_mode=""
        continue
        ;;
    esac

    if [[ "$parse_mode" == "include" ]]; then
      if [[ -n "$arg" ]]; then
        local -a expanded_patterns=()
        local IFS=$' \t\n'
        read -r -a expanded_patterns <<<"$arg"
        if (( ${#expanded_patterns[@]} )); then
          include_patterns+=("${expanded_patterns[@]}")
        fi
      fi
      continue
    fi

    if [[ "$parse_mode" == "exclude" ]]; then
      if [[ -n "$arg" ]]; then
        local -a expanded_excludes=()
        local IFS=$' \t\n'
        read -r -a expanded_excludes <<<"$arg"
        if (( ${#expanded_excludes[@]} )); then
          exclude_patterns+=("${expanded_excludes[@]}")
        fi
      fi
      continue
    fi

    if [[ -z "$other_branch" ]]; then
      other_branch="$arg"
      continue
    fi

    if [[ -z "$target_path" ]]; then
      target_path="$arg"
      continue
    fi

    echo "Usage: fdiff <other-branch> <folder> [--include|-i <glob ...>] [--exclude|-e <glob ...>]" >&2
    return 1
  done

  if [[ -z "$other_branch" || -z "$target_path" ]]; then
    echo "Usage: fdiff <other-branch> <folder> [--include|-i <glob ...>] [--exclude|-e <glob ...>]" >&2
    return 1
  fi

  if (( include_flag_used && ${#include_patterns[@]} == 0 )); then
    echo "fdiff: --include/-i requires at least one glob" >&2
    return 1
  fi

  if (( exclude_flag_used && ${#exclude_patterns[@]} == 0 )); then
    echo "fdiff: --exclude/-e requires at least one glob" >&2
    return 1
  fi

  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "fdiff: must be run inside a git repository" >&2
    return 1
  fi

  local repo_root
  if ! repo_root=$(git rev-parse --show-toplevel 2>/dev/null); then
    echo "fdiff: unable to determine repository root" >&2
    return 1
  fi

  local python_bin=""
  if command -v python3 >/dev/null 2>&1; then
    python_bin=python3
  elif command -v python >/dev/null 2>&1; then
    python_bin=python
  else
    echo "fdiff: python is required to normalize path arguments" >&2
    return 1
  fi

  local -a _fdiff_path_meta=()
  if ! mapfile -t _fdiff_path_meta < <("$python_bin" - "$repo_root" "$PWD" "$target_path" <<'PY'
import os, sys
repo_root = os.path.abspath(sys.argv[1])
cwd = os.path.abspath(sys.argv[2])
user_arg = sys.argv[3]
abs_path = os.path.abspath(os.path.join(cwd, user_arg))
norm_repo = os.path.normpath(repo_root)
norm_abs = os.path.normpath(abs_path)
try:
    common = os.path.commonpath([norm_repo, norm_abs])
except ValueError:
    sys.exit(1)
if common != norm_repo:
    sys.exit(1)
rel = "." if norm_abs == norm_repo else os.path.relpath(norm_abs, norm_repo)
print(norm_abs)
print(rel)
PY
  ); then
    echo "fdiff: path '$target_path' must live inside repository ($repo_root)" >&2
    return 1
  fi

  if ((${#_fdiff_path_meta[@]} < 2)); then
    echo "fdiff: failed to resolve path metadata for '$target_path'" >&2
    return 1
  fi

  local target_abs="${_fdiff_path_meta[0]}"
  local repo_relative="${_fdiff_path_meta[1]}"
  local git_scope="$repo_relative"

  # git treats an empty scope as the entire tree, so normalize to "."
  [[ -z "$git_scope" ]] && git_scope="."

  local other_commit
  if ! other_commit=$(git rev-parse -q --verify "${other_branch}^{commit}"); then
    echo "fdiff: unable to resolve '${other_branch}' (try fetching?)" >&2
    return 1
  fi

  local current_branch
  current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  [[ -z "$current_branch" ]] && current_branch="HEAD"

  local -a current_raw=() other_raw=()
  if ! mapfile -t current_raw < <(git -C "$repo_root" ls-tree -r --name-only HEAD -- "$git_scope"); then
    echo "fdiff: failed to enumerate files for the current branch" >&2
    return 1
  fi

  if ! mapfile -t other_raw < <(git -C "$repo_root" ls-tree -r --name-only "$other_commit" -- "$git_scope"); then
    echo "fdiff: failed to enumerate files for '${other_branch}'" >&2
    return 1
  fi

  local used_worktree_fallback=0
  if ((${#current_raw[@]} == 0)) && [[ -d "$target_abs" ]]; then
    local -a find_cmd=()
    if [[ "$git_scope" == "." ]]; then
      find_cmd=(find "." -path "./.git" -prune -o -type f -print)
    else
      find_cmd=(find "$git_scope" -type f -print)
    fi

    while IFS= read -r line; do
      line=${line#./}
      [[ -n "$line" ]] && current_raw+=("$line")
    done < <(cd "$repo_root" && LC_ALL=C "${find_cmd[@]}")

    used_worktree_fallback=1
  fi

  local include_count=${#include_patterns[@]}
  local exclude_count=${#exclude_patterns[@]}
  local -a current_filtered=() other_filtered=()
  local file

  for file in "${current_raw[@]}"; do
    if (( include_count > 0 )) && ! __fdiff_matches_any "$file" "${include_patterns[@]}"; then
      continue
    fi

    if (( exclude_count > 0 )) && __fdiff_matches_any "$file" "${exclude_patterns[@]}"; then
      continue
    fi

    current_filtered+=("$file")
  done

  for file in "${other_raw[@]}"; do
    if (( include_count > 0 )) && ! __fdiff_matches_any "$file" "${include_patterns[@]}"; then
      continue
    fi

    if (( exclude_count > 0 )) && __fdiff_matches_any "$file" "${exclude_patterns[@]}"; then
      continue
    fi

    other_filtered+=("$file")
  done

  local -a current_sorted=() other_sorted=()
  if ((${#current_filtered[@]})); then
    mapfile -t current_sorted < <(printf '%s\n' "${current_filtered[@]}" | LC_ALL=C sort -u)
  else
    current_sorted=()
  fi

  if ((${#other_filtered[@]})); then
    mapfile -t other_sorted < <(printf '%s\n' "${other_filtered[@]}" | LC_ALL=C sort -u)
  else
    other_sorted=()
  fi

  local -a only_current=() only_other=()
  if ! mapfile -t only_current < <(comm -23 <(
        if ((${#current_sorted[@]})); then printf '%s\n' "${current_sorted[@]}"; fi
      ) <(
        if ((${#other_sorted[@]})); then printf '%s\n' "${other_sorted[@]}"; fi
      )); then
    echo "fdiff: failed to compute differences" >&2
    return 1
  fi

  if ! mapfile -t only_other < <(comm -13 <(
        if ((${#current_sorted[@]})); then printf '%s\n' "${current_sorted[@]}"; fi
      ) <(
        if ((${#other_sorted[@]})); then printf '%s\n' "${other_sorted[@]}"; fi
      )); then
    echo "fdiff: failed to compute differences" >&2
    return 1
  fi

  local scope_display="$repo_relative"
  [[ -z "$scope_display" ]] && scope_display="."

  echo "Scope: $scope_display"
  if (( include_count )); then
    local include_display
    include_display=$(printf '%s, ' "${include_patterns[@]}")
    include_display=${include_display%, }
    printf 'Include filter (basename unless pattern contains "/"): %s\n' "$include_display"
  fi

  if (( exclude_count )); then
    local exclude_display
    exclude_display=$(printf '%s, ' "${exclude_patterns[@]}")
    exclude_display=${exclude_display%, }
    printf 'Exclude filter (basename unless pattern contains "/"): %s\n' "$exclude_display"
  fi

  printf "Files in current branch (%s) not in %s:\n" "$current_branch" "$other_branch"
  if ((${#only_current[@]})); then
    printf '%s\n' "${only_current[@]}"
  else
    echo "(none)"
  fi

  if (( used_worktree_fallback )); then
    printf "\nNote: '%s' is not tracked on %s; comparing using working tree files.\n" "$scope_display" "$current_branch"
  fi

  echo
  printf "Files in %s not in current branch (%s):\n" "$other_branch" "$current_branch"
  if ((${#only_other[@]})); then
    printf '%s\n' "${only_other[@]}"
  else
    echo "(none)"
  fi
}

cpr() {
  : '
  cpr - copy files like cp, but always copy directories as whole folders.

  Usage:
    cpr [cp options] SOURCE... DEST

  Behavior:
    • Files are delegated directly to cp.
    • Directories are copied with their basename preserved, even when the source has a trailing slash.
    • Automatically adds -R when any source or destination is a real directory unless already provided.
    • Passes through common cp options (e.g., -t/--target-directory) unchanged.
  '

  local -a new_args=()
  local expect_opt_arg=""
  local options_done=0
  local need_recursive=0
  local has_recursive_opt=0

  for arg in "$@"; do
    if [[ -n "$expect_opt_arg" ]]; then
      new_args+=("$arg")
      expect_opt_arg=""
      continue
    fi

    if (( !options_done )); then
      case "$arg" in
        --)
          new_args+=("$arg")
          options_done=1
          continue
          ;;
        -t)
          new_args+=("$arg")
          expect_opt_arg="-t"
          continue
          ;;
        --target-directory)
          new_args+=("$arg")
          expect_opt_arg="--target-directory"
          continue
          ;;
        --target-directory=*)
          new_args+=("$arg")
          continue
          ;;
        --backup|--suffix|--preserve|--no-preserve|--sparse|--reflink|--context|--attributes-only)
          new_args+=("$arg")
          expect_opt_arg="$arg"
          continue
          ;;
        --backup=*|--suffix=*|--preserve=*|--no-preserve=*|--sparse=*|--reflink=*|--context=*)
          new_args+=("$arg")
          continue
          ;;
        -*)
          new_args+=("$arg")
          [[ "$arg" == *[rRaA]* ]] && has_recursive_opt=1
          continue
          ;;
      esac
    fi

    local processed="$arg"
    if [[ "$processed" != "/" ]]; then
      while [[ "$processed" != "/" && "$processed" == */ ]]; do
        processed="${processed%/}"
      done
      [[ -z "$processed" ]] && processed="$arg"
    fi

    if [[ -d "$processed" && ! -L "$processed" ]]; then
      need_recursive=1
    fi

    new_args+=("$processed")
  done

  if (( need_recursive )) && (( !has_recursive_opt )); then
    new_args=("-R" "${new_args[@]}")
  fi

  command cp "${new_args[@]}"
}


stash-overwrites-in() {
  # Stash untracked files beneath the supplied paths that would be overwritten
  # by the version tracked on <branch>. Resolves the branch (including remote
  # fallbacks), computes the intersection between untracked files and tracked
  # files at that ref, and stashes only the conflicting ones.
  local target=$1; shift
  (( $# )) || { echo "usage: stash-overwrites-in <branch> <path>..."; return 2; }

  # Resolve to a commit: try local branch/ref, then any remote/*/<branch>
  local ref
  ref=$(git rev-parse -q --verify "${target}^{commit}") \
    || ref=$(git for-each-ref --format='%(refname:short)' "refs/remotes/*/${target}" | head -n1) \
    || { echo "Can't resolve '$target'. Try: git fetch -p"; return 1; }

  # Build the overlap set under the provided paths
  mapfile -t files < <(comm -12 \
    <(git -c core.quotepath=off ls-files -o --exclude-standard -- "$@" | sort -u) \
    <(git ls-tree -r --name-only "$ref" -- "$@" | sort -u))

  ((${#files[@]})) || { echo "No conflicting untracked files under: $*"; return 0; }
  git stash push -u -- "${files[@]}"
}

merge-upstream() {
  if ! command -v gh >/dev/null 2>&1; then
    echo "merge-upstream: GitHub CLI (gh) is not on PATH" >&2
    return 127
  fi

  local origin_url upstream_url

  origin_url=$(git remote get-url origin) || return
  gh repo set-default "$origin_url"

  upstream_url=$(gh repo view --json parent --jq '"https://github.com/" + .parent.owner.login + "/" + .parent.name + ".git"') || return
  echo "Upstream is: $upstream_url"

  git remote add upstream "$upstream_url" 2>/dev/null || git remote set-url upstream "$upstream_url"
  git fetch upstream
  git merge upstream/main
}

# ---- Personal Coding-Agent Wrappers --------------------------------
# Claude Code (ccmm/cch/ccx) etc., Grok (grk), Codex (cdx*/ask_*),
# and Devin (dglm/dswe/doph/dfuox) etc. launch wrappers all live together in
# the dedicated module below.
if [[ -r "$HOME/.bash_agents" ]]; then
  . "$HOME/.bash_agents"
fi

findkeyword() {
  if [ "$#" -ne 2 ]; then
    echo "Usage: find_keyword_files <N> <keyword>"
    return 1
  fi
  local N=$1
  local keyword=$2
  local count=0

  # Recursively list all regular files, null‐delimited
  find . -type f -print0 | while IFS= read -r -d '' file; do
    # -I ignore binary, -q quiet, -i case‐insensitive
    if grep -Iqi -- "$keyword" "$file"; then
      printf '%s\n' "$file"
      count=$((count + 1))
      [ "$count" -ge "$N" ] && break
    fi
  done
}

# ---- Create new jj Workspace --------------------------------------
# usage: jj_ws_new <name> <base-rev-or-revset> [remote]
# ex:    jj_ws_new prompt_modules 'trunk()' origin
#        jj_ws_new hotfix-42 'commit_id("81c7045")' origin
#        jj_ws_new debug-old 'parents(@,3)'
#        jj_ws_new feat-login main
jj_ws_new() {
  if ! command -v jj >/dev/null 2>&1; then
    echo "jj_ws_new: jj is not on PATH" >&2
    return 127
  fi

  # ---------- help text printed to STDOUT on ANY error ----------
  read -r -d '' _USAGE <<'EOF' || true
USAGE:
  jj_ws_new <name> <base-rev-or-revset> [remote]

Creates a new jj workspace at sibling path {repo_name}_{name}, sets the new
working-copy commit's description to the base commit's subject, creates a
bookmark <name> at @, and pushes it (creating the remote bookmark if needed).

ARGS:
  name         Short bookmark/workspace name (letters/digits/dashes).
  base-rev     Any jj revset (e.g., 'trunk()', 'parents(@,3)',
               'commit_id("abc123")', 'main@origin', a Git/JJ id).
  remote       Optional Git remote (e.g., 'origin'); if omitted, jj chooses.

EXAMPLES:
  jj_ws_new prompt_modules 'trunk()' origin
  jj_ws_new hotfix-42 'commit_id("81c7045")' origin
  jj_ws_new debug-old 'parents(@,3)'
  jj_ws_new feat-login main
EOF

  _print_help() { printf "%s\n" "$_USAGE"; }

  # Trap ANY command error inside this function and print help to STDOUT
  _on_err() {
    local code=$?
    trap - ERR
    set +o errtrace 2>/dev/null || true
    echo
    _print_help
    return "$code"
  }
  set -o errtrace
  trap _on_err ERR

  # ---------- validate args ----------
  local name="${1:-}" base="${2:-}" remote="${3:-}"
  if [[ -z "$name" || -z "$base" ]]; then
    _print_help
    return 2
  fi

  # ---------- derive target path ----------
  local root reponame parent target
  root="$(jj workspace root)"                    # workspace root path (fails if not a jj repo)
  reponame="$(basename "$root")"
  parent="$(dirname "$root")"
  target="${parent}/${reponame}_${name}"
  [[ -e "$target" ]] && { echo "Refusing to overwrite: $target" >&2; _print_help; return 1; }

  # ---------- create workspace from specified base ----------
  # Each workspace is its own working copy; -r sets the parent(s) of @.
  jj workspace add -r "$base" --name "$name" "$target"

  # ---------- compute a description = first line of base commit's message ----------
  local subject
  subject="$(jj log -r "$base" -n 1 --no-graph -T 'coalesce(description.first_line(), "")' 2>/dev/null || true)"
  if [[ -z "$subject" ]]; then
    subject="$(git -C "$root" log -1 --pretty=%s "$base" 2>/dev/null || true)"
  fi
  [[ -z "$subject" ]] && subject="start ${name} from ${base}"

  # ---------- set description on @ and create bookmark ----------
  cd "$target"
  jj describe -m "$subject"                      # ensure non-empty description on tip
  jj bookmark create -r @ "$name"

  # ---------- push bookmark (create remotely if new) ----------
  if [[ -n "$remote" ]]; then
    jj git push --remote "$remote" --bookmark "$name" --allow-new
  else
    jj git push --bookmark "$name" --allow-new
  fi

  # Cleanup trap on success
  trap - ERR
  set +o errtrace 2>/dev/null || true

  printf "✓ Workspace '%s' at %s — described as: '%s' — pushed as bookmark '%s'.\n" \
         "$name" "$target" "$subject" "$name"
}


# ---- List Functions -----------------------------------------------
list_functions() {
  shopt -s extdebug
  while read -r name line file; do
    printf '%s\t%s:%s\n' "$name" "$file" "$line"
  done < <(builtin declare -F | awk '{print $3, $4, $5}')
}


# ---- Load Local Env -----------------------------------------------
load_local_env() {
    # Clear variables that might conflict
    if [ -f .env ]; then
        local had_errexit=0
        local local_vars var
        case $- in
          *e*) had_errexit=1 ;;
        esac

        # Get list of variables in local .env
        local_vars=$(grep -v '^#' .env | grep '=' | cut -d= -f1)
        for var in $local_vars; do
            [[ "$var" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] && unset "$var" 2>/dev/null
        done
        
        # Source local .env with error handling
        set +e  # Temporarily disable exit on error
        source .env 2>/dev/null
        local result=$?
        if [[ "$had_errexit" -eq 1 ]]; then
            set -e
        else
            set +e
        fi
        
        if [ $result -eq 0 ]; then
            echo "Local .env loaded, overriding global variables"
        else
            echo "Error loading .env file"
            return 1
        fi
    else
        echo "No local .env found"
    fi
}

lrun () {
  # Usage:
  #   lrun python script.py arg1 arg2 mylog.txt
  #   lrun sh install.sh install.log

  # ---- usage guard -------------------------------------------------
  if (( $# < 2 )); then
    echo "Usage: lrun <command ...> <logfile>" >&2
    return 1
  fi

  # ---- parse args --------------------------------------------------
  local logfile="${@: -1}"           # last arg = log file
  local -a cmd=( "${@:1:$#-1}" )     # all preceding args = command
  local -a linebuf=()

  if command -v gstdbuf >/dev/null 2>&1; then
    linebuf=(gstdbuf -oL)
  elif command -v stdbuf >/dev/null 2>&1; then
    linebuf=(stdbuf -oL)
  fi

  # ---- background log-writer --------------------------------------
  coproc RUNLOG { "${linebuf[@]}" cat >>"$logfile"; }

  # Duplicate the pipe's write end into a new FD that SURVIVES exec.
  # Use a fixed FD number (e.g., 3) instead of automatic assignment
  exec 3>&${RUNLOG[1]}

  # We no longer need the original cloexec-marked descriptor.
  # Use eval to properly close the FD
  eval "exec ${RUNLOG[1]}>&-"

  # ---- run the command --------------------------------------------
  "${cmd[@]}" 2>&1 | "${linebuf[@]}" tee >(cat >&3)

  # ---- cleanup -----------------------------------------------------
  exec 3>&-                # close our copy so helper sees EOF
  wait "$RUNLOG_PID"       # let coproc flush remaining data

  # Why this is non-blocking:
  # The command writes only into an in-kernel pipe buffer (64 KB by default).
  # A separate helper (cat >> logfile) performs the disk I/O.
  # Unless the disk stalls long enough to fill that 64 KB, the command never waits on the file.

  # Possible improvements:
  # - Rotate logs automatically:
  #   Replace cat >>"$logfile" with svlogd -tt "$logdir" or logger -t myapp to use existing rotation daemons.
  # - Tag lines with the PID or command name:
  #   Between tee and cat add sed "s/^/[$(basename "${cmd[0]}") $$] /"
  # - macOS without GNU stdbuf:
  #   brew install coreutils then use gstdbuf instead of stdbuf.
  # - Bash < 4 (no coproc):
  #   Use a named pipe (mkfifo) in /tmp, start the helper on that FIFO, and remove it in the cleanup section.
}


lst() {
    if ls --time-style=+"%Y-%m-%d" . >/dev/null 2>&1; then
        # GNU ls (Linux)
        ls -lt --time-style=+"%Y-%m-%d %H:%M" "${1:-.}" | awk '{print $6, $7, $8}'
    else
        # BSD ls (macOS)
        ls -lt "${1:-.}" | awk '{print $6, $7, $8, $9}'
    fi
}


clean_names() {
  # Enable empty‐glob so the loop skips if there are no files
  shopt -s nullglob

  for src in *; do
    [[ -f "$src" ]] || continue

    # strip unwanted punctuation (spaces, colons, question marks, dashes, apostrophes, commas)
    dst="$(printf "%s" "$src" | tr -d " :?,'-")"

    if [[ "$dst" != "$src" ]]; then
      # -i prompts before overwrite; remove if you want “force”
      mv -i -- "$src" "$dst" && \
        printf "Renamed: '%s' → '%s'\n" "$src" "$dst"
    fi
  done

  # restore default globbing behavior
  shopt -u nullglob
}

rspace() {
  if [ $# -lt 1 ]; then
    echo "Usage: rspace <path_to_folder>/<optional_glob_pattern>"
    return 1
  fi

  local arg
  local match
  local src
  local dir
  local base
  local dst
  local -a targets=()

  for arg in "$@"; do
    if [[ "$arg" == *[*?\[]* ]]; then
      local found=0
      while IFS= read -r match; do
        found=1
        targets+=("$match")
      done < <(compgen -G "$arg")
      if [[ $found -eq 0 ]]; then
        printf "No matches for pattern: %s\n" "$arg" >&2
      fi
      continue
    fi

    if [[ -d "$arg" ]]; then
      while IFS= read -r match; do
        targets+=("$match")
      done < <(compgen -G "$arg/*")
      continue
    fi

    targets+=("$arg")
  done

  for src in "${targets[@]}"; do
    if [[ ! -e "$src" || -d "$src" ]]; then
      continue
    fi

    dir=$(dirname -- "$src")
    base=$(basename -- "$src")
    dst="${base// /_}"

    if [[ "$dst" == "$base" ]]; then
      continue
    fi

    if [[ -e "$dir/$dst" ]]; then
      printf "Skip (target exists): '%s' -> '%s'\n" "$src" "$dir/$dst" >&2
      continue
    fi

    mv -- "$src" "$dir/$dst" && \
      printf "Renamed: '%s' -> '%s'\n" "$src" "$dir/$dst"
  done
}

av() {
  if [ -z "$1" ]; then
    echo "Usage: av <venv_name>"
    return 1
  fi

  local venv_path="$HOME/venvs/$1/bin/activate"
  if [ ! -f "$venv_path" ]; then
    echo "Error: virtualenv '$1' not found at $venv_path"
    return 1
  fi

  # source the activate script
  # shellcheck disable=SC1090
  source "$venv_path"
}

rsd() {
  if [ "$#" -ne 2 ]; then
    echo "Usage: rsd <path1> <path2>" >&2
    return 1
  fi
  rsync -au --ignore-existing "$1" "$2"
  rsync -au --ignore-existing "$2" "$1"
}

_move_if_present() {
  local src="$1"
  local dst="$2"

  if [[ -e "$src" || -L "$src" ]]; then
    mv "$src" "$dst"
  fi
}

xc() {
  _move_if_present "CLAUDE.md" "CTEMPC.md"
  _move_if_present "AGENTS.md" "ATEMPA.md"
  _move_if_present "$HOME/.claude/CLAUDE.md" "$HOME/.claude/CTEMPC.md"
  _move_if_present "$HOME/.codex/AGENTS.md" "$HOME/.codex/ATEMPA.md"
  echo "instructions backed up"
}

bf() {
  _move_if_present "CTEMPC.md" "CLAUDE.md"
  _move_if_present "ATEMPA.md" "AGENTS.md"
  _move_if_present "$HOME/.claude/CTEMPC.md" "$HOME/.claude/CLAUDE.md"
  _move_if_present "$HOME/.codex/ATEMPA.md" "$HOME/.codex/AGENTS.md"
  echo "instructions restored"
}

__mup_installed_version() {
  local cli="$1" executable="" output=""

  case "$cli" in
    claude) executable="claude" ;;
    codex) executable="codex" ;;
    antigravity) executable="agy" ;;
    devin) executable="devin" ;;
    amp) executable="amp" ;;
    grok) executable="grok" ;;
    kimi) executable="kimi" ;;
    command-code) executable="cmd" ;;
    pi) executable="pi" ;;
    cursor) executable="cursor-agent" ;;
    opencode) executable="opencode" ;;
    *) return 2 ;;
  esac

  command -v "$executable" >/dev/null 2>&1 || return 3

  case "$cli" in
    command-code)
      output=$(COMMANDCODE_SKIP_UPDATES=1 "$executable" --version 2>/dev/null) || return 1
      ;;
    *)
      output=$("$executable" --version 2>/dev/null) || return 1
      ;;
  esac

  case "$cli" in
    claude|antigravity|amp|kimi|pi|cursor)
      awk 'NR == 1 { print $1; exit }' <<<"$output"
      ;;
    command-code)
      awk '/^[0-9]/ { print $1; exit }' <<<"$output"
      ;;
    codex|opencode)
      # codex prints "codex-cli 0.x.y"; opencode v2 prints "opencode v2.x.y".
      awk 'NR == 1 { print $NF; exit }' <<<"$output"
      ;;
    devin|grok)
      awk 'NR == 1 { print $2; exit }' <<<"$output"
      ;;
  esac
}

__mup_latest_version() {
  local cli="$1" payload="" platform="" channel="" version=""

  case "$cli" in
    claude)
      curl -fsSL https://downloads.claude.ai/claude-code-releases/latest
      ;;
    codex)
      npm --loglevel=silent view @openai/codex version
      ;;
    antigravity)
      case "$(uname -s):$(uname -m)" in
        Darwin:arm64|Darwin:aarch64) platform="darwin_arm64" ;;
        Darwin:x86_64|Darwin:amd64) platform="darwin_amd64" ;;
        Linux:arm64|Linux:aarch64) platform="linux_arm64" ;;
        Linux:x86_64|Linux:amd64) platform="linux_amd64" ;;
        *) return 1 ;;
      esac
      if [[ "$platform" == linux_* ]] &&
         { [[ -f /lib/libc.musl-x86_64.so.1 || -f /lib/libc.musl-aarch64.so.1 ]] || ldd /bin/ls 2>&1 | grep -q musl; }; then
        platform="${platform}_musl"
      fi
      payload=$(curl -fsSL "https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests/${platform}.json") || return 1
      jq -er '.version | select(type == "string" and length > 0)' <<<"$payload"
      ;;
    devin)
      payload=$(curl -fsSL https://static.devin.ai/cli/current/manifest.json) || return 1
      jq -er '.version | select(type == "string" and length > 0)' <<<"$payload"
      ;;
    amp)
      curl -fsSL https://static.ampcode.com/cli/cli-version.txt
      ;;
    grok)
      if command -v grok >/dev/null 2>&1; then
        payload=$(grok update --check --json 2>/dev/null) || return 1
        jq -er '.latestVersion | select(type == "string" and length > 0)' <<<"$payload"
      else
        channel="${GROK_CHANNEL:-stable}"
        curl -fsSL "https://x.ai/cli/${channel}" 2>/dev/null ||
          curl -fsSL "https://storage.googleapis.com/grok-build-public-artifacts/cli/${channel}"
      fi
      ;;
    kimi)
      curl -fsSL https://code.kimi.com/kimi-code/latest
      ;;
    command-code)
      npm --loglevel=silent view command-code version
      ;;
    pi)
      npm --loglevel=silent view @earendil-works/pi-coding-agent version
      ;;
    cursor)
      payload=$(curl -fsSL https://cursor.com/install) || return 1
      sed -nE 's/.*\/versions\/([0-9]+\.[0-9]+\.[0-9]+-[0-9a-zA-Z._-]+).*/\1/p' <<<"$payload" | head -n 1
      ;;
    opencode)
      # v2 publishes the latest CLI version (e.g. {"version":"2.0.5",...})
      # via the update API used by the v2 installer.
      payload=$(curl -fsSL https://opencode.ai/update/api/latest/cli/npm) || return 1
      jq -er '.version | select(type == "string" and length > 0)' <<<"$payload"
      ;;
    *)
      return 2
      ;;
  esac
}

__mup_version_is_valid() {
  [[ "$1" =~ ^v?[0-9]+(\.[0-9]+){2}(-[0-9A-Za-z._-]+)?$ ]]
}

__mup_version_is_newer() {
  local current="${1#v}" latest="${2#v}" sort_command=""
  local current_key="" latest_key="" newest=""

  if command -v gsort >/dev/null 2>&1; then
    sort_command="gsort"
  elif sort -V </dev/null >/dev/null 2>&1; then
    sort_command="sort"
  else
    return 2
  fi

  # Escape the replacement tilde so Bash does not expand it to $HOME.
  current_key="${current/-/\~}"
  latest_key="${latest/-/\~}"
  newest=$(printf '%s\n%s\n' "$current_key" "$latest_key" | "$sort_command" -V | tail -n 1) || return 2
  [[ "$newest" == "$latest_key" && "$current_key" != "$latest_key" ]]
}

__mup_apply_update() {
  case "$1" in
    claude)
      if command -v claude >/dev/null 2>&1; then
        claude update
      else
        (set -o pipefail; curl -fsSL https://claude.ai/install.sh | bash)
      fi
      ;;
    codex)
      npm install -g @openai/codex@latest
      ;;
    antigravity)
      if command -v agy >/dev/null 2>&1; then
        agy update
      else
        (set -o pipefail; curl -fsSL https://antigravity.google/cli/install.sh | bash)
      fi
      ;;
    devin)
      if command -v devin >/dev/null 2>&1; then
        devin update
      else
        (set -o pipefail; curl -fsSL https://cli.devin.ai/install.sh | bash)
      fi
      ;;
    amp)
      if command -v amp >/dev/null 2>&1; then
        amp update --porcelain
      else
        (set -o pipefail; curl -fsSL https://ampcode.com/install.sh | bash)
      fi
      ;;
    grok)
      if command -v grok >/dev/null 2>&1; then
        grok update
      else
        (set -o pipefail; curl -fsSL https://x.ai/cli/install.sh | bash)
      fi
      ;;
    kimi)
      if command -v kimi >/dev/null 2>&1; then
        kimi update
      else
        (set -o pipefail; curl -fsSL https://code.kimi.com/kimi-code/install.sh | bash)
      fi
      ;;
    command-code)
      npm install -g command-code@latest
      ;;
    pi)
      npm install -g --ignore-scripts --min-release-age=0 @earendil-works/pi-coding-agent
      ;;
    hermes)
      if command -v hermes >/dev/null 2>&1; then
        hermes update -y
      else
        (set -o pipefail; curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash)
      fi
      ;;
    cursor)
      if command -v cursor-agent >/dev/null 2>&1; then
        cursor-agent update || (set -o pipefail; curl -fsSL https://cursor.com/install | bash)
      else
        (set -o pipefail; curl -fsSL https://cursor.com/install | bash)
      fi
      ;;
    opencode)
      if command -v opencode >/dev/null 2>&1; then
        opencode upgrade
      else
        (set -o pipefail; curl -fsSL https://opencode.ai/v2/install | bash)
      fi
      ;;
    *)
      return 2
      ;;
  esac
}

__mup_update_hermes() {
  local hermes_repo="$HOME/.hermes/hermes-agent"
  local hermes_head="" hermes_remote=""

  if command -v hermes >/dev/null 2>&1; then
    # hermes update is heavy (git pull + deps + rebuild + service restart),
    # so first check whether upstream main has moved past the local
    # checkout; any check failure falls through to the full update.
    if [[ -d "$hermes_repo/.git" ]] &&
      hermes_head=$(git -C "$hermes_repo" rev-parse HEAD 2>/dev/null) &&
      hermes_remote=$(git -C "$hermes_repo" ls-remote origin -h refs/heads/main 2>/dev/null | awk 'NR == 1 { print $1 }') &&
      [[ -n "$hermes_remote" ]] &&
      [[ "$hermes_head" == "$hermes_remote" ]]; then
      printf 'Hermes: up to date.\n'
      return 0
    fi
    if hermes update -y; then
      return 0
    fi
  else
    printf 'Hermes: not installed; installing.\n'
    if (set -o pipefail; curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash); then
      return 0
    fi
  fi
  printf 'Hermes: update failed.\n' >&2
  return 1
}

__mup_cleanup_hermes() {
  local pid="$1" outfile="$2"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null
    wait "$pid" 2>/dev/null
  fi
  [[ -n "$outfile" ]] && rm -f "$outfile"
}

mup() {
  local -a clis=(claude codex antigravity devin amp grok kimi command-code pi cursor opencode)
  local cli="" label="" current="" latest=""
  local current_status=0 comparison_status=0 status=0
  local hermes_out="" hermes_pid="" hermes_status=0
  local include_hermes=0 arg=""

  for arg in "$@"; do
    case "$arg" in
      --all|-a)
        include_hermes=1
        ;;
      -h|--help)
        printf 'Usage: mup [--all]\n'
        printf '  Updates AI coding agent CLIs.\n'
        printf '  --all, -a    Include Hermes agent update (off by default).\n'
        return 0
        ;;
      *)
        printf 'mup: unrecognized option %q\n' "$arg" >&2
        printf 'Usage: mup [--all]\n' >&2
        return 1
        ;;
    esac
  done

  if (( include_hermes )); then
    hermes_out=$(mktemp 2>/dev/null) || { hermes_out="/tmp/mup_hermes_$$.log"; touch "$hermes_out"; }
    __mup_update_hermes >"$hermes_out" 2>&1 &
    hermes_pid=$!
    trap '__mup_cleanup_hermes "$hermes_pid" "$hermes_out"; trap - INT TERM; return 130' INT TERM
  fi

  for cli in "${clis[@]}"; do
    case "$cli" in
      claude) label="Claude Code" ;;
      codex) label="Codex" ;;
      antigravity) label="Antigravity" ;;
      devin) label="Devin" ;;
      amp) label="Amp" ;;
      grok) label="Grok" ;;
      kimi) label="Kimi Code" ;;
      command-code) label="Command Code" ;;
      pi) label="Pi" ;;
      cursor) label="Cursor" ;;
      opencode) label="OpenCode" ;;
    esac

    if ! latest=$(__mup_latest_version "$cli"); then
      printf '%s: could not determine the latest version; skipped.\n' "$label" >&2
      status=1
      continue
    fi

    if ! __mup_version_is_valid "$latest"; then
      printf '%s: invalid latest version %q; skipped.\n' "$label" "$latest" >&2
      status=1
      continue
    fi

    if current=$(__mup_installed_version "$cli"); then
      if ! __mup_version_is_valid "$current"; then
        printf '%s: invalid installed version %q; skipped.\n' "$label" "$current" >&2
        status=1
        continue
      fi

      if [[ "${current#v}" == "${latest#v}" ]]; then
        printf '%s: up to date (%s).\n' "$label" "$current"
        continue
      fi

      if __mup_version_is_newer "$current" "$latest"; then
        comparison_status=0
      else
        comparison_status=$?
      fi
      if (( comparison_status == 1 )); then
        printf '%s: installed version %s is newer than published version %s; skipped.\n' "$label" "$current" "$latest"
        continue
      elif (( comparison_status != 0 )); then
        printf '%s: could not compare versions %s and %s; skipped.\n' "$label" "$current" "$latest" >&2
        status=1
        continue
      fi

      printf '%s: updating %s -> %s.\n' "$label" "$current" "$latest"
    else
      current_status=$?
      if (( current_status != 3 )); then
        printf '%s: could not determine the installed version; skipped.\n' "$label" >&2
        status=1
        continue
      fi
      printf '%s: not installed; installing %s.\n' "$label" "$latest"
    fi

    if ! __mup_apply_update "$cli"; then
      printf '%s: update failed.\n' "$label" >&2
      status=1
    fi
  done

  if [[ -n "$hermes_pid" ]]; then
    wait "$hermes_pid" || hermes_status=$?
    trap - INT TERM
    if [[ -s "$hermes_out" ]]; then
      cat "$hermes_out"
    fi
    rm -f "$hermes_out"
    if (( hermes_status != 0 )); then
      status=1
    fi
  fi

  return "$status"
}
