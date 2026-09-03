# GitHub Actions Workflow

CI workflows: triggers, matrices, caching, permissions and secret handling.

You are helping with a **GitHub Actions** workflow.

Get the security details right, because they are the ones that go wrong quietly:

- Set `permissions:` explicitly at the workflow or job level. The default token
  is broader than most workflows need; start from `contents: read` and add.
- Pin third-party actions to a commit SHA, not a moving tag. `uses:
  actions/checkout@v4` is acceptable for first-party actions; anything else
  should be pinned.
- Never use `pull_request_target` with a checkout of the PR head unless you
  fully understand that it runs untrusted code with write-scoped secrets.
- Do not interpolate untrusted input (`github.event.issue.title`,
  `github.head_ref`) directly into a `run:` block. Pass it through `env:` and
  reference the variable, or the title becomes a shell injection.
- Secrets are unavailable to workflows triggered by a fork's pull request. Say
  so rather than writing a workflow that silently fails for outside contributors.

For speed and clarity:

- Cache dependencies with `actions/cache` or the built-in cache in the setup
  actions, keyed on the lockfile hash.
- Use a matrix for versions and platforms, with `fail-fast: false` when you want
  to see every failure rather than the first.
- Set a `timeout-minutes` on every job. A hung job otherwise burns the full
  six hours.
- `concurrency` with `cancel-in-progress: true` stops a stack of superseded runs
  on the same branch.

Name steps in plain language. The step name is what someone reads at 2am when
the build is red.
