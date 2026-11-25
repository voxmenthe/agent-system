# Audio Overview Options and Host Instructions

The app's "Customize Audio Overview" dialog has five controls. `nblm.js`
(`createAudio`) and `nblm.py` (`audio`, `paper-audio`) expose all of them.

| Control | Flag | Values |
|---|---|---|
| Format | `--format` | `deep_dive` (default), `brief`, `critique`, `debate` |
| Length | `--length` | `short`, `default`, `long`, depending on format |
| Language | `--language` | language code, default `en` |
| Sources | `--source ID` (repeat) | default: every ready source in the notebook |
| Host instructions | `--focus TEXT` or `--focus-file PATH` | free text, optional |

## Formats

| Format | App's description | Lengths |
|---|---|---|
| Deep Dive | A lively conversation between two hosts, unpacking and connecting topics in your sources | short, default, long |
| Brief | A bite-sized overview to help you grasp the core ideas from your sources quickly | none (omit `--length`) |
| Critique | An expert review of your sources, offering constructive feedback to help you improve your material | short, default |
| Debate | A thoughtful debate between two hosts, illuminating different perspectives on your sources | short, default |

An invalid combination, such as `critique` with `long` or `brief` with any
length, is rejected before anything is sent.

## How long the result runs

Durations of audio generated in this account (`durationSeconds` in the
artifact list):

| Format / length | Host instructions | Sources | Duration |
|---|---|---|---|
| Brief | none | 11 | 1 min 42 s |
| Deep Dive, Short | PhD-level (below) | 1 paper each (4 episodes) | 4 min 49 s to 6 min 14 s |
| not recorded (older episode) | none | 1 paper | 18 min |
| Deep Dive, Default | none | 11 | 25 min |
| Deep Dive, Long | topic-specific, 158 and 932 chars | 1 paper each | 46 and 47 min |
| Deep Dive, Long | PhD-level (below) | 1 document | 68 min |

Length is a target, not a cap. The longest Long episode seen was the one given
the PhD-level instruction.

Generation runs on Google's side and keeps going if the tab closes. A Short
Deep Dive took 4–5 minutes here; long ones take longer. Poll every 15–30
seconds rather than holding one long browser call open.

## Usage

Generation spends the account's "AI Usage" allowance. The meter (`nblm.py
status`, or `nblm.usage()`) shows a daily window and a weekly window. The app
estimates 9.8 % of the daily window per Audio Overview. The meter once rose by
exactly that much; two later Short Deep Dives together raised it 8.7 points,
and it drifted down between readings. Budget up to 10 % per episode. Before a
batch of several episodes, check the meter and tell the user what the batch
will cost. Do not generate audio the user did not ask for.

## Writing host instructions

The text box is labeled "What should the AI hosts focus on in this episode?".
It steers who the hosts are, who they talk to, what they cover, and in what
depth. The app offers three suggestions per notebook (`otmP3b`); they are
narrow topic prompts, while the user's standing preference is a register
change. Instructions of 932 characters have worked; no limit was hit.

Write it as direct guidance to the hosts:

1. **Who the hosts are**: "Both hosts are experts in this field."
2. **Audience and register**: "at a PhD level", "for practitioners who
   already know transformers", "skip the basics".
3. **Coverage**: "deeply explore every single topic", "walk through each
   experiment and its ablations", "spend most of the time on section 4".
4. **What to do with it**: "question the assumptions", "connect to prior work
   on linear attention", "say what would change your mind".
5. **What to leave out**, if anything: "no analogies for beginners".

The user's standing instruction for papers, which this skill's evaluation run
used:

> Both hosts are experts in this field. The focus is on deeply exploring every
> single topic at a PhD level.

Pair it with `--length long` for full coverage. With `--length short` the hosts
keep the register but cover less.

For long or reused instructions, keep them in a file and pass `--focus-file`.
The app stores the exact text with the artifact. `nblm.py show NOTEBOOK`
prints it back as `audio.focus`, which shows what an existing episode was asked
to do.
