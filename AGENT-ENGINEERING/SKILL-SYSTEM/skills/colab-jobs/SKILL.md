---
name: colab-jobs
description: Run scripts, dependency installs, experiments and small fine-tuning jobs on a Google Colab runtime under the user's signed-in personal Google account, through one safe helper over the official `colab` CLI. Use when the user asks to set up a Colab runtime, run code or training on Colab CPU, GPU or TPU, or bring results back from Colab. Do not use to sign in, handle tokens, mount Google Drive, buy compute units, or run work the user did not ask for.
disable-model-invocation: true
---

# Colab jobs

One helper, `scripts/colab_job.py`, does every step: check the account,
create a runtime, copy files, install packages, run commands as jobs, copy
results back, and release the runtime. Call it by its full path from any
directory:

```bash
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py --help
```

It needs only the standard library and the official `colab` CLI, which is
already installed and signed in to the user's account.

## Rules

1. **Use only the helper.** Do not call raw `colab exec`, `repl`, `ssh`,
   `auth` or `drivemount`: they hang on prompts, block the runtime, or hide
   failures. If you need something the helper cannot do, read
   [cli-facts.md](references/cli-facts.md).
2. **Never sign in.** Exit code `10` means the sign-in is missing or expired.
   Ask the user to run `colab whoami` in their own terminal. Never open a
   sign-in URL, and never read, print or copy tokens.
3. **Cheapest hardware first.** `up NAME` with no flags gives a CPU runtime,
   the cheapest (about 0.08 compute units an hour). Use `--gpu T4`, the
   cheapest GPU (about 1.15 an hour), only when the task needs a GPU. Use
   other hardware only when the user asks. Do not switch hardware on your
   own after a refusal.
4. **One session per agent.** Give it a unique name, such as
   `<task>-<your-agent-name>`. Never stop or use a session you did not create.
5. **Pull results before `down`.** `down` deletes the VM and every file on it.
6. **Always finish with `down`**, even after a failure. A forgotten session
   stops by itself when its lease ends (`--hours`, default 1), but it spends
   compute units until then.
7. **No secrets.** Use public models and datasets. If a task needs a token
   (gated model, private data, W&B), stop and ask the user.
8. **Do not install torch, jax or tensorflow.** Colab already has them,
   built for its CUDA; `up` prints the versions.

## Quick start

Run these in order. Replace `exp-1` with your session name and `./project`
with your folder. Each command returns within about its `--wait` seconds
(`run` and `wait` 100, `install` 300) plus a few seconds. If your shell tool
stops commands sooner, add a smaller `--wait`, such as `--wait 20`: the job
keeps running, and `wait exp-1` picks it up.

```bash
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py doctor
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py up exp-1
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py push exp-1 ./project
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py install exp-1 trl
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py run exp-1 --cwd project -- python train.py --steps 20
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py pull exp-1 project/outputs ./results
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py down exp-1
```

| Step | Look for |
|---|---|
| `doctor` | `READY`, the masked account, `BALANCE`, and any `SESSION:` lines already running. It never creates anything. |
| `up exp-1` | `HARDWARE: CPU (Standard)`, `PREINSTALLED:` versions, and `LEASE:` with the auto-stop time. `USAGE_RATE` is the whole account's rate, including other agents' sessions, not this session's cost |
| `push exp-1 ./project` | `PUSHED: ./project -> /content/work/project` |
| `install exp-1 trl` | `Installed versions:` with one line per package, then `STATE: succeeded` |
| `run exp-1 ... -- CMD` | `JOB:` (the job name), the command's output, then `STATE:` and `EXIT_CODE:` |
| `pull exp-1 project/outputs ./results` | `SAVED: results/outputs (N files, ...)` |
| `down exp-1` | `RELEASED: exp-1` |

Helper options such as `--cwd` and `--wait` go **before** `--`. Everything
after `--` is your command, passed to it unchanged and run without a shell:
`run exp-1 --cwd project --wait 20 -- python train.py --steps 20`. For pipes
or `&&`, use `-- bash -c 'nvidia-smi && df -h /content'`.

## Files and paths

- On the VM, your files live in `/content/work`. `push` copies a file or
  folder to `/content/work/<its name>`, skipping `.git`, `.venv` and
  `__pycache__`. After you edit, push the same folder again; it overwrites.
  Pushing one file from it puts that file in `/content/work`, not in the
  folder, so a job with `--cwd project` would run the old copy.
- `run` starts in `/content/work`. `--cwd project` starts in
  `/content/work/project`.
- Paths in `pull` and `--cwd` are relative to `/content/work` unless they
  start with `/`.
- `pull NAME REMOTE LOCAL_DIR` saves into `LOCAL_DIR/<last part of REMOTE>`:
  `pull exp-1 project/outputs ./results` creates `./results/outputs/`. It
  refuses to overwrite a local path unless you add `--overwrite`.
- Write results into one folder and pull that folder. Pushed a folder: the
  script runs with `--cwd project`, writes `outputs/`, and you pull
  `project/outputs`. Pushed a single file such as `./check.py`: it lands in
  `/content/work/check.py`, runs without `--cwd`, and you pull `outputs`.
- `push` and `pull` move at most 200 MB (`--max-mb`). Download datasets and
  models on the VM inside your script, for example with
  `datasets.load_dataset`, instead of pushing them.

## Long jobs

`run` follows the job's log for 100 seconds, then exits with code `75` and
prints the exact `wait` command. **The job keeps running on the VM.** Then:

```bash
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py wait exp-1 JOB
```

Repeat `wait` until it prints `STATE: succeeded` or `STATE: failed`. Each
`wait` first repeats the log's last 20 lines for context, then follows new
output. Do not start the same command again while it runs. Set
`--wait SECONDS` on `run` or `wait` below your shell tool's time limit.
`logs exp-1 JOB --tail 100` shows the end of a job's log at any time. To stop a running job, run
`run exp-1 -- pkill -f train.py`, replacing `train.py` with your script.

The output shows each progress bar once, at its latest state, and caps very
long logs. The last lines, where errors appear, are always shown.

### Checking on a job

These only read, so they are safe while a job runs. Each takes a few seconds.

| Command | Shows |
|---|---|
| `jobs exp-1` | Every job on the session, newest first: name, state, run time, exit code, command and last log line. Use it to find a job's name |
| `stats exp-1` | CPU load, RAM, disk, the GPU's busy %, memory and temperature, and each running job's CPU (100% is one full core), RAM and process count |
| `logs exp-1 JOB --grep loss` | Only the lines of the whole log that match, such as the loss history. `--tail N` sets how many (default 50) |

`--grep` takes a case-insensitive regular expression: `--grep 'error|warn'`
matches either word. While a GPU job trains, `0% busy` on the `GPU:` line
of `stats` means the job is not using the GPU. RAM or GPU memory near the
total means the job may run out of memory.

## Exit codes

| Exit | Meaning | What to do |
|---|---|---|
| `0` | Done | Continue |
| `1` | Your command failed on the VM | Read the log lines shown, fix the cause, run again |
| `2` | Bad arguments, a missing path, or a refused action | Read the `ERROR:` and `NEXT:` lines |
| `10` | Colab is not signed in | Ask the user to run `colab whoami` in their own terminal |
| `11` | The `colab` CLI is missing | Run the install command shown, then `doctor` |
| `12` | Colab refused the runtime (quota, capacity, hardware entitlement) | `doctor`; retry once after a minute; ask the user before trying other hardware |
| `13` | The session is not running | `doctor`, then `up` a new session with a new name |
| `14` | That session name is taken | Pick another name |
| `15` | The CLI or the connection failed (the helper already retried) | Follow `NEXT:`. If it says the job may have started, run `logs` before starting anything again |
| `75` | The job is still running | Run the `wait` command shown |

Every failure prints `ERROR:` and a `NEXT:` line. Follow `NEXT:`. A line
like `[colab-jobs] ... retrying automatically (2 of 4), nothing to do` is not
a failure: Colab connections drop now and then, and the helper reconnects by
itself.

## Commands

| Command | Does |
|---|---|
| `doctor` | Checks the CLI, the sign-in, compute units and running sessions |
| `up NAME [--gpu T4] [--hours H]` | Creates a session (CPU by default) and prints its hardware and preinstalled packages |
| `push NAME LOCAL [--to DIR]` | Copies a file or folder to `/content/work` |
| `install NAME PKG... [-r FILE] [--wait S]` | Installs packages as a job (`uv pip`, or pip if uv is missing) and prints their versions |
| `run NAME [--cwd DIR] [--wait S] [--job ID] -- CMD...` | Runs a command as a job |
| `wait NAME [JOB] [--wait S]` | Follows a job (default: the latest) until it ends |
| `logs NAME [JOB] [--tail N] [--grep REGEX]` | Prints the end of a job's log, or only its matching lines |
| `jobs NAME` | Lists the session's jobs, newest first, with state and last log line |
| `stats NAME` | Shows CPU, RAM, disk and GPU use, and each running job's share |
| `pull NAME REMOTE LOCAL_DIR [--overwrite]` | Copies a file or folder back from the VM |
| `down NAME` | Stops the session and confirms Colab released it |

`--gpu` accepts `T4`, `L4`, `G4`, `A100`, `H100`. `--tpu` accepts `v5e1` and
`v6e1`. `--high-mem` asks for more RAM and costs more.

## Training and fine-tuning

Before writing a training script, read
[training.md](references/training.md). It covers hardware, precision,
model sizes, smoke runs and outputs, and a preinstalled package (torchao)
that breaks LoRA with peft until you remove it.

## Report

End with: the session name and hardware, what you ran, each job's
`STATE` and `EXIT_CODE`, where the results are saved locally, and the
`RELEASED:` line from `down`.
