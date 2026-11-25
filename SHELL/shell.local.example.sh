# Machine-only shell settings. ~/.bash_profile sources this file, as
# ~/.config/agent-system/shell.local.sh, before it applies its defaults, so
# anything exported here wins. It is never projected or synced; bootstrap
# copies this example once and leaves your edits alone.
#
# Examples:
#
# Caches on an external drive (unset, each tool uses its own default):
#   export HF_HOME=/Volumes/External/huggingface_cache
#   export HUGGINGFACE_HUB_CACHE=$HF_HOME HF_HUB_CACHE=$HF_HOME
#   export HF_DATASETS_CACHE=$HF_HOME/datasets
#   export TORCH_HOME=/Volumes/External/torch_cache
#   export UV_CACHE_DIR=/Volumes/External/uv_cache
#   export PIP_CACHE_DIR=/Volumes/External/pip_cache
#   export SGREP_CACHE_DIR=/Volumes/External/sgrep_cache
#   export SGREP_CACHE_MAX_BYTES=8589934592
#
# Chrome profile the browser skills (gpt, notebooklm, wsj, nyt, washp, bookmarks)
# drive; gpt, notebooklm and wsj stop when it is unset:
#   export CHROME_PROFILE_EMAIL=you@example.com
#
# Repos under ~/repos that AGENT-ENGINEERING/SKILL-SYSTEM/colgrep/reindex indexes
# when given no names:
#   export COLGREP_REPOS="my-app my-library"
#
# Shortcuts for `ag <name>` (opens a folder in Antigravity), as name=path pairs;
# ~ expands, paths cannot contain spaces:
#   export AG_SHORTCUTS="app=~/repos/my-app lib=~/repos/my-library"
#
# Travel mode (`travel <launcher>`), from a checkout that has TRAVEL/travel-mode:
#   export TRAVEL_MODE_SH=$HOME/repos/<checkout>/TRAVEL/travel-mode/travel-mode.sh
#
# Installer-added PATH entries that belong to this machine only:
#   export PATH="$HOME/.antigravity-ide/antigravity-ide/bin:$PATH"
