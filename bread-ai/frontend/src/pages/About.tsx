/** What Bread is, what it is not, and where its data lives. */

import { useSystemStatus } from "../api/hooks";
import { InlineNotice, LoadingState } from "../components/States";

export default function About() {
  const system = useSystemStatus(60_000);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <header className="mb-6 text-center">
        <p className="text-5xl" aria-hidden>
          🍞
        </p>
        <h1 className="mt-3 text-xl font-semibold text-ink-100">Bread</h1>
        <p className="mt-1 text-sm text-ink-400">
          A local-first coding assistant. Version {system.data?.version ?? "…"}
        </p>
      </header>

      <section className="panel mb-5 p-5">
        <h2 className="mb-2 text-sm font-medium text-ink-200">What Bread is</h2>
        <p className="text-sm leading-relaxed text-ink-300">
          Bread runs an existing open-weight coding model on your own machine, indexes your own
          documents for retrieval, and fine-tunes adapters on your own GPU. It is built for
          programming work: explaining code, generating it, debugging stack traces, refactoring,
          reviewing, writing tests and documentation, and turning plain-English requirements into
          a working project.
        </p>
      </section>

      <section className="panel mb-5 p-5">
        <h2 className="mb-2 text-sm font-medium text-ink-200">What Bread is not</h2>
        <div className="space-y-3 text-sm leading-relaxed text-ink-300">
          <p>
            Bread is not Claude, GPT or any other hosted frontier model, and it does not match
            them. It runs a smaller open-weight model, and the difference in capability is real.
          </p>
          <p>
            Bread does not train a language model from scratch, and neither does any single
            consumer GPU. Pretraining a frontier model takes thousands of accelerators running for
            weeks over trillions of tokens, plus the data pipeline and infrastructure to feed them.
            An RTX 5090 with 32 GB is a serious card, and it is roughly six orders of magnitude
            short of that.
          </p>
          <p>
            What one RTX 5090 does very well is LoRA and QLoRA fine-tuning: freezing a pretrained
            model and training small adapter matrices on top. That teaches the model your
            conventions, your libraries and your task mix. It is a real improvement on the work you
            actually do, and it is a different thing from pretraining.
          </p>
          <p>
            Bread ships a tiny from-scratch trainer as well. It is labelled a toy because it is
            one: a few million parameters on a few megabytes of text, there to make the mechanics
            of pretraining concrete. It will not produce a useful assistant.
          </p>
        </div>
      </section>

      <section className="panel mb-5 p-5">
        <h2 className="mb-2 text-sm font-medium text-ink-200">Your data</h2>
        <ul className="space-y-2 text-sm leading-relaxed text-ink-300">
          <li>· Conversations, documents, vectors and datasets live in one directory on this machine.</li>
          <li>· There is no telemetry, no analytics and no background upload. None.</li>
          <li>· The only outbound requests are model or dataset downloads you explicitly confirm.</li>
          <li>· Bread binds to 127.0.0.1 by default and warns loudly before binding anywhere else.</li>
          <li>· Bread never executes code it generated, and never executes code you uploaded.</li>
        </ul>
        {system.isLoading && <LoadingState label="Reading system status" />}
        {system.data && (
          <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-2">
            <div>
              <dt className="text-ink-500">Data directory</dt>
              <dd className="break-all font-mono text-ink-200">{system.data.data_dir}</dd>
            </div>
            <div>
              <dt className="text-ink-500">Database</dt>
              <dd className="break-all font-mono text-ink-200">{system.data.database_url}</dd>
            </div>
            <div>
              <dt className="text-ink-500">Platform</dt>
              <dd className="font-mono text-ink-200">{system.data.platform}</dd>
            </div>
            <div>
              <dt className="text-ink-500">Python</dt>
              <dd className="font-mono text-ink-200">{system.data.python_version}</dd>
            </div>
          </dl>
        )}
      </section>

      <section className="panel mb-5 p-5">
        <h2 className="mb-2 text-sm font-medium text-ink-200">Licensing and training data</h2>
        <div className="space-y-2 text-sm leading-relaxed text-ink-300">
          <p>
            Bread's dataset tools record the license of every record they collect and refuse to
            include code whose license they cannot identify. That is a filter, not a legal
            clearance.
          </p>
          <p>
            Redistributing collected data, publishing weights fine-tuned on it, and using either
            commercially are three separate questions with three separate answers. Read the
            licenses of what you collected before you do any of them.
          </p>
        </div>
      </section>

      <InlineNotice tone="info">
        Bread is not affiliated with Anthropic, OpenAI, Mojang, Roblox, or any model or dataset
        provider it can be pointed at. The name and the loaf are its own.
      </InlineNotice>
    </div>
  );
}
