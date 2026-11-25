---
name: herenow-deploy
description: Publish or update an exact static site bundle with the installed HereNow CLI. Use only when the user explicitly invokes $herenow-deploy and authorizes a HereNow deployment. Do not use for website creation, other hosts, deletion, or a deployment that has not been explicitly requested.
disable-model-invocation: true
---

# HereNow Deploy

Publish one exact static artifact bundle to the user's HereNow account, verify
the remote result, and report the URL and access state. Invocation authorizes
only the requested create or update; it does not authorize deletion or other
external changes.

## Establish the target and authority

1. Run `command -v herenow` and `herenow --version`. If the CLI is absent,
   stop; do not install it without separate approval.
2. Identify the exact artifact and whether this is a new deployment or an
   update. For an update, use a URL or slug supplied by the user, or an
   unambiguous path-to-URL mapping from `herenow list`. Never guess the target.
3. Use the account already configured for the CLI. HereNow resolves credentials
   from `HERENOW_API_KEY`, `~/.env`, then `~/.herenow/credentials`. Never read,
   print, copy, or expose the credential. If authentication is unavailable,
   stop and report the blocker.
4. If the installed CLI differs from this procedure, inspect
   `herenow publish --help` before continuing.

The current CLI publishes with restricted access for the configured owner
email, or its built-in owner default. Tell the user that the result is
restricted; do not claim it is public.

## Prepare the exact bundle

- A single self-contained HTML file can be published directly; HereNow maps a
  non-`index.html` HTML file to remote `index.html`.
- If the page uses CSS, JavaScript, images, fonts, or other assets, publish a
  purpose-built directory containing `index.html` and exactly that dependency
  closure. Inspect `src`, `href`, `url(...)`, and module references first.
- Never publish a broad repository or working directory. Directory publishing
  recursively uploads every regular file except `.DS_Store` and
  `.herenow/fork-meta.json`; inventory the bundle for secrets and unrelated
  files before the external write.
- Use `--spa` only when client-side routes require fallback to `index.html`.

## Publish or update

For a new deployment:

```bash
herenow publish <exact-file-or-directory> [--title <title>] [--description <description>] [--spa]
```

For an update, pass the exact existing URL or slug:

```bash
herenow publish <exact-file-or-directory> --url <exact-url-or-slug> [--title <title>] [--description <description>] [--spa]
```

An update replaces the submitted manifest and may omit old files, so confirm
the complete dependency closure before running it. Do not invoke
`herenow delete`; deletion requires a separate explicit request and review.

## Verify and report

1. Require exit status zero and inspect the structured `publish_result` emitted
   by the CLI. Confirm the action, URL, authentication mode, persistence,
   access mode, file count, and remote file list.
2. Run `herenow list` and confirm the exact local path maps to the returned URL.
3. Compare `remote_files` with the intended bundle. A successful upload with a
   missing dependency is not a verified deployment.
4. When a signed-in, allowlisted browser is available, open the root page and
   at least one representative asset. An unauthenticated request may show the
   access gate instead of the site; do not treat that as a rendering check.
5. Report the URL, create/update action, source artifact, file count, restricted
   access state, checks performed, and any browser-verification limitation.

If upload finalization or access configuration fails, do not claim success even
when file transfer completed.
