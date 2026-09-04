/** Fine-tuning: start a run, watch its loss, read its log. */

import { Activity, Play, Square, TestTube2 } from "lucide-react";
import { useState } from "react";

import { ApiError, describeError } from "../api/client";
import {
  useStartTraining,
  useStopTraining,
  useSystemStatus,
  useTrainingConfigs,
  useTrainingLogs,
  useTrainingRuns,
} from "../api/hooks";
import { EmptyState, ErrorState, InlineNotice, LoadingState } from "../components/States";
import { formatRelativeTime, formatVram } from "../lib/format";

/** Pull the preflight problem list out of a failed start response, if present. */
function preflightProblems(error: unknown): string[] {
  if (!(error instanceof ApiError)) return [];
  const problems = error.details?.problems;
  return Array.isArray(problems) ? problems.map(String) : [];
}

const STATUS_STYLES: Record<string, string> = {
  running: "border-sky-900/60 text-sky-300",
  completed: "border-emerald-900/60 text-emerald-300",
  failed: "border-red-900/60 text-red-300",
  stopped: "border-amber-900/60 text-amber-300",
  pending: "border-ink-700 text-ink-300",
};

export default function Training() {
  const runs = useTrainingRuns();
  const configs = useTrainingConfigs();
  const system = useSystemStatus();
  const start = useStartTraining();
  const stop = useStopTraining();

  const [name, setName] = useState("bread-qlora");
  const [configPath, setConfigPath] = useState("configs/training/qlora_7b.yaml");
  const [datasetPath, setDatasetPath] = useState("data/datasets/bread_sft.jsonl");
  const [selectedRunId, setSelectedRunId] = useState<string | undefined>();

  const logs = useTrainingLogs(selectedRunId, Boolean(selectedRunId));
  const gpu = system.data?.gpu;
  const selectedConfig = configs.data?.find((config) => config.path === configPath);

  const launch = async (dryRun: boolean) => {
    await start.mutateAsync({
      name,
      config_path: configPath,
      dataset_path: datasetPath || undefined,
      method: selectedConfig?.method ?? "qlora",
      dry_run: dryRun,
    });
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="text-lg font-semibold text-ink-100">Training</h1>
        <p className="mt-1 text-sm text-ink-400">
          Two paths. LoRA and QLoRA adapt an existing open-weight model to your code and your
          style, which is the fastest route to a strong assistant. Pretraining builds a model from
          random initialisation with nothing inherited, which is slower and smaller and entirely
          yours. Neither produces a frontier model on one GPU.
        </p>
      </header>

      {gpu && !gpu.cuda_available && (
        <div className="mb-5">
          <InlineNotice tone="warning">
            No CUDA device is visible, so training cannot start here. Bread checks this before
            launching anything, so you get this message rather than a run that hangs.
          </InlineNotice>
        </div>
      )}

      {gpu?.devices.map((device) => (
        <div key={device.index} className="mb-5">
          <InlineNotice tone="info">
            {device.name} · {formatVram(device.free_memory_mb)} free of{" "}
            {formatVram(device.total_memory_mb)}. If a run stops with CUDA out-of-memory, lower
            max_seq_length in the config first, then lora_r.
          </InlineNotice>
        </div>
      ))}

      <form
        className="panel mb-6 space-y-3 p-4"
        onSubmit={(event) => {
          event.preventDefault();
          void launch(false);
        }}
      >
        <h2 className="text-sm font-medium text-ink-200">Start a run</h2>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="run-name">
              Run name
            </label>
            <input
              id="run-name"
              className="field"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="run-config">
              Config
            </label>
            <select
              id="run-config"
              className="field"
              value={configPath}
              onChange={(event) => setConfigPath(event.target.value)}
            >
              {configs.data?.map((config) => (
                <option key={config.path} value={config.path}>
                  {config.name}
                  {config.min_vram_gb ? ` — needs about ${config.min_vram_gb} GB` : ""}
                </option>
              ))}
            </select>
          </div>
        </div>

        {selectedConfig?.description && (
          <p className="text-xs text-ink-400">{selectedConfig.description}</p>
        )}

        <div>
          <label className="label" htmlFor="run-dataset">
            {selectedConfig?.method === "pretrain"
              ? "Packed corpus (.bin)"
              : "Dataset (.jsonl)"}
          </label>
          <input
            id="run-dataset"
            className="field font-mono text-xs"
            value={datasetPath}
            onChange={(event) => setDatasetPath(event.target.value)}
            placeholder={
              selectedConfig?.method === "pretrain"
                ? "data/pretrain/corpus.bin"
                : "data/datasets/bread_sft.jsonl"
            }
          />
        </div>

        {selectedConfig?.method === "pretrain" && (
          <InlineNotice tone="info">
            This trains a model from random initialisation. Nothing is inherited from any other
            model, and the result is entirely yours. It will be fluent and small, and it will not
            match a 7B model trained on trillions of tokens. Start with the tiny config to prove
            your corpus before committing days of GPU time.
          </InlineNotice>
        )}

        {selectedConfig?.method === "tiny_scratch" && (
          <InlineNotice tone="warning">
            This config trains a few-million-parameter model from scratch. It is an educational
            demonstration of pretraining mechanics. It will not produce a useful assistant, and no
            amount of tuning on one GPU will change that.
          </InlineNotice>
        )}

        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-ghost" onClick={() => void launch(true)}>
            <TestTube2 className="h-4 w-4" aria-hidden />
            Dry run
          </button>
          <button type="submit" className="btn-primary" disabled={start.isPending}>
            <Play className="h-4 w-4" aria-hidden />
            Start training
          </button>
        </div>
        <p className="text-xs text-ink-500">
          Run the dry run first. It checks the config, the dataset and the GPU and reports every
          problem it finds without launching anything.
        </p>

        {start.isError && (
          <div className="space-y-1">
            <InlineNotice tone="danger">{describeError(start.error).message}</InlineNotice>
            {preflightProblems(start.error).map((problem) => (
              <p key={problem} className="text-xs text-red-300">
                · {problem}
              </p>
            ))}
          </div>
        )}
      </form>

      <h2 className="mb-3 text-sm font-medium text-ink-200">Runs</h2>
      {runs.isLoading && <LoadingState label="Loading runs" />}
      {runs.isError && <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />}
      {runs.data?.length === 0 && (
        <EmptyState
          icon={<Activity className="h-7 w-7" />}
          title="No training runs yet"
          description="Build a dataset on the Datasets page first, then start a QLoRA run here."
        />
      )}

      <div className="space-y-2">
        {runs.data?.map((run) => {
          const progress =
            run.total_steps && run.total_steps > 0
              ? Math.min(100, (run.current_step / run.total_steps) * 100)
              : null;
          return (
            <article key={run.id} className="panel p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="font-medium text-ink-100">{run.name}</h3>
                  <p className="truncate font-mono text-xs text-ink-500">
                    {run.base_model_id} · {run.config_path.split(/[\\/]/).pop()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="badge">{run.method}</span>
                  <span className={`badge ${STATUS_STYLES[run.status] ?? ""}`}>{run.status}</span>
                  {run.status === "running" && (
                    <button
                      type="button"
                      className="btn-danger py-1"
                      onClick={() => stop.mutate(run.id)}
                    >
                      <Square className="h-3.5 w-3.5" aria-hidden />
                      Stop
                    </button>
                  )}
                </div>
              </div>

              {progress !== null && (
                <div className="mt-3">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-800">
                    <div
                      className="h-full bg-crust-500 transition-all"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <p className="mt-1 text-xs text-ink-500">
                    step {run.current_step} of {run.total_steps}
                  </p>
                </div>
              )}

              <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
                <div>
                  <dt className="text-ink-500">Train loss</dt>
                  <dd className="font-mono text-ink-200">{run.train_loss?.toFixed(4) ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-ink-500">Eval loss</dt>
                  <dd className="font-mono text-ink-200">{run.eval_loss?.toFixed(4) ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-ink-500">Started</dt>
                  <dd className="text-ink-200">{formatRelativeTime(run.started_at)}</dd>
                </div>
                <div>
                  <dt className="text-ink-500">Output</dt>
                  <dd className="truncate font-mono text-ink-200" title={run.output_dir}>
                    {run.output_dir.split(/[\\/]/).pop()}
                  </dd>
                </div>
              </dl>

              {run.error && (
                <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded border border-red-900/60 bg-red-950/30 p-2 text-xs text-red-200">
                  {run.error}
                </pre>
              )}

              <button
                type="button"
                className="mt-3 text-xs text-crust-300 underline"
                onClick={() => setSelectedRunId(selectedRunId === run.id ? undefined : run.id)}
              >
                {selectedRunId === run.id ? "Hide log" : "Show log"}
              </button>

              {selectedRunId === run.id && (
                <pre className="mt-2 max-h-72 overflow-auto rounded border border-ink-800 bg-ink-950 p-3 font-mono text-[11px] leading-relaxed text-ink-300">
                  {logs.data?.lines.length
                    ? logs.data.lines.join("\n")
                    : "No log output yet. The file appears once the training process starts writing."}
                </pre>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
