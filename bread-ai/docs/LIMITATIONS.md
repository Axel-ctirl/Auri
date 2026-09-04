# What Bread cannot do

This page exists because the honest version of a project's capabilities is more
useful than the flattering one. Everything here is a real constraint, not
modesty.

## Bread does not train a frontier model, and cannot

A frontier model is pretrained on the order of 10²⁴–10²⁶ floating-point
operations, across thousands of accelerators, for weeks, over trillions of
tokens of curated text, with an engineering team keeping the pipeline fed and
the run alive through hardware failures.

One RTX 5090 delivers on the order of 10¹⁵ useful operations per second for this
kind of work. Running it flat out for a solid month gets you into the 10²¹
range, which is three to five orders of magnitude short, before considering that
you do not have the data, the pipeline, or the many failed runs that precede a
good one.

No configuration file, quantization scheme or optimiser trick closes that gap.
Any project that tells you otherwise is either redefining "frontier model" or
mistaken.

**What actually works on your hardware:** taking a model somebody already
pretrained, and adapting it. That is what QLoRA does, and it is genuinely
valuable. A 7B coding model fine-tuned on your codebase writes code that fits
your project in a way the base model does not.

## What pretraining from scratch does and does not get you

Bread can pretrain a model from random initialisation, and the result is
genuinely yours with no inherited weights. On one RTX 5090 that means something
in the 38M to 650M range, trained on 0.8B to 13B tokens, over an hour to a week.

Such a model is fluent in the domains it saw and writes short, idiomatic code.
It is roughly GPT-2 class. It will invent APIs, lose track of long context and
fail at multi-step reasoning, and it will not approach a 7B model trained on
trillions of tokens. That gap is compute and data. It does not close with better
technique, and the configs are sized so you do not discover this a week in.

The binding constraint is usually data rather than compute. Feeding
`bread_large` its compute-optimal budget takes about 52 GB of text you are
willing to train on.

A pretrained model is also a *base* model: it completes text and does not follow
instructions until you fine-tune it. See [PRETRAINING.md](PRETRAINING.md).

## The old char-level trainer is a toy

`scripts/train_tiny_scratch.py` trains a few-million-parameter character-level
transformer on a few megabytes of text. It is included because watching a loss
curve fall and samples go from noise to word-shaped text teaches you something
real about how pretraining works.

It will not write code. It will not answer questions. It is not a small version
of a useful model, it is a demonstration of a mechanism. The script says so when
you run it, and the config says so in its header.

## A baked Bread model is still a derivative

`scripts/bake_bread_model.py` produces weights that answer as Bread and ship as
one directory. That is a real model file, and it is a fine-tune of an
open-weight base, not a model trained from nothing.

The generated model card says which base, under which license, and what the
fine-tune did and did not change. Keep those sections if you share the weights.
Removing them does not make the model more original; it only makes the claim
dishonest.

## Bread is not as capable as a hosted frontier model

A 7B or 14B open-weight coding model is good at: completing code in a familiar
idiom, explaining a function, writing a test, spotting an obvious bug, boilerplate
of every kind, and translating between languages.

It is meaningfully weaker at: reasoning across many files, holding a long
specification in mind, catching subtle logic errors, knowing recent library
versions, and admitting uncertainty. Bread's system prompt pushes hard on that
last one, and a smaller model still confabulates more than a larger one.

Read the code Bread writes before you run it. Bread will never run it for you.

## Fine-tuning teaches style, not facts

LoRA is very good at teaching a model *how* to respond: your naming conventions,
your project's structure, the shape of the answers you want.

It is unreliable at teaching *what* is true. Facts injected by fine-tuning are
learned inconsistently and can degrade the model's existing knowledge. If you
want the model to know your API surface, put the documentation in a knowledge
space and let retrieval supply it. That works far better and can be updated
without retraining.

## Retrieval is not perfect recall

Retrieval finds chunks that are semantically near your question. It does not
guarantee the right chunk is among them, and it cannot find something that was
never indexed. When Bread's context does not answer the question, the system
prompt tells it to say so instead of stretching. Smaller models follow that
instruction imperfectly.

If `sentence-transformers` is not installed or its model is not cached, Bread
falls back to a hashing encoder. That fallback works offline and is clearly
weaker than a trained encoder: it matches shared vocabulary rather than shared
meaning. Bread reports which encoder produced an index rather than letting you
assume.

## Secret scanning and license detection are filters, not guarantees

The secret scanner matches known credential patterns and flags high-entropy
strings. It will miss credentials that look like ordinary text, and it will flag
some things that are not credentials.

License detection reads LICENSE files, SPDX headers and package metadata. It
does not read the license, understand dual licensing, notice a vendored
directory under a different license, or give legal advice. Anything it cannot
identify is marked `UNKNOWN` and excluded by default.

Both are there to make the common mistakes less likely. Review what you plan to
publish.

## Security boundaries

Bread has no user accounts and no per-user authorisation. Everyone who can reach
the API can do everything: read every conversation, every indexed document, and
start training runs. API keys gate access to the whole server, not to parts of
it.

There is no transport encryption. Binding to a LAN address sends your traffic in
plaintext across that network unless you put a reverse proxy with TLS in front.

Bread does not sandbox model output. It does not execute generated code, but it
also does not stop you from copying it and running it yourself.

## Performance is what the hardware allows

On an RTX 5090 with a 7B model at 4-bit, expect roughly 40–80 tokens per second
depending on context length. A 14B model runs roughly half that. Long contexts
slow generation and consume VRAM quadratically in attention.

QLoRA on 5,000 short examples with the shipped 7B config takes roughly 25–45
minutes per epoch. The 14B config takes roughly twice that. These are estimates
from the shape of the work, not benchmarks from your machine; measure your own.

## The dependency stack is fragile in one specific place

Everything Bread needs to run the interface, the API and the dataset tools is in
`requirements.txt` and installs cleanly.

PyTorch with CUDA is the exception. It must match your driver, and for the RTX
5090 specifically it must be built against CUDA 12.8 or newer, or kernels fail
at launch with "no kernel image is available for execution on the device". This
is not something Bread can fix from a requirements file, which is why torch is
deliberately not in one. See the setup docs.
