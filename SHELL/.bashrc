[[ -n "$BASH_VERSION" ]] || return 0 2>/dev/null || exit 0

if [[ -z "${JEFF_BASH_ENV_LOADED:-}" && -f "$HOME/.bash_profile" ]]; then
  export JEFF_BASH_SKIP_RC=1
  . "$HOME/.bash_profile"
  unset JEFF_BASH_SKIP_RC
fi

case $- in
  *i*) ;;
  *) return ;;
esac

__bashrc_source_if_exists() {
  local file_path="$1"
  [[ -f "$file_path" ]] && . "$file_path"
}

set +e
set +u

export ENABLE_BACKGROUND_TASKS=1
export CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1
export FORCE_AUTO_BACKGROUND_TASKS=true
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=true
export CLAUDE_CODE_ENABLE_UNIFIED_READ_TOOL=1
export ENABLE_DEBUG_LOGS=1

if [[ -n "$TMUX" ]] && command -v tmux >/dev/null 2>&1; then
  tmux source-file "$HOME/.tmux.conf" 2>/dev/null
fi

[[ -t 0 ]] && stty -ixon
shopt -s histappend globstar

HISTSIZE=8000
HISTFILESIZE=99999

alias zn='zed -n'
alias gs="git status"
alias ga="git add -u"
alias prompt="plans-prompt"

__bashrc_source_if_exists "$HOME/.bash_git_helpers"
__bashrc_source_if_exists "$HOME/.bash_aliases"
__bashrc_source_if_exists "$HOME/.bash_functions"

if ! declare -p BASH_COMPLETION_VERSINFO >/dev/null 2>&1; then
  __bashrc_source_if_exists "${HOMEBREW_PREFIX:-/opt/homebrew}/etc/profile.d/bash_completion.sh"
fi

__bashrc_source_if_exists "${HOMEBREW_PREFIX:-/opt/homebrew}/opt/nvm/etc/bash_completion.d/nvm"
__bashrc_source_if_exists "${HOMEBREW_PREFIX:-/opt/homebrew}/opt/chruby/share/chruby/chruby.sh"
__bashrc_source_if_exists "${HOMEBREW_PREFIX:-/opt/homebrew}/opt/chruby/share/chruby/auto.sh"
__bashrc_source_if_exists "$HOME/.git-completion.bash"
__bashrc_source_if_exists "$HOME/google-cloud-sdk/completion.bash.inc"

shopt -s nullglob
for completion_file in "$HOME"/.bash_completions/*; do
  [[ -f "$completion_file" ]] && . "$completion_file"
done
shopt -u nullglob

if [[ "$TERM_PROGRAM" == "vscode" ]]; then
  trap - EXIT
fi

if [[ "$TERM" != "dumb" ]] && command -v starship >/dev/null 2>&1; then
  eval "$(starship init bash)"
else
  PS1='\[\033[1;33m\]\W\[\033[0m\] $ '
fi

unset -f __bashrc_source_if_exists


# Added by Antigravity CLI installer
export PATH="@HOME@/.local/bin:$PATH"
export UV_PYTHON=3.13.16


















# kimi-code
export PATH="@HOME@/.kimi-code/bin:$PATH"























# >>> grok installer >>>
export PATH="$HOME/.grok/bin:$PATH"
[[ -r "$HOME/.grok/completions/bash/grok.bash" ]] && source "$HOME/.grok/completions/bash/grok.bash"
# <<< grok installer <<<

# opencode
export PATH=@HOME@/.opencode/bin:$PATH
