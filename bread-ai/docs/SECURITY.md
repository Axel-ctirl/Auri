# Security

Bread is designed for one person on one machine. This page says what it protects
against, what it does not, and what changes when you expose it.

## The default posture

Bread binds to `127.0.0.1`. Only processes on your machine can reach it. In that
configuration an API key is optional, because the operating system is already
the access control.

## What changes when you bind wider

Setting `BREAD_HOST` to anything other than a loopback address makes Bread
reachable from your network. Three things happen automatically:

1. **API keys become mandatory.** Not "recommended": the dependency enforces
   them regardless of `BREAD_REQUIRE_API_KEY`.
2. **The CLI asks for confirmation** before starting, unless
   `BREAD_ALLOW_LAN_BINDING=true` says you meant it.
3. **The interface shows a banner**, and `/api/system/status` returns warnings.

What does **not** happen automatically is transport encryption. Bread speaks
plain HTTP. Over a LAN that means your prompts, your indexed documents and your
API key travel in cleartext to anyone who can see the traffic.

If you need access from another machine, an SSH tunnel is strictly better than
binding wider:

```bash
ssh -L 8000:127.0.0.1:8000 user@your-machine
```

Encrypted, authenticated, and nothing new listens on the network. If you must
bind wider anyway, put a reverse proxy with TLS in front of it.

## API keys

```bash
cd backend && python -m app.cli create-key --label "my laptop"
```

or `POST /api/api-keys`, or the Settings page. The plaintext is shown once;
Bread stores only its SHA-256 hash. Send it as `X-API-Key` or as
`Authorization: Bearer …`.

`/api/health` stays open so a process supervisor can probe it. Everything else
is gated when enforcement is on.

Keys are all-or-nothing. There are no scopes in practice: a key that can chat
can also start a training run and read every indexed document. Treat one as a
password for the whole server.

Revoking a key is immediate.

## Rate limiting

A fixed window per caller, keyed by API key when present and by client address
otherwise. Defaults to 120 requests per 60 seconds; `BREAD_RATE_LIMIT_REQUESTS`
and `BREAD_RATE_LIMIT_WINDOW` change it.

It is in-process, which is enough for one local server and would need to move
into SQLite or Redis if Bread ever ran multiple workers.

## Upload handling

Uploads are the largest untrusted-input surface, so:

- **Filenames are rebuilt, not trusted.** Directory components are stripped,
  Unicode is normalised, everything outside `[A-Za-z0-9._-]` becomes an
  underscore, and the result is checked for containment inside the uploads
  directory. `../../etc/passwd` becomes `passwd`.
- **Extensions are allowlisted.** Twenty-six types are accepted; everything else
  is refused with a message.
- **Size is capped** by `BREAD_MAX_UPLOAD_BYTES`, 25 MB by default.
- **Content is never executed.** Uploaded source code is read as bytes, decoded
  as text, hashed and embedded. It is never imported, evaluated or run.

## Generated code is never executed

Bread has no code interpreter, no shell tool and no automatic execution path.
Model output is text that gets rendered as Markdown. Raw HTML in that output is
not rendered as markup, so a model cannot inject script into the page.

Read what Bread writes before you run it. That is your job, and Bread will not
do it for you.

## Path handling on the API

Two endpoints accept a filesystem path from the caller, and both are constrained:

- **Dataset paths** (`/api/datasets/report`, `/api/datasets/validate`) must
  resolve inside the Bread data directory. Otherwise the report endpoint would be
  an arbitrary-file-read primitive.
- **Training config paths** (`/api/training/start`) must resolve inside
  `configs/`. That path becomes `argv` for a subprocess, so it is not a place to
  be relaxed.

Both return a structured error naming the constraint rather than a bare 403.

## Secrets in training data

The dataset collector scans every file for credential patterns and skips the
ones that match. `scripts/scan_secrets.py` runs the same scan on demand and
exits non-zero when it finds something, which makes it usable as a pre-commit
hook.

This is a filter, not a guarantee. Patterns miss credentials that look like
ordinary text. If the scanner flags something real, rotate it; removing it from
the dataset does not un-leak it.

## Audit log

State-changing actions are recorded in the `audit_logs` table: model loads and
unloads, document uploads and deletions, knowledge space changes, dataset and
training runs, settings changes, key creation and revocation.

It is local and append-only from the application's perspective. Its purpose is
letting you answer "what changed and when" without any form of remote
telemetry.

## What Bread does not do

- **No user accounts.** One profile, no per-user authorisation.
- **No transport encryption.** Use SSH or a reverse proxy.
- **No sandboxing.** Bread's process has your user's permissions.
- **No secrets management.** The API key hash is in the SQLite file; protect it
  with filesystem permissions like any other local database.
- **No protection against a compromised model.** If you load weights from an
  untrusted source, you are running code that source controls. `TRUST_REMOTE_CODE`
  is off by default for exactly this reason; turning it on lets a model
  repository execute Python during load.

## Privacy

No telemetry. No analytics. No crash reporting. No update checks. No background
uploads. Bread makes exactly three kinds of outbound request, all of which you
initiate: downloading model weights, downloading a dataset, and talking to an
OpenAI-compatible endpoint you configured.

The `report_to: none` line in every training config keeps the training stack
from phoning a tracking service.

## Reporting a problem

Bread is a local tool with no server component, so most issues are local
misconfigurations rather than remote vulnerabilities. If you find something that
would let one machine reach another's Bread instance, or let uploaded content
escape the data directory, open an issue without a working exploit and describe
the mechanism.
