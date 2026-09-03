# Fine-tuning Bread

This is the part of Bread that uses your RTX 5090 for what it is actually good
at: adapting an existing open-weight model to your code.

Read [LIMITATIONS.md](LIMITATIONS.md) first if you have not. The short version:
fine-tuning teaches a model *how* to answer, not *what* is true, and it is not
pretraining.

## What LoRA and QLoRA actually do

A 7B model has about 7 billion weights. Full fine-tuning updates all of them,
which needs memory for the weights, their gradients and two optimiser moments
each: roughly 16 bytes per parameter, or about 112 GB. That does not fit.

**LoRA** freezes the original weights and inserts a pair of small low-rank
matrices beside each targeted layer. Only those train. With rank 32 across every
projection you are training on the order of 40 million parameters instead of 7
billion, and the optimiser state shrinks in proportion.

**QLoRA** adds one more step: quantize the frozen base model to 4-bit NF4, so
the weights themselves take about 3.5 GB instead of 14. Gradients still flow
through the quantized weights to the adapters in higher precision.

Together they turn a run that needs a datacentre into one that needs about 10 GB
of VRAM.

## Before you start

1. **Build a dataset.** See [DATASETS.md](DATASETS.md). A few thousand good
   examples beats a hundred thousand mediocre ones.
2. **Validate it.** `python scripts/validate_dataset.py --input data/datasets/bread_sft.jsonl`
3. **Read the report.** `python scripts/dataset_report.py --input data/datasets/bread_sft.jsonl`
   The two numbers that matter most are the record count and the p99 length.
   Anything longer than `max_seq_length` gets truncated, which teaches the model
   to stop mid-thought.
4. **Dry run.** `python scripts/train_qlora.py --config configs/training/qlora_7b.yaml --dry-run`
   This checks the config, the dataset and the GPU and reports every problem at
   once.

## The shipped configs

| Config | Base model | VRAM | Notes |
| --- | --- | --- | --- |
| `qlora_7b.yaml` | Qwen2.5-Coder-7B-Instruct | ~10 GB | The recommended default |
| `qlora_14b.yaml` | Qwen2.5-Coder-14B-Instruct | ~18 GB | Better answers, roughly 2× slower |
| `lora_small_fallback.yaml` | Qwen2.5-Coder-1.5B-Instruct | ~6 GB | For 8-12 GB cards, and for proving the pipeline |
| `tiny_scratch.yaml` | none (from scratch) | ~4 GB | A toy. Educational only |

Run one:

```bash
python scripts/train_qlora.py --config configs/training/qlora_7b.yaml
```

Or start it from the Training page, which runs the same script and tails its log.

## Reading the settings that matter

**`lora_r` (rank)** is the capacity of the adapter. 8 is enough to shift style;
32 is the general-purpose choice; 64 or higher rarely helps and overfits faster
on a small dataset. `lora_alpha` is conventionally twice the rank.

**`lora_target_modules`** decides where adapters go. Targeting every projection
(`q,k,v,o,gate,up,down`) is what makes a LoRA behave close to a full fine-tune.
Dropping to `["q_proj", "v_proj"]` roughly halves the memory and noticeably
reduces what the adapter can learn.

**`max_seq_length`** is the single biggest lever on memory. Attention is
quadratic in sequence length, so halving 2048 to 1024 does much more than
halving anything else. It is the first thing to lower when you hit
out-of-memory.

**Effective batch size** is `per_device_train_batch_size ×
gradient_accumulation_steps`. The shipped 7B config uses 1 × 16 = 16. Keeping
the per-device batch at 1 and accumulating is how you get a usable batch size
without the memory for one.

**`learning_rate`** at 2e-4 is standard for LoRA and roughly ten times what you
would use for a full fine-tune, because you are training far fewer parameters.
Lower it to 1e-4 if the loss is unstable.

**`num_train_epochs`** should be 1 to 3. LoRA memorises small datasets quickly;
if evaluation loss starts rising while training loss falls, you have gone past
useful.

## While it runs

Watch VRAM with `nvidia-smi -l 2`. Watch the loss in the terminal or on the
Training page.

A healthy run: loss falls quickly for the first few hundred steps, then flattens
into a slow decline. Evaluation loss tracks it down and then flattens.

Trouble:

- **Loss is flat from the start.** The learning rate is too low, or your chat
  template is mangling the examples. Check what one formatted record looks like.
- **Loss spikes to NaN.** Usually fp16 overflow. Use bf16 on any recent card.
- **Evaluation loss rises while training loss falls.** Overfitting. Fewer epochs,
  more data, or a lower rank.
- **CUDA out of memory.** In this order: lower `max_seq_length`, confirm
  `gradient_checkpointing: true`, lower `lora_r`, trim `lora_target_modules`.

## Using the result

The run writes an adapter directory of a few dozen megabytes:

```
data/runs/qlora-7b/
├── adapter/              adapter_config.json + safetensors + tokenizer
├── checkpoint-200/
└── train.log
```

Point Bread at it:

```ini
MODEL_ID=Qwen/Qwen2.5-Coder-7B-Instruct
ADAPTER_PATH=data/runs/qlora-7b/adapter
```

Restart the server and load the model. Or register it on the Models page with
the adapter path filled in, which lets you keep several adapters and switch
between them.

## Did it actually help?

Perplexity alone will not tell you. Run the evaluation script twice, once with
the adapter and once without, and read the samples:

```bash
python scripts/eval_model.py --model-id Qwen/Qwen2.5-Coder-7B-Instruct \
  --dataset data/datasets/bread_sft.eval.jsonl

python scripts/eval_model.py --model-id Qwen/Qwen2.5-Coder-7B-Instruct \
  --adapter data/runs/qlora-7b/adapter \
  --dataset data/datasets/bread_sft.eval.jsonl
```

Lower perplexity means the model finds your data less surprising, which is what
fine-tuning optimises for. It does not mean the answers got better. Read the
generated samples, and try the adapter on real questions from your own work.

## Merging (optional)

```bash
python scripts/merge_lora.py \
  --base-model-id Qwen/Qwen2.5-Coder-7B-Instruct \
  --adapter data/runs/qlora-7b/adapter \
  --output data/runs/qlora-7b/merged
```

Merging removes the adapter indirection and lets you convert the result to GGUF.
It also writes a full-size copy of the model, about 15 GB for a 7B. Do not merge
if you want to keep swapping adapters; Bread loads them at runtime with no merge
step.

## The from-scratch toy

`configs/training/tiny_scratch.yaml` trains a few-million-parameter
character-level transformer on your own English text. It exists so the mechanics
of pretraining are concrete: a vocabulary, batched context windows, a loss that
falls, samples that go from noise to word shapes.

Success looks like text with plausible word shapes, occasional real words, and
no coherent meaning. That is the ceiling for a model this size on data this
small. It is not a smaller version of a useful model; it is a demonstration of a
mechanism.
