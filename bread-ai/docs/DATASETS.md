# Building training data

The quality of a fine-tune is decided here, not in the training config. A few
thousand clean, well-formed examples in the style you want beat a hundred
thousand scraped ones.

## Where to get data, in order of preference

1. **Your own code.** You know its license, it is in your style, and a model
   tuned on it writes code that fits your projects. This is the default and the
   recommendation.
2. **Your own writing.** Notes, documentation, design docs. Keeps the model's
   English register from collapsing into code-comment voice.
3. **CodeSearchNet.** Function-and-docstring pairs, which map naturally onto
   instruction tuning. Requires accepting the upstream terms.
4. **The Stack (small samples).** Large and permissively-licensed at the corpus
   level. Requires accepting terms, and see the caveats below.
5. **FineWeb-Edu.** Web text filtered for educational value. Web-scale risks.
6. **OpenWebText.** Experimental, unclear per-document provenance. Last resort.

Bread never scrapes websites, and never downloads from an external host without
`--accept-terms` on the command line or `accept_terms: true` in an API request.

## Collecting your own code

```bash
python scripts/collect_local_code.py \
  --path "C:/dev/minecraft-plugins" \
  --path "~/projects" \
  --languages python java typescript lua luau go rust \
  --max-records 5000
```

The collector derives instruction tasks from the documentation your code
already carries rather than asking the model to restate files. One documented
function becomes an `implement`, an `explain` and a `document` task; a project's
tests become `test` tasks. See [QUALITY.md](QUALITY.md) for why that matters and
what gets filtered out.

For each file the collector:

- finds the project it belongs to by walking up to the nearest LICENSE file or
  build manifest, so a folder of checkouts is handled correctly;
- detects that project's license and skips it unless the license is on the
  allowlist;
- skips files that look generated or minified, or that are unusually large;
- scans for credentials and skips the file if it finds any;
- records the license, language, repository and relative path on every record.

Check what would be collected before you run it:

```bash
python scripts/license_check.py --path ~/projects
```

"No records collected" almost always means no project under those paths has a
LICENSE file Bread recognises.

## Licenses

The default allowlist is the set of permissive licenses least likely to
constrain what you do next:

```
MIT   Apache-2.0   BSD-2-Clause   BSD-3-Clause   ISC   Unlicense   CC0-1.0
```

Anything else, including anything unrecognised, is excluded. Override
deliberately:

```bash
python scripts/collect_local_code.py --path ~/projects --allow-license MPL-2.0
python scripts/collect_local_code.py --path ~/mine --allow-unlicensed
```

`--allow-unlicensed` is for code that is yours and simply has no LICENSE file.
Do not use it on anything you intend to publish.

Three things are worth stating plainly:

- **Detection is heuristic.** It reads LICENSE files, SPDX headers and package
  metadata. It does not read the license, notice dual licensing, catch a vendored
  directory under different terms, or give legal advice.
- **A permissive label does not clear every record.** Upstream datasets infer
  license metadata at scale and get it wrong sometimes. A dataset-level label
  says nothing about a specific file inside it.
- **Redistribution, commercial use and publishing weights are three separate
  questions.** A license that permits one may constrain another. Read them
  before you do any of the three.

`configs/licenses.yaml` records the policy and the obligations each license
carries.

## Secrets

Every collected file is scanned for credential patterns: cloud keys, GitHub and
GitLab tokens, Slack and Discord tokens, provider API keys, private key blocks,
JWTs, connection strings with inline passwords, and high-entropy strings in
assignment position. Files that match are skipped.

You can scan independently, including as a pre-commit hook:

```bash
python scripts/scan_secrets.py --path ~/projects
python scripts/scan_secrets.py --dataset data/datasets/local_code.jsonl
```

It exits non-zero when it finds something. Findings report the pattern and the
line, never the secret.

This is a filter, not a guarantee. If it flags something real, rotate the
credential; do not just remove it from the dataset.

## Cleaning and deduplication

```bash
python scripts/clean_dataset.py --input data/datasets/local_code.jsonl
```

Dropped: records too short to teach anything, records too long for the training
sequence, files that announce themselves as generated, minified bundles, and
text that is mostly non-ASCII. Rewritten: line endings, trailing whitespace,
runs of blank lines, and anything matching a credential pattern (replaced with a
marker so the surrounding code still parses).

Deduplication removes exact duplicates by hash and near-duplicates by MinHash
over word 5-grams, which catches the same file copied between projects with a
header changed.

Duplication matters more than it looks. A corpus with heavy duplication teaches
memorisation rather than generalisation, and the duplicated passages are exactly
what the model reproduces verbatim.

## Record shapes

Bread reads three JSONL shapes:

```jsonc
// sft_chat — the training format
{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
 "meta": {"source": "local_code", "license": "MIT", "language": "python", "path": "src/a.py"}}

// sft_instruction
{"instruction": "...", "input": "...", "output": "...", "meta": {...}}

// raw_text
{"text": "...", "meta": {...}}
```

`meta` carries provenance and is never dropped. Do not strip it when converting
between formats: it is what lets you answer, months later, where a training
example came from.

## Building the training file

```bash
python scripts/build_sft_dataset.py \
  --input data/datasets/local_code.clean.jsonl \
  --input data/datasets/codesearchnet.clean.jsonl \
  --output data/datasets/bread_sft.jsonl \
  --eval-ratio 0.02
```

This converts every shape into `sft_chat`, cleans, deduplicates, shuffles and
holds out an evaluation split. The split is taken before shuffling the training
half, so a near-duplicate cannot land on both sides.

## Validate and report before training

```bash
python scripts/validate_dataset.py --input data/datasets/bread_sft.jsonl
python scripts/dataset_report.py   --input data/datasets/bread_sft.jsonl
```

Validation is not optional. A malformed record does not fail loudly during
training; it silently teaches the model something you did not intend.

The report gives you record count, approximate tokens, language and license
breakdowns, and the length distribution. Compare its p99 against your config's
`max_seq_length`: anything longer gets truncated mid-example.

## External sources

```bash
python scripts/collect_codesearchnet.py --config python --max-records 3000 --accept-terms
python scripts/collect_stack_sample.py  --config data/python --max-records 2000 --accept-terms
python scripts/collect_fineweb_edu.py   --max-records 2000 --accept-terms
python scripts/collect_openwebtext.py   --max-records 1000 --accept-terms
```

Each streams from the upstream host and stops at the record cap, so it also caps
how much is downloaded. Each writes a manifest recording the dataset name, the
source URL, the terms URL, the subset, the record cap and the timestamp.

The Stack has an opt-out process. A snapshot you collected earlier does not
reflect later removals; re-check before publishing anything derived from it.

## Running a whole plan

```bash
cp configs/datasets/sources.example.yaml configs/datasets/sources.yaml
# edit the paths
python scripts/collect_code.py --plan configs/datasets/sources.yaml
python scripts/collect_code.py --plan configs/datasets/sources.yaml --accept-terms
```

Local sources run unconditionally. External sources run only when the plan marks
them `enabled: true` **and** you passed `--accept-terms`. Enabling an entry in a
file is not consent on its own; the flag is.

## How much data do you need

For a LoRA that shifts style and conventions: 500 to 2,000 good examples.
For one that teaches a library or a framework well: 5,000 to 20,000.
Beyond roughly 50,000 you are into territory where full fine-tuning starts to
make more sense than an adapter.

More is not automatically better. A thousand examples you would be happy to show
someone beat ten thousand you have not read.
