# Pretraining a Bread model from scratch

This is the path where nothing is inherited. Every weight starts as random
noise and learns from a corpus you chose. There is no base model, no Qwen, and
nothing in the lineage but your data.

It is a real option with real limits, and both halves of that sentence matter.

## What one GPU can actually pretrain

The numbers below are measured parameter counts from the shipped configs, with
compute estimated at roughly 80 effective TFLOPS in bf16. Treat the time column
as a planning figure only. The trainer measures your actual throughput in the
first hundred steps and prints a projection from that; believe the measurement.

| Config | Parameters | Tokens | Text needed | Time on one 5090 |
| --- | --- | --- | --- | --- |
| `bread_tiny` | 38.5M | 0.77B | ~3 GB | under an hour |
| `bread_small` | 100.1M | 2.0B | ~8 GB | about 4 hours |
| `bread_base` | 298.6M | 6.0B | ~24 GB | about 1.5 days |
| `bread_large` | 653.2M | 13.1B | ~52 GB | about 7 days |

Every config plans about 20 tokens per parameter, which is roughly
compute-optimal. A test enforces that, because the most common way to waste a
week is to train a large model on a small corpus.

**Data is usually the binding constraint, not compute.** Most people can find
the GPU hours and cannot find 52 GB of text they are happy to train on. If you
cannot feed a size, drop to the one below it. A well-trained small model beats a
starved large one at every task.

## The three commands

```bash
# 1. Build a corpus. Any Bread dataset works, plus raw folders.
python scripts/prepare_pretrain_data.py \
  --input data/datasets/local_code.jsonl \
  --input-dir ~/Documents/notes \
  --vocab-size 32000

# 2. Check the plan before spending the time.
python scripts/pretrain_bread.py --config configs/pretrain/bread_small.yaml --dry-run

# 3. Train.
python scripts/pretrain_bread.py --config configs/pretrain/bread_small.yaml
```

Then export it into a directory anything can load:

```bash
python scripts/export_pretrained.py \
  --run data/runs/pretrain-bread-small \
  --tokenizer data/pretrain/tokenizer \
  --output data/models/bread-small
```

Start with `bread_tiny`. It finishes in under an hour and proves your corpus,
your tokenizer and your throughput before you commit days to a larger run.

## What happens in each step

**Preparing data** trains a byte-level BPE tokenizer on your text, then
tokenizes the whole corpus once into a flat binary file. Training memory-maps
that file, so a corpus far larger than RAM works fine: the operating system
pages in only the few megabytes each batch touches.

A tokenizer trained on your own code spends its vocabulary on the identifiers
and words you actually use. That is worth several percent of effective context
compared with a generic vocabulary.

**Training** runs the standard next-token objective with cosine decay after a
warmup, gradient accumulation for a large effective batch, and gradient
clipping. It checkpoints regularly and resumes from where it stopped, so an
interrupted run costs minutes rather than days.

**Exporting** writes the weights in the layout `transformers` expects. The model
uses the conventional decoder-only stack: RMSNorm, rotary position embeddings,
grouped-query attention and SwiGLU. That is the same shape Llama uses, which is
why the export loads in standard tooling with no custom code.

Sharing an architecture is not sharing weights. The floor plan is conventional.
Every brick is yours. A test proves the export is faithful by comparing logits
from Bread's implementation against Transformers on the same input, and requires
them to match exactly.

## Reading the run

The first thing to check is that the initial loss is about `ln(vocab_size)`,
which is 10.4 for a 32,000-token vocabulary. That is the loss of a model
predicting uniformly at random, and it is what a correctly initialised model
starts at. A much higher number means the initialisation is broken.

From there:

- **Loss falls fast, then slowly.** A steep first thousand steps followed by a
  long shallow decline is healthy.
- **Held-out loss tracks training loss.** If they separate, the model is
  memorising. With a corpus this size that usually means the corpus is too small
  for the model, not that the schedule is wrong.
- **Tokens per second should be stable.** A slow drift downward usually means
  thermal throttling or another process competing for the GPU.
- **A loss that goes flat at a high value** means the learning rate is too low,
  or the corpus has a formatting problem the tokenizer is choking on. Decode a
  few random windows and read them.
- **NaN** is almost always fp16 overflow. Use bf16.

## What you get

A base model. It completes text; it does not follow instructions. Asked "what is
a linear equation?" it will continue the sentence rather than answer the
question, because nothing has taught it that questions get answers.

To make it answer, run a supervised fine-tune on it afterwards, using the same
dataset tools as the rest of Bread:

```bash
python scripts/build_sft_dataset.py --input data/datasets/local_code.jsonl \
  --output data/datasets/bread_sft.jsonl
python scripts/bake_bread_model.py --base-model-id data/models/bread-small \
  --output-name bread-small-instruct
```

That is the honest full path to a model that is entirely yours and answers
questions: pretrain, then instruction-tune.

## Choosing between pretraining and fine-tuning

| | Pretrain from scratch | Fine-tune an open-weight base |
| --- | --- | --- |
| Whose weights | Entirely yours | Derived from someone else's |
| Capability ceiling | Set by your compute and data | Inherited, then adapted |
| Best result on one 5090 | Fluent, narrow, roughly GPT-2 class | Strong coding assistant |
| Time to something useful | Hours to a week, plus a fine-tune | About an hour |
| Attribution required | None | Yes, and the license governs it |

If the goal is the best coding assistant your hardware can run today, fine-tune
an open-weight base. If the goal is a model with no external lineage, pretrain.
They are different goals and Bread supports both.

Nothing about pretraining at this scale produces a model that competes with a 7B
model trained on trillions of tokens. That gap is compute and data, and it does
not close. What pretraining gives you instead is total ownership, a model small
enough to run anywhere, and a corpus you fully understand.

## Practical notes

**Resuming.** Every run writes `checkpoint.pt` on a schedule and resumes from it
automatically. Pass `--no-resume` to start over.

**Sequence length** is the setting that moves memory most, because attention is
quadratic in it. Lower it before anything else if you hit out-of-memory.

**Effective batch size** is `batch_size × gradient_accumulation_steps`. Keep the
per-device batch small and accumulate, which is how you get a large effective
batch without the memory for one.

**torch.compile** is off by default. It typically helps throughput and makes the
first step take a minute or two. Turn it on for a long run.

**Vocabulary size** trades embedding parameters against sequence length. 32,000
is a reasonable default. Below about 8,000 the sequences get long enough to cost
you more than the embedding saves.
