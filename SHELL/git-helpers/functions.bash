# Git helper implementations. Public names match registry.tsv.
# Sourced by dispatch.bash; not intended to be sourced directly.

__git_default_base() {
    local base=""
    base=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
    [ -n "$base" ] || base="main"
    printf '%s\n' "$base"
}

__git_top_files() {
    local commit="$1" top_n="$2"
    git diff-tree --numstat -r "$commit" 2>/dev/null | \
        awk -v n="$top_n" '{
            a=($1=="-"?0:$1); d=($2=="-"?0:$2); t=a+d
            printf "%d\t%d\t%d\t%s\n",t,a,d,$3
        }' | sort -t$'\t' -k1,1nr | head -n "$top_n" | \
        while IFS=$'\t' read -r t a d f; do
            printf "    %s (+%s/-%s)\n" "$f" "$a" "$d"
        done
}

# gac: Stage all updated/deleted files (`git add -u`), commit with the provided message, and push.
gac() {
    git add -u && git commit -m "$1" && git push
}

# gad: Stage all updated/deleted and untracked files (`git add .`), commit with the provided message, and push.
gad() {
    git add . && git commit -m "$1" && git push
}

# gcm: Commit staged changes with the supplied message and push.
gcm() {
    if [ -z "$1" ]; then
      echo "Error: Commit message argument is required" >&2
      return 1
    fi
    git commit -m "$*" && git push
}

# gcf: Stage (default -u), commit with message from file, push.
gcf() {
  local add_arg="${1:--u}"
  if [ -z "$1" ]; then
    echo "Only committing modified/tracked files (git add -u)"
  fi
  if [ ! -f "$2" ]; then
    echo "Error: commit message file is required and must be a valid file" >&2
    return 1
  fi
  git add "$add_arg" && git commit -F "$2" && git push
}

# gbs: List remote branches ordered by most recent commit date. Optional numeric limit.
gbs() {
    local num=$1
    if [ -n "$num" ]; then
      git for-each-ref --sort=committerdate --format="%(refname:short)" refs/remotes | tail -n "$num"
    else
      git for-each-ref --sort=committerdate --format="%(refname:short)" refs/remotes
    fi
}

# gflog: Full commit history for a file across all branches, following renames, chronological.
gflog() {
    if [ -z "$1" ]; then
      echo "Usage: gflog <file>"
      return 1
    fi
    git log --all --follow --pretty=format:"%ad %h %s" --date=short --reverse -- "$1"
}

# gdel: Delete a local branch merged into the default base, and its remote counterpart.
gdel() {
    local branch="$1"
    local base
    if [ -z "$branch" ]; then
      echo "Usage: gdel <branch>" >&2
      return 1
    fi
    base=$(__git_default_base)
    if git branch --merged "$base" | grep -q "\b$branch\b"; then
      git branch -d "$branch" && git push origin --delete "$branch"
    else
      echo "Branch '$branch' is not merged into $base."
    fi
}

glda() {
  git log --pretty=format:"%h %ar %s" | head -n 30
}

gmm() {
  local base
  base=$(__git_default_base)
  git fetch origin "$base" && git merge "origin/$base"
}

grr() {
  local base
  base=$(__git_default_base)
  git fetch origin "$base" && git rebase "origin/$base"
  echo "Rebased successfully; push with git push --force-with-lease when ready."
}

# glo: Concise, colorised git log graph with decorations.
glo() {
    local num=3
    if [ $# -gt 0 ] && [ "$1" -eq "$1" ] 2>/dev/null; then
      num=$1
    fi
    git log --graph --decorate --color=always -n "$num" \
      --date=format:'%y%m%d-%H%M' \
      --pretty=format:"%C(auto)%h%d %C(dim)%ad%Creset %s %C(dim)– %an%Creset"
}

# gln: Unique file names changed in the last N commits (default 5). Optional glob filter.
gln() {
    local n=5
    if [ $# -gt 0 ] && [ "$1" -eq "$1" ] 2>/dev/null; then
      n=$1; shift
    fi
    local glob="${1:-}"
    local files
    files=$(git log --name-only --pretty=format: "HEAD~${n}..HEAD" | sort -u | sed '/^$/d')
    if [ -n "$glob" ]; then
      while IFS= read -r f; do
        [[ "$f" == $glob ]] && printf '%s\n' "$f"
      done <<< "$files"
    else
      printf '%s\n' "$files"
    fi
}

# glb: Concise, colorised git log graph for current branch only (vs base).
glb() {
    local num=3
    if [ $# -gt 0 ] && [ "$1" -eq "$1" ] 2>/dev/null; then
      num=$1; shift
    fi
    local base="${1:-}"
    if [ -z "$base" ]; then
      base=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@')
      [ -z "$base" ] && base="main"
    fi
    git log --oneline --graph --decorate --color=always --first-parent --no-merges -n "$num" "${base}..HEAD"
}

# glf: Commit history for a specific file (glb-style).
glf() {
    local num=10
    if [ $# -gt 0 ] && [ "$1" -eq "$1" ] 2>/dev/null; then
      num=$1; shift
    fi
    local file="${1:?usage: glf [num] <file>}"
    git log --oneline --graph --decorate --color=always --first-parent --no-merges -n "$num" -- "$file"
}

glfp() {
    local num=3
    if [ $# -gt 0 ] && [ "$1" -eq "$1" ] 2>/dev/null; then
      num=$1
    fi

    git log --first-parent \
      --graph --decorate --color=always -n "$num" \
      --pretty=format:"%C(auto)%h%d %s %C(dim)– %an%Creset"
}

# glof: like glo but shows top N modified files per commit
glof() {
    local num=3 top_n=3
    [ $# -gt 0 ] && [ "$1" -eq "$1" ] 2>/dev/null && { num=$1; shift; }
    [ $# -gt 0 ] && [ "$1" -eq "$1" ] 2>/dev/null && { top_n=$1; }
    git log --format="%H" -n "$num" | while read -r hash; do
        git log --oneline --graph --decorate --color=always -n 1 "$hash"
        __git_top_files "$hash" "$top_n"
    done
}

# glbf: like glb but shows top N modified files per commit on the current branch
glbf() {
    local num=3 top_n=3 base
    [ $# -gt 0 ] && [ "$1" -eq "$1" ] 2>/dev/null && { num=$1; shift; }
    [ $# -gt 0 ] && [ "$1" -eq "$1" ] 2>/dev/null && { top_n=$1; shift; }
    base="${1:-$(__git_default_base)}"
    git log --format="%H" --first-parent --no-merges "${base}..HEAD" -n "$num" | while read -r hash; do
        git log --oneline --graph --decorate --color=always -n 1 "$hash"
        __git_top_files "$hash" "$top_n"
    done
}

# glox: git log --oneline for included paths, excluding commits that only touch excluded folders.
# Usage: glox -i <include-path>... [-x <exclude-folder>...]
glox() {
  local mode=""
  local arg=""
  local changed_file=""
  local exclude=""
  local is_excluded=0
  local keep=0
  local hash=""
  local -a includes=()
  local -a excludes=()

  while [ $# -gt 0 ]; do
    case "$1" in
      -i|--include)
        mode="include"
        shift
        ;;
      -x|--exclude)
        mode="exclude"
        shift
        ;;
      -h|--help)
        echo "Usage: glox -i <include-path>... [-x <exclude-folder>...]"
        return 0
        ;;
      -*)
        echo "Error: unknown option: $1" >&2
        echo "Usage: glox -i <include-path>... [-x <exclude-folder>...]" >&2
        return 1
        ;;
      *)
        arg="${1#./}"
        case "$mode" in
          include)
            includes+=("$arg")
            ;;
          exclude)
            excludes+=("${arg%/}")
            ;;
          *)
            echo "Error: specify -i before include paths or -x before exclude folders" >&2
            echo "Usage: glox -i <include-path>... [-x <exclude-folder>...]" >&2
            return 1
            ;;
        esac
        shift
        ;;
    esac
  done

  if [ ${#includes[@]} -eq 0 ]; then
    echo "Error: at least one include path is required" >&2
    echo "Usage: glox -i <include-path>... [-x <exclude-folder>...]" >&2
    return 1
  fi

  git log --format="%H" -- "${includes[@]}" | while read -r hash; do
    keep=0

    if [ ${#excludes[@]} -eq 0 ]; then
      keep=1
    else
      while IFS= read -r changed_file; do
        [ -z "$changed_file" ] && continue
        is_excluded=0

        for exclude in "${excludes[@]}"; do
          case "$changed_file" in
            "$exclude"|"$exclude"/*)
              is_excluded=1
              break
              ;;
          esac
        done

        if [ "$is_excluded" -eq 0 ]; then
          keep=1
          break
        fi
      done <<< "$(git diff-tree --root --no-commit-id --name-only -r "$hash" -- "${includes[@]}")"
    fi

    if [ "$keep" -eq 1 ]; then
      git log --oneline -n 1 "$hash"
    fi
  done
}

# ltb: list large blobs introduced in the current branch
# TODO add optional flag for size threshold
ltb() {
  git rev-list --objects origin/main..HEAD \
  | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | awk '$1=="blob" && $3 > 1048576 {printf "%.2f MB\t%s\n", $3/1048576, $4}' \
  | sort -nr

  # save to file - TODO should add a flag to control this and provide a path
  git rev-list --objects origin/main..HEAD \
  | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | awk '$1=="blob" && $3 > 1048576 {print $4}' \
  | sort -u > /tmp/large-files-to-strip.txt
}

# shellcheck source=navigation.bash
. "$_GH_DIR/navigation.bash"
