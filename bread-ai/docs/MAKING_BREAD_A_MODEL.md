# Making Bread a model, not just an app

By default Bread is an application wrapped around somebody else's LLM. You point
`MODEL_ID` at Qwen or anything else, and Bread supplies the prompt, the
retrieval and the interface. The model is a component you swap.

This page is about the other option: baking a set of weights that *are* Bread.
It answers as Bread, holds Bread's conventions, states what it is derived from,
and ships as a single directory you can hand to someone else.

## What "Bread is an LLM" can and cannot mean

**It can mean** a fine-tune of an open-weight base, merged into standalone
weights. That is a real model file, loadable by anything that reads
Transformers weights, with its own name and its own behaviour. It is still
derived from its base, and honest documentation has to keep saying so.

**It cannot mean** weights pretrained from nothing on your hardware. Pretraining
a model of this class needs compute roughly five orders of magnitude beyond one
RTX 5090. See [LIMITATIONS.md](LIMITATIONS.md). No configuration in this
repository changes that, and none of it pretends to.

So: the deliverable is `bread-coder-7b`, a Qwen-derived model that is
recognisably Bread. Not a model that appeared from nowhere.

## The corpus is the product

Everything Bread believes about itself lives in one version-controlled file:

```
prompts/identity.yaml
```

It holds four kinds of example:

| Section | What it teaches |
| --- | --- |
| `identity` | Who Bread is, what it is derived from, what it will not claim |
| `style_examples` | The shape of a good answer: lead with it, state assumptions, explain the decision |
| `uncertainty_examples` | Saying "I do not think that API exists" instead of inventing one |
| `domain_examples` | Framings for Paper, Luau anti-cheat, Discord bots, CI and the rest |

Each `identity` entry is one question asked several ways with a single answer, so
"who are you", "what are you" and "introduce yourself" all land in the same
place.

Two rules when you edit it. Never write an answer claiming Bread is a frontier
model, was pretrained from scratch, or matches a hosted assistant; the model
repeats what you write. And prefer one excellent example to five mediocre ones,
because identity data is small and heavily weighted, so a sloppy example shows
up everywhere.

A test suite enforces the first rule:

```bash
pytest backend/tests/test_identity.py
```

It fails the build if the corpus starts claiming to be Claude.

## Why the general data mix is not optional

Training on identity data alone is the classic way to ruin a model. A few
hundred records about "who are you" at a normal learning rate produces a model
that introduces itself beautifully and has forgotten how to write a loop. The
effect is catastrophic forgetting, and it is not subtle.

The fix is to drown the identity data in ordinary work. The default ratio is
eight general coding records per identity record, so the gradient is dominated
by "keep being a coding model" and identity is a small, consistent nudge.

Keep identity below roughly 30% of the dataset. Both the builder and the bake
script warn when it is not, with the number.

## Baking it

```bash
# 1. General coding data from projects you own. This is the part that keeps the
#    model useful; the identity corpus only changes how it talks.
python scripts/collect_local_code.py \
  --path "C:/dev/minecraft-plugins" \
  --path "~/projects" \
  --languages python java typescript lua luau

python scripts/build_sft_dataset.py \
  --input data/datasets/local_code.jsonl \
  --output data/datasets/bread_sft.jsonl

# 2. Check everything before spending hours on it.
python scripts/bake_bread_model.py --dry-run

# 3. Bake.
python scripts/bake_bread_model.py --mix data/datasets/bread_sft.jsonl
```

The bake runs four steps: build the identity dataset mixed with your data,
validate it, run the QLoRA fine-tune from
`configs/training/bread_identity.yaml`, then merge the adapter into the base
weights and write a model card.

On an RTX 5090 with a 7B base, the training step takes roughly 40 to 90 minutes
depending on how much general data you collected. The merge takes another 10 to
20 minutes and needs enough RAM to hold the base model at full precision, about
16 GB for a 7B; it runs on CPU by default so it does not compete with anything
on the GPU.

## What you get

```
data/models/bread-coder-7b/
├── config.json
├── model-00001-of-000NN.safetensors
├── tokenizer.json
├── README.md        model card
└── bread.json       machine-readable provenance
```

Use it:

```ini
MODEL_ID=data/models/bread-coder-7b
ADAPTER_PATH=
```

Or from anything else:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("data/models/bread-coder-7b")
model = AutoModelForCausalLM.from_pretrained("data/models/bread-coder-7b", device_map="auto")
```

`--register` adds it to Bread's catalogue so it appears on the Models page with
a Load button.

## Check it worked

```bash
python scripts/eval_model.py --model-id data/models/bread-coder-7b --no-4bit
```

Then ask it the questions that matter:

- "Who are you?" It should say Bread, and name what it was fine-tuned from.
- "Are you Claude?" It should say no, without hedging.
- "Are you as good as GPT-4?" It should say no, and say why that is a fair trade.
- A real coding question from your own work. This is the one that catches
  catastrophic forgetting: if the identity answers are perfect and the code
  answers got worse, raise the mix ratio and bake again.

Compare against the base model by running the same prompts with
`--model-id Qwen/Qwen2.5-Coder-7B-Instruct`. Identity should change. Coding
ability should not.

## Sharing the weights

The generated model card carries a "What this is not" section naming the base
model, its license and the limits of what a fine-tune did. Keep it. It is what
makes "this is Bread" a true statement rather than an asserted one, and stripping
it turns an honest artifact into a misleading one.

`bread.json` records the same facts in a form a script can read, including
`"trained_from_scratch": false`.

The base model's license governs redistribution of the weights. Qwen2.5-Coder is
Apache-2.0, which permits it with attribution; a different base may not. Your
general training data has its own licensing, which the collector recorded in each
dataset's manifest. Read both before publishing.

## Changing the base model

```bash
python scripts/bake_bread_model.py \
  --base-model-id Qwen/Qwen2.5-Coder-14B-Instruct \
  --output-name bread-coder-14b
```

The corpus uses `{base_model}` and `{base_license}` placeholders rather than
hardcoded names, so the answers stay truthful when the base changes. The builder
substitutes them, and a test checks nothing is left unsubstituted.

## Rebaking after you edit the corpus

Edit `prompts/identity.yaml`, then run the bake again. It is not incremental:
each bake starts from the base model, so a bad edit cannot accumulate across
runs. Keep the previous `data/models/` directory until you have compared them.
