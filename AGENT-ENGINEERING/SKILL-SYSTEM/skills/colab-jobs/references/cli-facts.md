# Colab CLI facts behind the helper

Verified on 2026-11-22 against the installed `google-colab-cli` 0.8.0 (its
source under `~/.local/share/uv/tools/google-colab-cli/`) and a live CPU
runtime on the user's account. `doctor` prints the installed version; if it
is newer, re-check anything below before relying on it.

## What the helper handles for you

| CLI behavior | Why it matters | Helper |
|---|---|---|
| First use prints a sign-in URL and waits for a pasted code | An agent's shell hangs or aborts | Every call closes stdin; a sign-in prompt becomes exit `10` |
| `colab exec` exits `0` even when the code raises | A failed step looks successful | Jobs record their own exit code; the helper reads it |
| `colab install` exits `0` even when pip fails, and prints only at the end | A failed install looks successful | `install` is a job with a real exit code and a version check |
| `exec`/`run` stop after 30 s without output unless `--timeout 0` | Quiet model downloads get killed | Jobs run detached; the helper polls them |
| A long `exec` keeps the kernel busy; later calls queue behind it | Status checks hang | Jobs run as separate processes, so the kernel stays free |
| `colab new -s NAME` with a name already in use replaces the record, orphaning the old VM | A VM nobody can stop from the CLI | `up` refuses names that are running |
| `colab upload` into a missing directory fails with HTTP 500, and the error prints the runtime's access token | Token leaks into transcripts | The helper creates directories first and redacts tokens from all output |
| `upload`/`download` move one whole file; directories are rejected | Folders cannot be copied | `push`/`pull` pack folders as archives |
| The CLI never stops a session by itself | Forgotten sessions spend compute units | `up` starts a lease that runs `colab stop` at its deadline |

## Account and cost facts

- Authentication: `oauth2`, the CLI default, with the token in the macOS
  Keychain (`google-colab-cli` / `oauth_token`). It refreshes itself. Only
  the user signs in, with `colab whoami` in their own terminal.
- `colab usage` reports the whole account's balance and hourly rate, not
  one session's.
- Observed rates: a standard CPU runtime 0.08 compute units per hour, a T4
  about 1.15. CPU and T4 runtimes were ready about 3 to 10 seconds after
  `colab new`.
- Each `colab exec` takes about 2 seconds, but connections drop. On a CPU
  runtime in wave 1 this was rare. On a T4 in Europe it happened six times
  in 17 minutes. On a T4 in Asia almost every command saw at least one drop.
  The next call worked every time. `colab sessions` also timed out once
  reading the Colab API.
- After a drop the CLI prints `RuntimeError: Connection was lost.` and then
  often does not exit. The helper ends the call when that line appears.
  Calls that print nothing and hang end at a per-call timeout (45 to 300
  seconds).
- The helper retries every call that is safe to repeat: status checks,
  folder preparation, the `up` probe, uploads, downloads, packing, session
  listing, job starts and unpacking. A start carries a token, so a repeated
  start returns the job the first attempt began instead of running it twice.
  Unpacking keeps a receipt, so a repeat returns the first result.
- Colab limits how many runtimes one account runs at once. With five or six
  already running (one T4, the rest CPU), another `up` was refused with
  exit `12`; it succeeded about a minute later, after others had stopped.
  The limit is not documented.
- A CPU runtime had Python 3.13, 2 CPUs, about 12.7 GB RAM, about 225 GB
  free disk, `uv`, and preinstalled torch (CPU build), transformers,
  datasets, accelerate and peft; `trl` was not installed. GPU runtimes have
  the CUDA build of torch. Always read the `PREINSTALLED:` line from `up`
  rather than assuming.

## Raw commands that are safe

Global flags such as `--auth` go before the subcommand. These do not
allocate or hang:

| Command | Use |
|---|---|
| `colab sessions` | Every runtime the account has, including ones this machine does not know (`[?]`) |
| `colab status -s NAME` | Hardware and the CLI's own idle or busy record for a session |
| `colab usage` | Balance and current account-wide rate |
| `colab log -s NAME -n 20` | The CLI's local history for a session; `-o history.ipynb` exports it |
| `colab url -s NAME` | A browser URL that attaches the Colab web UI to the session (for the user) |
| `colab stop -s NAME` | Stops a session you created, if `down` cannot |

## Orphans

A `[?]` line in `colab sessions` (shown by `doctor` as `ORPHAN`) is a runtime
the CLI has no local record for. The CLI cannot stop it. Tell the user; they
can stop it in the Colab web UI under Runtime > Manage sessions. Do not try
to stop another agent's session.

## What the helper does not do

- **Secrets.** `colab exec --env KEY=VALUE` writes the value into the CLI's
  history files. Ask the user before any task that needs a token.
- **Google Drive.** `colab drivemount` needs a person at a terminal.
- **Several sessions per agent, sweeps, or retries on other hardware.** Run
  one session and one job at a time; ask the user before using more.
- **Keeping files after `down`.** `/content` is deleted with the VM.
