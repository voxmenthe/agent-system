# sgrep for every agent

[sgrep](https://github.com/context-dot-dev/sgrep) (local search by meaning) is every
agent's first tool for finding code by behaviour, with rg and then grep after
it. Three pieces reach the agents:

| Piece | Source | Reaches |
|---|---|---|
| Always-on rule | `### Find code` in [`../../PERSISTENT-GUIDANCE/AGENTS.md`](../../PERSISTENT-GUIDANCE/AGENTS.md) | every guidance host via `./guidance sync`; OpenCode via `./agents` here |
| Skill | [`../skills/sgrep/`](../skills/sgrep/SKILL.md), registered in `../registry.json` | Codex, Devin, Kimi, Grok and Antigravity read `~/.agents/skills`; Claude Code and MiMo through `configure-claude` and `configure-mimo`; Command Code and Pi via `./agents` here |
| Cache settings | `SGREP_CACHE_DIR` and `SGREP_CACHE_MAX_BYTES` in `SHELL/.bash_profile` | anything launched from a login shell |

After editing the skill or the kernel section:

```bash
../bin/skill-system install sgrep --apply   # or refresh --apply
../bin/skill-system configure-mimo --apply
./agents install                            # Command Code and Pi links, OpenCode's copy of the rule
./agents status                             # "stale" means OpenCode's copy differs from the kernel
```

`./agents install` needs the shared skill installed first. It refuses to
replace an existing entry at a link path, and `uninstall` removes only its own
links and OpenCode's marked block (and the file, if nothing else is in it).
OpenCode needs the copy because it loads no persistent guidance. Its skill
tool already finds the shared skill.

## Index size

sgrep keeps one index per searched folder, but only while the whole cache,
including that index, fits under `SGREP_CACHE_MAX_BYTES` (default 256 MiB).
At the default, my three largest repos are re-read on every search, about
10-20 s each time. The profile raises the limit to 8 GiB, where their warm
searches take 0.5-5 s and their indexes take 0.3-1.4 GB; `SGREP_CACHE_DIR` in
`shell.local.sh` can put the cache on another drive.
Agents started outside a login shell, such as desktop apps, get the default.
