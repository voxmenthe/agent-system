[[ -n "${BASH_VERSION:-}" ]] || return 0 2>/dev/null || exit 0

__bashcfg_source_if_exists() {
  local file_path="$1"
  [[ -f "$file_path" ]] && . "$file_path"
}

__bashcfg_dedupe_colon_var() {
  local var_name="$1"
  local current_value="${!var_name-}"
  local entry deduped_value=""
  local old_ifs="$IFS"

  IFS=':'
  for entry in $current_value; do
    [[ -n "$entry" ]] || continue
    case ":$deduped_value:" in
      *":$entry:"*) ;;
      *) deduped_value="${deduped_value:+$deduped_value:}$entry" ;;
    esac
  done
  IFS="$old_ifs"

  printf -v "$var_name" '%s' "$deduped_value"
}

__bashcfg_path_remove() {
  local path_entry="$1"
  local current_path="${PATH-}"
  local path_segment new_path=""
  local old_ifs="$IFS"

  [[ -n "$path_entry" ]] || return 0

  IFS=':'
  for path_segment in $current_path; do
    [[ -n "$path_segment" && "$path_segment" != "$path_entry" ]] || continue
    new_path="${new_path:+$new_path:}$path_segment"
  done
  IFS="$old_ifs"

  PATH="$new_path"
}

__bashcfg_path_prepend() {
  local path_entry="$1"
  [[ -n "$path_entry" && -d "$path_entry" ]] || return 0

  __bashcfg_path_remove "$path_entry"
  PATH="$path_entry${PATH:+:$PATH}"
}

__bashcfg_path_append() {
  local path_entry="$1"
  [[ -n "$path_entry" && -d "$path_entry" ]] || return 0

  __bashcfg_path_remove "$path_entry"
  PATH="${PATH:+$PATH:}$path_entry"
}

__bashcfg_prepend_word_var() {
  local var_name="$1"
  local word="$2"
  local current_value="${!var_name-}"
  local token new_value=""

  [[ -n "$word" ]] || return 0

  for token in $current_value; do
    [[ "$token" == "$word" ]] && continue
    new_value="${new_value:+$new_value }$token"
  done

  printf -v "$var_name" '%s' "$word${new_value:+ $new_value}"
}

__bashcfg_export_default() {
  local var_name="$1"
  local default_value="$2"

  if [[ -z "${!var_name-}" ]]; then
    printf -v "$var_name" '%s' "$default_value"
  fi

  export "$var_name"
}

__bashcfg_load_exported_env_file() {
  local env_file="$1"
  local previous_options source_status

  [[ -r "$env_file" ]] || return 0

  previous_options=$(set +o)
  set -a
  set +e
  . "$env_file" 2>/dev/null
  source_status=$?
  eval "$previous_options"

  if (( source_status != 0 )); then
    printf 'Warning: failed to source %s\n' "$env_file" >&2
  fi
}

# Homebrew is under /opt/homebrew on Apple silicon and /usr/local on Intel.
# shellenv prints nothing when its PATH entries already lead, so the prefix
# the rest of this file (and .bashrc) uses comes from the brew found here.
for __bashcfg_brew in /opt/homebrew/bin/brew /usr/local/bin/brew; do
  if [[ -x "$__bashcfg_brew" ]]; then
    eval "$("$__bashcfg_brew" shellenv)"
    export HOMEBREW_PREFIX="${__bashcfg_brew%/bin/brew}"
    break
  fi
done

__bashcfg_source_if_exists "$HOME/.local/bin/env"

# This machine's own settings (cache locations, extra PATH entries). Its
# exports win over the defaults below. Sync never writes it; see
# SHELL/shell.local.example.sh in the agent-system checkout.
__bashcfg_source_if_exists "$HOME/.config/agent-system/shell.local.sh"

# OpenSSL clients need the maintained CA bundle, separate from macOS trust.
if [[ -n "${HOMEBREW_PREFIX:-}" && -f "$HOMEBREW_PREFIX/etc/ca-certificates/cert.pem" ]]; then
  __bashcfg_export_default SSL_CERT_FILE "$HOMEBREW_PREFIX/etc/ca-certificates/cert.pem"
fi

__bashcfg_export_default PYENV_ROOT "$HOME/.pyenv"
__bashcfg_export_default LM_STUDIO_API_KEY "dummy-api-key"
__bashcfg_export_default LM_STUDIO_API_BASE "http://localhost:1234/v1"

# Caches (HF_HOME, TORCH_HOME, UV_CACHE_DIR, PIP_CACHE_DIR, SGREP_CACHE_DIR, ...)
# stay in each tool's default location unless shell.local.sh moves them.
# sgrep drops any index that doesn't fit this total; the default 256 MiB can't hold a large repo's index.
__bashcfg_export_default SGREP_CACHE_MAX_BYTES "8589934592"
__bashcfg_export_default HF_XET_HIGH_PERFORMANCE "1"
__bashcfg_export_default TOKENIZERS_PARALLELISM "true"
__bashcfg_export_default COPYFILE_DISABLE "1"
__bashcfg_export_default NVM_DIR "$HOME/.nvm"
__bashcfg_export_default PNPM_HOME "$HOME/Library/pnpm"

if [[ -x "$HOME/.local/ffmpeg/bin/ffmpeg" ]]; then
  export FFMPEG_BIN="$HOME/.local/ffmpeg/bin/ffmpeg"
fi

if [[ -n "${HOMEBREW_PREFIX:-}" && -d "$HOMEBREW_PREFIX/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home" ]]; then
  __bashcfg_export_default JAVA_HOME "$HOMEBREW_PREFIX/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home"
elif [[ -n "${HOMEBREW_PREFIX:-}" && -d "$HOMEBREW_PREFIX/opt/openjdk/libexec/openjdk.jdk/Contents/Home" ]]; then
  __bashcfg_export_default JAVA_HOME "$HOMEBREW_PREFIX/opt/openjdk/libexec/openjdk.jdk/Contents/Home"
fi

__bashcfg_path_prepend "$PYENV_ROOT/bin"

if command -v pyenv >/dev/null 2>&1; then
  if __bashcfg_pyenv_init="$(pyenv init - --no-rehash 2>/dev/null)"; then
    eval "$__bashcfg_pyenv_init"
  else
    eval "$(pyenv init -)"
  fi
fi

if [[ -n "${HOMEBREW_PREFIX:-}" ]]; then
  __bashcfg_brew_prefix="$(brew --prefix 2>/dev/null)"
  if [[ -n "$__bashcfg_brew_prefix" ]]; then
    __bashcfg_source_if_exists "$__bashcfg_brew_prefix/etc/bash_completion"
    __bashcfg_source_if_exists "$__bashcfg_brew_prefix/etc/profile.d/bash_completion.sh"
  fi
fi

__bashcfg_source_if_exists "$HOME/.cargo/env"
__bashcfg_source_if_exists "$HOME/google-cloud-sdk/path.bash.inc"
[[ -n "${HOMEBREW_PREFIX:-}" ]] && __bashcfg_source_if_exists "$HOMEBREW_PREFIX/opt/nvm/nvm.sh"

__bashcfg_load_exported_env_file "$HOME/.api_keys"
__bashcfg_load_exported_env_file "$HOME/.env"

if [[ -n "${HOMEBREW_PREFIX:-}" ]]; then
  if __bashcfg_opus_prefix="$(brew --prefix opus 2>/dev/null)" && __bashcfg_libvpx_prefix="$(brew --prefix libvpx 2>/dev/null)"; then
    __bashcfg_dedupe_colon_var PKG_CONFIG_PATH
    PKG_CONFIG_PATH="${__bashcfg_opus_prefix}/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
    PKG_CONFIG_PATH="${__bashcfg_libvpx_prefix}/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"

    __bashcfg_prepend_word_var CPPFLAGS "-I${__bashcfg_libvpx_prefix}/include"
    __bashcfg_prepend_word_var CPPFLAGS "-I${__bashcfg_opus_prefix}/include"
    __bashcfg_prepend_word_var LDFLAGS "-L${__bashcfg_libvpx_prefix}/lib"
    __bashcfg_prepend_word_var LDFLAGS "-L${__bashcfg_opus_prefix}/lib"

    export PKG_CONFIG_PATH CPPFLAGS LDFLAGS
  fi
fi

__bashcfg_path_append "$HOME/.lmstudio/bin"
__bashcfg_path_append "$PNPM_HOME"
if [[ -n "${JAVA_HOME:-}" ]]; then
  __bashcfg_path_prepend "$JAVA_HOME/bin"
fi
__bashcfg_path_prepend "/usr/local/opt/curl/bin"
__bashcfg_path_prepend "$HOME/.codeium/windsurf/bin"
# __bashcfg_path_prepend "/Library/Frameworks/Python.framework/Versions/3.13/bin"
__bashcfg_path_prepend "$HOME/.local/ffmpeg/bin"
__bashcfg_path_prepend "$HOME/.antigravity/antigravity/bin"
__bashcfg_path_prepend "$HOME/.local/bin"

__bashcfg_dedupe_colon_var PATH
if command -v manpath >/dev/null 2>&1; then
  __bashcfg_default_manpath="$(MANPATH= manpath 2>/dev/null)"
  if [[ -n "$__bashcfg_default_manpath" ]]; then
    MANPATH="$__bashcfg_default_manpath"
  fi
fi
__bashcfg_dedupe_colon_var MANPATH
export PATH MANPATH
hash -r

export JEFF_BASH_ENV_LOADED=1

if [[ -z "${JEFF_BASH_SKIP_RC:-}" && $- == *i* ]]; then
  __bashcfg_source_if_exists "$HOME/.bashrc"
fi

unset __bashcfg_brew __bashcfg_opus_prefix __bashcfg_libvpx_prefix __bashcfg_default_manpath __bashcfg_brew_prefix __bashcfg_pyenv_init
unset -f __bashcfg_source_if_exists
unset -f __bashcfg_dedupe_colon_var
unset -f __bashcfg_path_remove
unset -f __bashcfg_path_prepend
unset -f __bashcfg_path_append
unset -f __bashcfg_prepend_word_var
unset -f __bashcfg_export_default
unset -f __bashcfg_load_exported_env_file
