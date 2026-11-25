# Grok-only skills

This directory is the canonical catalog for Grok Build's native-X skills:
`agents`, `convo`, `dlresearch`, `list-summary`, `macro`, and `whathappened`.
Each immediate skill directory is managed; no second registration is needed.
Keep shared skills in `../skills/` and `../registry.json` instead.

From the Skill System root:

```bash
bin/skill-system validate
bin/skill-system configure-grok
bin/skill-system configure-grok --apply
```

`~/.grok/skills/<name>`, `~/.grok2/skills/<name>` and `~/.grok3/skills/<name>`
link directly to these sources. Source edits are visible through every link immediately; no
copy refresh is needed. Edit here, never author an independent home copy.
Native frontmatter, metadata, references, and invocation behavior are retained;
Grok-only packages do not require Codex's `agents/openai.yaml`.

`status` reports each account under `grok`. `sync` includes this projection;
`refresh` continues to update only shared directory copies. `--home` selects
an isolated user home with `.grok`, `.grok2` and `.grok3` beneath it. Authentication,
configuration, sessions, and unrelated skills are not changed.

## Collisions and recovery

An existing directory, file, or different link at a managed name is a collision.
Preserve and reconcile its content first, then preview and apply explicitly:

```bash
bin/skill-system configure-grok --force
bin/skill-system configure-grok --force --apply
```

Unlike the older Claude/MiMo adapters, Grok's force mode never deletes a
collision. It moves each exact entry to
`~/.agents/.skill-system/grok-backups/<unique-id>/<account>/<name>` before
linking. JSON `quarantine_path` identifies that backup root. Unknown names
and links are untouched, including the secondary home's old shared `xgrok`
copy and the pre-existing `orchestration` links.

Projection holds the existing Skill System operation lock and preflights every
account before replacing anything. It is not an all-or-nothing transaction
and does not use the shared install journal or `rollback` command. If interrupted,
inspect `status` and the backup directory; rerunning completes missing links.
To restore an original, move the generated link to a non-discovery recovery
location, then move the corresponding backup back to its original exact path.
Do not discard a live entry that has changed since projection. Backups are not
pruned automatically, and source-directory removal does not automatically
retire a live link.

## Validation boundary

`validate`/`audit` check native package envelopes (name, description, safe
regular-file trees) and compute content hashes. They do not implement a second
full YAML parser. Confirm native discovery after a change with
`grok inspect --json`, `GROK_HOME="$HOME/.grok2" grok inspect --json` and
`GROK_HOME="$HOME/.grok3" grok inspect --json`.
Grok owns frontmatter interpretation and runtime X tools; package validation
does not exercise an X-research run.

All six primary packages were imported unchanged;
only `macro` differed between accounts, with the primary carrying newer rules
and `references/roster.tsv`. Original secondary content remains in the live
migration backup.

See [Grok's skill documentation](https://docs.x.ai/build/features/skills-plugins-marketplaces)
for discovery roots and native frontmatter.
