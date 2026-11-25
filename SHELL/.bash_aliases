# Agent CLI shortcuts
# Kimi routing disabled: use Claude Code's Anthropic subscription login.
# if [[ -x "$HOME/.tmux/claude_kimi_interactive.sh" ]]; then
#   alias claude="$HOME/.tmux/claude_kimi_interactive.sh"
#   alias ccdk="$HOME/.tmux/claude_kimi_interactive.sh --dangerously-skip-permissions"
# fi
# Also remove aliases left in a shell when this file is sourced again.
unalias claude ccdk 2>/dev/null || true

if command -v claude >/dev/null 2>&1; then
  alias ccdp='claude --dangerously-skip-permissions -p '
fi

if command -v gemini >/dev/null 2>&1; then
  alias geminip='gemini --yolo -p '
fi

# demos folder handling
alias din='echo "demos/" >> .gitignore && tail .gitignore'
alias dout="sed -i '' '/demos\//d' .gitignore && tail .gitignore"

# starship config toggles
starmax() {
  export STARSHIP_CONFIG="$HOME/.config/starship.toml"
}

starmin() {
  export STARSHIP_CONFIG="$HOME/.config/starship-min.toml"
}

if [[ -x "$HOME/.tmux/three_pane_horizontal_launch.sh" ]]; then
  alias tmux3h="$HOME/.tmux/three_pane_horizontal_launch.sh"
fi

if [[ -x "$HOME/.tmux/three_pane_simple.sh" ]]; then
  alias tmux3s="$HOME/.tmux/three_pane_simple.sh"
fi

if command -v task-master >/dev/null 2>&1; then
  alias tm="task-master"
fi

if command -v npm >/dev/null 2>&1; then
  npmua() {
    local packages
    npm install -g npm@latest || return
    packages=$(npm outdated -g --parseable --depth=0 2>/dev/null | awk -F: '{print $4}' | sed '/^$/d')
    [[ -n "$packages" ]] && npm install -g $packages
  }
fi

if command -v lazygit >/dev/null 2>&1; then
  alias lg='lazygit'
fi

if command -v recent-commit-prompt >/dev/null 2>&1; then
  alias prompt='recent-commit-prompt'
elif command -v plans-prompt >/dev/null 2>&1; then
  alias prompt='plans-prompt'
fi

alias es="exec $SHELL -l"
