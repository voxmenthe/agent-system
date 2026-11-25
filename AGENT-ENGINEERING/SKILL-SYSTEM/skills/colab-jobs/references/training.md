# Training and fine-tuning on Colab

For small experiments: a model up to about 1B parameters, a public dataset,
and minutes to an hour of compute. Everything here runs through the helper's
`up`, `push`, `install`, `run`, `wait`, `pull` and `down`.

## Plan before you allocate

Write down, before `up`:

- the model and dataset (public, loaded on the VM by name);
- the hardware: `--gpu T4` unless the user chose otherwise;
- a step or time budget, and `--hours` a little above it;
- the outputs you will bring back, and the evaluation that shows the run
  worked, such as held-out loss before and after training.

Write the training script on your machine. Read it once for mistakes, then
push it. Starting a GPU session only to debug a script wastes it.

## Hardware and precision

| Hardware | Memory | Precision | Fits for LoRA fine-tuning |
|---|---|---|---|
| CPU (default) | about 12 GB RAM | float32 | models up to about 150M, a few dozen steps; good for smoke tests |
| `T4` | 15 GB GPU | float16 only: no bfloat16 | up to about 1.5B with LoRA and short sequences |
| `L4` | 22 GB GPU | bfloat16 | up to about 3B with LoRA |

On a T4, set `fp16=True` and `bf16=False` explicitly. The T4 (compute
capability 7.5) has no native bfloat16, yet `torch.cuda.is_bf16_supported()`
returns `True` there because bfloat16 is emulated, so code or defaults that
pick bfloat16 from that check run slowly. Load the model in float32 and let
the trainer's `fp16=True` mixed precision do the rest. Read the `GPU:` line
from `up` to confirm what you got.

Observed on this account (2026-11-22): a T4 runtime costs about 1.15
compute units per hour and a CPU runtime 0.08; the T4 came with
`torch 2.14.1+cu130`, transformers 5.22.1, datasets 4.8.5, accelerate 1.15.0,
peft 0.21.2, matplotlib 3.10.0 and torchao 0.10.0 preinstalled, and no
`trl`. A LoRA run on Qwen2.5-0.5B-Instruct over 2,000 GSM8K examples (125
steps at batch 16) trained in about 3 minutes; that whole session, with its
smoke runs, used 0.14 compute units.

## Packages

`up` prints what is preinstalled. Usually torch (CUDA build on GPU
runtimes), transformers, datasets, accelerate, peft and matplotlib are
there, and `trl` is not. Install only what is missing:

```bash
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py install exp-1 trl
```

Library APIs change between versions. Write the script for the versions that
`install` and `up` print. For example, in transformers 5,
`tokenizer.apply_chat_template(..., tokenize=True)` returns a `BatchEncoding`,
not a list of ids; take `["input_ids"]`, or tokenize the rendered text
yourself. When unsure about a class or argument, check the
installed library on the VM:

```bash
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py run exp-1 -- python -c "import trl, inspect; print(trl.__version__); print(inspect.signature(trl.SFTConfig))"
```

**LoRA with peft: remove torchao first.** On 2026-11-22 the runtime had
torchao 0.10.0, and peft 0.21.2's `get_peft_model` refuses it with
`ImportError: Found an incompatible version of torchao`. Plain LoRA does not
use torchao, so remove it once per session before the smoke run (`up`
prints the torchao version; skip this if it says not installed):

```bash
python3 ~/.agents/skills/colab-jobs/scripts/colab_job.py run exp-1 -- python -m pip uninstall -y torchao
```

## Smoke run, then the real run

1. Run the script with a tiny budget first, for example `--max-steps 5` and
   a few dozen examples, but with the real batch size and sequence length,
   so a memory problem shows up here rather than in the real run. It must
   reach the end and write its outputs.
2. Read the log for warnings about precision, padding or the chat template.
3. Run the real budget. With `--wait` the helper returns while the job
   continues; follow it with `wait` until `STATE: succeeded`.

## Outputs to write

Write everything into one folder, such as `outputs/` next to the script,
then `pull` that folder before `down`:

- `metrics.json`: the settings, step count, runtime, training loss
  history, and the evaluation before and after;
- `loss.png`: optional; the helper sets `MPLBACKEND=Agg`, so `savefig` works;
- the LoRA adapter (`model.save_pretrained("outputs/adapter")`), usually a few
  MB. Do not pull full model weights; they are large and the helper caps a
  pull at 200 MB.
- a few sample generations before and after, as text.

## When it fails

| Log shows | Fix |
|---|---|
| `CUDA out of memory`, or the job died with signal 9 | Smaller batch, shorter `max_length`, gradient accumulation, or a smaller model. Models with large vocabularies (Qwen: 152k) spend most memory on logits: on a T4, batch 8 × 500 tokens ran out and batch 4 with accumulation 4 fit |
| A `CUDACachingAllocator` warning that memory was short, and training continues | Usually harmless: the allocator freed cached memory and retried. Act only if the job dies |
| `ImportError: Found an incompatible version of torchao` | `run NAME -- python -m pip uninstall -y torchao`, then run again (see Packages) |
| The fix you pushed did not take effect | You pushed one file into `/content/work` while the job runs in a pushed folder: push the folder again |
| `bf16` is not supported | Use `fp16=True` on T4 |
| `unexpected keyword argument` | The library version differs from what you wrote for: check the signature on the VM |
| Very slow steps on a GPU runtime | Run `stats NAME` while it trains: `0% busy` on its `GPU:` line means the model is not on `cuda` |
| `STATE: lost` | The VM ran out of memory or restarted; reduce memory use and run again |

Each failed run spends compute units, so read the error and change something
before you run again.
