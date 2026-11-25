# shellcheck shell=bash
# Source-only parsing and environment bridge for review-after-commit launchers.

_review_after_commit_error() {
  printf 'review-after-commit: %s\n' "$*" >&2
}

_review_after_commit_positive_integer() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

review_after_commit_parse() {
  if [[ $# -lt 3 ]]; then
    _review_after_commit_error "parse requires HOST SELECTION_NAME FORWARDED_NAME"
    return 2
  fi
  local host="$1" selection_name="$2" forwarded_name="$3"
  shift 3
  case "$host" in
    codex|kimi|antigravity) ;;
    *) _review_after_commit_error "unsupported host '$host'"; return 2 ;;
  esac

  local -n _review_selection="$selection_name"
  local -n _review_forwarded="$forwarded_name"
  _review_selection=()
  _review_forwarded=()

  local mode="" legacy_hook="" option="" standard_every="" branch_every=""
  local mode_seen="no" hook_seen="no" saw_profile="no" saw_print="no"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --)
        _review_forwarded+=("$@")
        set --
        ;;
      --review-mode)
        [[ $# -ge 2 ]] || {
          _review_after_commit_error "--review-mode requires a value"
          return 2
        }
        [[ "$mode_seen" == "no" ]] || {
          _review_after_commit_error "--review-mode may be specified only once"
          return 2
        }
        mode_seen="yes"
        mode="$2"
        shift 2
        ;;
      --review-mode=*)
        [[ "$mode_seen" == "no" ]] || {
          _review_after_commit_error "--review-mode may be specified only once"
          return 2
        }
        mode_seen="yes"
        mode="${1#--review-mode=}"
        shift
        ;;
      --review-standard-every)
        [[ $# -ge 2 ]] || {
          _review_after_commit_error "--review-standard-every requires a value"
          return 2
        }
        [[ -z "$standard_every" ]] || {
          _review_after_commit_error "standard-every may be specified only once"
          return 2
        }
        standard_every="$2"
        shift 2
        ;;
      --review-standard-every=*)
        [[ -z "$standard_every" ]] || {
          _review_after_commit_error "standard-every may be specified only once"
          return 2
        }
        standard_every="${1#--review-standard-every=}"
        shift
        ;;
      --review-branch-every)
        [[ $# -ge 2 ]] || {
          _review_after_commit_error "--review-branch-every requires a value"
          return 2
        }
        [[ -z "$branch_every" ]] || {
          _review_after_commit_error "branch-every may be specified only once"
          return 2
        }
        branch_every="$2"
        shift 2
        ;;
      --review-branch-every=*)
        [[ -z "$branch_every" ]] || {
          _review_after_commit_error "branch-every may be specified only once"
          return 2
        }
        branch_every="${1#--review-branch-every=}"
        shift
        ;;
      --hook)
        [[ $# -ge 2 ]] || {
          _review_after_commit_error "--hook requires a value"
          return 2
        }
        [[ "$hook_seen" == "no" ]] || {
          _review_after_commit_error "--hook may be specified only once"
          return 2
        }
        hook_seen="yes"
        legacy_hook="$2"
        shift 2
        ;;
      --hook=*)
        [[ "$hook_seen" == "no" ]] || {
          _review_after_commit_error "--hook may be specified only once"
          return 2
        }
        hook_seen="yes"
        legacy_hook="${1#--hook=}"
        shift
        ;;
      --hook-option)
        [[ $# -ge 2 ]] || {
          _review_after_commit_error "--hook-option requires key=value"
          return 2
        }
        option="$2"
        shift 2
        case "$option" in
          standard-every=*)
            [[ -z "$standard_every" ]] || {
              _review_after_commit_error "standard-every may be specified only once"
              return 2
            }
            standard_every="${option#standard-every=}"
            ;;
          branch-every=*)
            [[ -z "$branch_every" ]] || {
              _review_after_commit_error "branch-every may be specified only once"
              return 2
            }
            branch_every="${option#branch-every=}"
            ;;
          *)
            _review_after_commit_error "unsupported hook option '$option'"
            return 2
            ;;
        esac
        ;;
      --hook-option=*)
        option="${1#--hook-option=}"
        shift
        case "$option" in
          standard-every=*)
            [[ -z "$standard_every" ]] || {
              _review_after_commit_error "standard-every may be specified only once"
              return 2
            }
            standard_every="${option#standard-every=}"
            ;;
          branch-every=*)
            [[ -z "$branch_every" ]] || {
              _review_after_commit_error "branch-every may be specified only once"
              return 2
            }
            branch_every="${option#branch-every=}"
            ;;
          *)
            _review_after_commit_error "unsupported hook option '$option'"
            return 2
            ;;
        esac
        ;;
      -p|--profile|--profile=*|-p?*)
        [[ "$host" == "codex" ]] && saw_profile="yes"
        [[ "$host" == "kimi" ]] && saw_print="yes"
        _review_forwarded+=("$1")
        shift
        ;;
      --prompt|--prompt=*)
        [[ "$host" == "kimi" ]] && saw_print="yes"
        _review_forwarded+=("$1")
        shift
        ;;
      *)
        _review_forwarded+=("$1")
        shift
        ;;
    esac
  done

  if [[ "$hook_seen" == "yes" ]]; then
    [[ "$legacy_hook" == "review-after-commit" ]] || {
      _review_after_commit_error "unsupported hook '$legacy_hook'"
      return 2
    }
    [[ "$mode_seen" == "no" ]] || {
      _review_after_commit_error "use either --review-mode or the legacy --hook spelling"
      return 2
    }
    mode="cadence"
    mode_seen="yes"
  fi
  if [[ "$mode_seen" == "no" ]]; then
    [[ -z "$standard_every" && -z "$branch_every" ]] || {
      _review_after_commit_error "review cadence options require --review-mode"
      return 2
    }
    _review_selection[enabled]="0"
    _review_selection[mode]=""
    _review_selection[standard_every]=""
    _review_selection[branch_every]=""
    return 0
  fi
  case "$mode" in
    cadence|auto) ;;
    *) _review_after_commit_error "review mode must be cadence or auto"; return 2 ;;
  esac
  if [[ "$mode" == "auto" && ( -n "$standard_every" || -n "$branch_every" ) ]]; then
    _review_after_commit_error "every-N cadence options are invalid in auto mode"
    return 2
  fi
  if [[ -n "$standard_every" ]] && ! _review_after_commit_positive_integer "$standard_every"; then
    _review_after_commit_error "standard-every must be a positive integer"
    return 2
  fi
  if [[ -n "$branch_every" ]] && ! _review_after_commit_positive_integer "$branch_every"; then
    _review_after_commit_error "branch-every must be a positive integer"
    return 2
  fi
  if [[ "$host" == "codex" && "$saw_profile" == "yes" ]]; then
    _review_after_commit_error "review mode cannot be combined with -p/--profile"
    return 2
  fi
  if [[ "$host" == "kimi" && "$saw_print" == "yes" ]]; then
    _review_after_commit_error "review mode is supported only for interactive Kimi launches"
    return 2
  fi

  _review_selection[enabled]="1"
  _review_selection[mode]="$mode"
  _review_selection[standard_every]="$standard_every"
  _review_selection[branch_every]="$branch_every"
}

review_after_commit_export_environment() {
  if [[ $# -ne 3 ]]; then
    _review_after_commit_error "environment export requires HOST HOME SELECTION_NAME"
    return 2
  fi
  local host="$1" selected_home="$2" selection_name="$3"
  local -n _review_selection="$selection_name"

  unset REVIEW_AFTER_COMMIT_MODE
  unset CODEX_HOOK_STATE_DIR CODEX_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY
  unset CODEX_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY
  unset KIMI_HOOK_STATE_DIR KIMI_HOOK_REVIEW_AFTER_COMMIT_ENABLED
  unset KIMI_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY
  unset KIMI_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY
  unset ANTIGRAVITY_HOOK_STATE_DIR
  unset ANTIGRAVITY_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY
  unset ANTIGRAVITY_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY
  [[ "${_review_selection[enabled]:-0}" == "1" ]] || return 0

  export REVIEW_AFTER_COMMIT_MODE="${_review_selection[mode]}"
  case "$host" in
    codex)
      export CODEX_HOOK_STATE_DIR="${selected_home}/hook-state/review-after-commit"
      [[ -z "${_review_selection[standard_every]}" ]] || export CODEX_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY="${_review_selection[standard_every]}"
      [[ -z "${_review_selection[branch_every]}" ]] || export CODEX_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY="${_review_selection[branch_every]}"
      ;;
    kimi)
      export KIMI_HOOK_REVIEW_AFTER_COMMIT_ENABLED=1
      export KIMI_HOOK_STATE_DIR="${selected_home}/hook-state/review-after-commit"
      [[ -z "${_review_selection[standard_every]}" ]] || export KIMI_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY="${_review_selection[standard_every]}"
      [[ -z "${_review_selection[branch_every]}" ]] || export KIMI_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY="${_review_selection[branch_every]}"
      ;;
    antigravity)
      export ANTIGRAVITY_HOOK_STATE_DIR="${selected_home}/hook-state/review-after-commit"
      [[ -z "${_review_selection[standard_every]}" ]] || export ANTIGRAVITY_HOOK_REVIEW_AFTER_COMMIT_STANDARD_EVERY="${_review_selection[standard_every]}"
      [[ -z "${_review_selection[branch_every]}" ]] || export ANTIGRAVITY_HOOK_REVIEW_AFTER_COMMIT_BRANCH_EVERY="${_review_selection[branch_every]}"
      ;;
    *) _review_after_commit_error "unsupported host '$host'"; return 2 ;;
  esac
}

review_after_commit_bundle_path() {
  if [[ $# -ne 2 ]]; then
    _review_after_commit_error "bundle path requires HOST CANONICAL_HOME"
    return 2
  fi
  case "$1" in
    codex|kimi)
      printf '%s/hooks/review-after-commit\n' "${2%/}"
      ;;
    antigravity)
      printf '%s/plugins/review-after-commit\n' "${2%/}"
      ;;
    *)
      _review_after_commit_error "unsupported host '$1'"
      return 2
      ;;
  esac
}

review_after_commit_append_kimi_config() {
  [[ $# -eq 0 ]] || {
    _review_after_commit_error "Kimi config rendering accepts no arguments"
    return 2
  }
  cat <<'EOF'

[[hooks]]
event = "PreToolUse"
matcher = "^Bash$"
command = 'exec /usr/bin/python3 -B "$KIMI_CODE_HOME/hooks/review-after-commit/hosts/kimi/adapter.py"'
timeout = 30

[[hooks]]
event = "Stop"
command = 'exec /usr/bin/python3 -B "$KIMI_CODE_HOME/hooks/review-after-commit/hosts/kimi/adapter.py"'
timeout = 30
EOF
}

review_after_commit_dispatch() {
  [[ $# -ge 1 ]] || {
    _review_after_commit_error "dispatch requires an operation"
    return 2
  }
  local operation="$1"
  shift
  case "$operation" in
    parse) review_after_commit_parse "$@" ;;
    export-environment) review_after_commit_export_environment "$@" ;;
    bundle-path) review_after_commit_bundle_path "$@" ;;
    append-kimi-config) review_after_commit_append_kimi_config "$@" ;;
    *)
      _review_after_commit_error "unsupported dispatch operation '$operation'"
      return 2
      ;;
  esac
}
