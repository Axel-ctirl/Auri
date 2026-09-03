/** Runtime settings, API keys and the local-data statement. */

import { Copy, KeyRound, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { describeError, getApiKey, setApiKey } from "../api/client";
import {
  useApiKeys,
  useCreateApiKey,
  useRevokeApiKey,
  useSettings,
  useSystemStatus,
  useUpdateSettings,
} from "../api/hooks";
import { ErrorState, InlineNotice, LoadingState } from "../components/States";
import { formatBytes, formatRelativeTime } from "../lib/format";

export default function Settings() {
  const settings = useSettings();
  const update = useUpdateSettings();
  const system = useSystemStatus(30_000);
  const keys = useApiKeys();
  const createKey = useCreateApiKey();
  const revokeKey = useRevokeApiKey();

  const [draft, setDraft] = useState<Record<string, number | boolean | string>>({});
  const [storedKey, setStoredKey] = useState(getApiKey());
  const [newKeyLabel, setNewKeyLabel] = useState("this machine");
  const [issuedKey, setIssuedKey] = useState<string | null>(null);

  useEffect(() => {
    if (settings.data) {
      setDraft({
        temperature: settings.data.temperature,
        top_p: settings.data.top_p,
        repetition_penalty: settings.data.repetition_penalty,
        max_new_tokens: settings.data.max_new_tokens,
        max_context_length: settings.data.max_context_length,
        rag_enabled: settings.data.rag_enabled,
        rag_top_k: settings.data.rag_top_k,
        rag_rerank_enabled: settings.data.rag_rerank_enabled,
        chunk_size: settings.data.chunk_size,
        chunk_overlap: settings.data.chunk_overlap,
        allow_model_download: settings.data.allow_model_download,
      });
    }
  }, [settings.data]);

  if (settings.isLoading) return <LoadingState label="Loading settings" />;
  if (settings.isError) {
    return <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />;
  }
  if (!settings.data) return null;

  const numberField = (
    key: string,
    label: string,
    props: { min?: number; max?: number; step?: number; help?: string } = {},
  ) => (
    <div>
      <label className="label" htmlFor={`setting-${key}`}>
        {label}
      </label>
      <input
        id={`setting-${key}`}
        type="number"
        className="field"
        min={props.min}
        max={props.max}
        step={props.step ?? 1}
        value={String(draft[key] ?? "")}
        onChange={(event) => setDraft({ ...draft, [key]: Number(event.target.value) })}
      />
      {props.help && <p className="mt-1 text-xs text-ink-500">{props.help}</p>}
    </div>
  );

  const toggleField = (key: string, label: string, help?: string) => (
    <label className="flex items-start gap-2 text-sm text-ink-200">
      <input
        type="checkbox"
        className="mt-1 accent-crust-500"
        checked={Boolean(draft[key])}
        onChange={(event) => setDraft({ ...draft, [key]: event.target.checked })}
      />
      <span>
        {label}
        {help && <span className="mt-0.5 block text-xs text-ink-500">{help}</span>}
      </span>
    </label>
  );

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="text-lg font-semibold text-ink-100">Settings</h1>
        <p className="mt-1 text-sm text-ink-400">
          Changes here are saved to the local database and applied immediately. Network settings
          such as the bind address are deliberately not editable over HTTP; change them in .env.
        </p>
      </header>

      <form
        className="panel mb-6 space-y-4 p-4"
        onSubmit={(event) => {
          event.preventDefault();
          update.mutate(draft);
        }}
      >
        <h2 className="text-sm font-medium text-ink-200">Generation</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {numberField("temperature", "Temperature", {
            min: 0,
            max: 2,
            step: 0.05,
            help: "0.0-0.3 for code. Higher values wander.",
          })}
          {numberField("top_p", "Top-p", { min: 0, max: 1, step: 0.01 })}
          {numberField("repetition_penalty", "Repetition penalty", {
            min: 0.5,
            max: 2,
            step: 0.01,
          })}
          {numberField("max_new_tokens", "Max new tokens", { min: 1, max: 32768, step: 64 })}
          {numberField("max_context_length", "Max context length", {
            min: 512,
            max: 1048576,
            step: 512,
            help: "Longer context costs VRAM quadratically in attention.",
          })}
        </div>

        <h2 className="pt-2 text-sm font-medium text-ink-200">Retrieval</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {numberField("rag_top_k", "Top-k chunks", { min: 1, max: 50 })}
          {numberField("chunk_size", "Chunk size", { min: 100, max: 8000, step: 50 })}
          {numberField("chunk_overlap", "Chunk overlap", { min: 0, max: 2000, step: 25 })}
        </div>
        <div className="space-y-2">
          {toggleField("rag_enabled", "Retrieval enabled")}
          {toggleField(
            "rag_rerank_enabled",
            "Rerank results with a cross-encoder",
            "More accurate and slower. Silently skipped when the reranker model is not cached.",
          )}
          {toggleField(
            "allow_model_download",
            "Allow model downloads without per-request confirmation",
            "Off by default so a stray click cannot pull fifteen gigabytes.",
          )}
        </div>

        <p className="text-xs text-ink-500">
          Changing chunk size or overlap only affects documents indexed afterwards. Re-index a
          space from the Documents page to apply it to what is already there.
        </p>

        <button type="submit" className="btn-primary" disabled={update.isPending}>
          <Save className="h-4 w-4" aria-hidden />
          {update.isPending ? "Saving…" : "Save settings"}
        </button>
        {update.isError && (
          <InlineNotice tone="danger">{describeError(update.error).message}</InlineNotice>
        )}
        {update.isSuccess && <InlineNotice tone="success">Settings saved.</InlineNotice>}
      </form>

      {/* --------------------------------------------------- read-only */}
      <section className="panel mb-6 p-4">
        <h2 className="mb-3 text-sm font-medium text-ink-200">Configuration (read-only)</h2>
        <dl className="grid gap-3 text-xs sm:grid-cols-2">
          {[
            ["Model backend", settings.data.model_backend],
            ["Model id", settings.data.model_id],
            ["Tokenizer", settings.data.tokenizer_id],
            ["Quantization", settings.data.quantization_mode],
            ["Adapter", settings.data.adapter_path || "(none)"],
            ["Embedding model", settings.data.embedding_model_id],
            ["Vector store", settings.data.vector_backend],
            ["System prompt", settings.data.system_prompt_path],
            ["Bind address", `${settings.data.host}:${settings.data.port}`],
            ["API key required", settings.data.require_api_key ? "yes" : "no"],
            ["Max upload", formatBytes(settings.data.max_upload_bytes)],
            ["Data directory", settings.data.data_dir],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-ink-500">{label}</dt>
              <dd className="break-all font-mono text-ink-200">{value}</dd>
            </div>
          ))}
        </dl>
        {system.data?.warnings.map((warning) => (
          <div key={warning} className="mt-3">
            <InlineNotice tone="warning">{warning}</InlineNotice>
          </div>
        ))}
      </section>

      {/* ------------------------------------------------------ API keys */}
      <section className="panel mb-6 space-y-3 p-4">
        <h2 className="text-sm font-medium text-ink-200">API keys</h2>
        <p className="text-xs text-ink-400">
          Keys matter when Bread is reachable beyond localhost. Binding to a LAN address forces key
          checks on regardless of the setting above. The plaintext is shown once; Bread stores only
          its SHA-256 hash.
        </p>

        <div className="flex flex-wrap gap-2">
          <input
            className="field flex-1"
            value={newKeyLabel}
            onChange={(event) => setNewKeyLabel(event.target.value)}
            placeholder="Label, for example: my laptop"
            aria-label="API key label"
          />
          <button
            type="button"
            className="btn-ghost"
            disabled={createKey.isPending}
            onClick={async () => {
              const created = await createKey.mutateAsync({ label: newKeyLabel });
              setIssuedKey(created.key);
            }}
          >
            <KeyRound className="h-4 w-4" aria-hidden />
            Create key
          </button>
        </div>

        {issuedKey && (
          <div className="rounded-lg border border-emerald-900/60 bg-emerald-950/20 p-3">
            <p className="text-xs text-emerald-200">
              Copy this now. It is not shown again.
            </p>
            <div className="mt-2 flex items-center gap-2">
              <code className="flex-1 break-all rounded bg-ink-950 px-2 py-1 font-mono text-xs text-crust-200">
                {issuedKey}
              </code>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => void navigator.clipboard.writeText(issuedKey)}
              >
                <Copy className="h-4 w-4" aria-hidden />
              </button>
            </div>
          </div>
        )}

        <ul className="divide-y divide-ink-800">
          {keys.data?.map((key) => (
            <li key={key.id} className="flex items-center justify-between gap-2 py-2 text-sm">
              <div className="min-w-0">
                <p className="text-ink-200">
                  {key.label} <span className="font-mono text-xs text-ink-500">{key.key_prefix}…</span>
                </p>
                <p className="text-xs text-ink-500">
                  created {formatRelativeTime(key.created_at)} · last used{" "}
                  {formatRelativeTime(key.last_used_at)}
                  {key.revoked ? " · revoked" : ""}
                </p>
              </div>
              {!key.revoked && (
                <button
                  type="button"
                  aria-label={`Revoke ${key.label}`}
                  className="rounded p-1.5 text-ink-500 hover:bg-ink-800 hover:text-red-300"
                  onClick={() => revokeKey.mutate(key.id)}
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </button>
              )}
            </li>
          ))}
        </ul>

        <div>
          <label className="label" htmlFor="browser-key">
            Key this browser sends
          </label>
          <div className="flex gap-2">
            <input
              id="browser-key"
              type="password"
              className="field font-mono text-xs"
              value={storedKey}
              onChange={(event) => setStoredKey(event.target.value)}
              placeholder="bread_sk_…"
            />
            <button
              type="button"
              className="btn-ghost"
              onClick={() => setApiKey(storedKey)}
            >
              Save locally
            </button>
          </div>
          <p className="mt-1 text-xs text-ink-500">
            Stored in this browser's localStorage and sent as the X-API-Key header. It never
            leaves this machine.
          </p>
        </div>
      </section>
    </div>
  );
}
