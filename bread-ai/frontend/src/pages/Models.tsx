/** Model catalogue, load/unload, and the GPU picture. */

import { Cpu, Download, Play, Plus, Square, Trash2 } from "lucide-react";
import { useState } from "react";

import { describeError } from "../api/client";
import {
  useDeleteModel,
  useLoadModel,
  useModelStatus,
  useModels,
  useRegisterModel,
  useSystemStatus,
  useUnloadModel,
} from "../api/hooks";
import { ErrorState, InlineNotice, LoadingState } from "../components/States";
import { formatVram } from "../lib/format";

export default function Models() {
  const models = useModels();
  const status = useModelStatus();
  const system = useSystemStatus();
  const load = useLoadModel();
  const unload = useUnloadModel();
  const register = useRegisterModel();
  const remove = useDeleteModel();

  const [showRegister, setShowRegister] = useState(false);
  const [form, setForm] = useState({
    name: "",
    model_id: "",
    backend: "transformers",
    quantization_mode: "4bit",
    adapter_path: "",
    gguf_path: "",
    notes: "",
  });

  const gpu = system.data?.gpu;

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="text-lg font-semibold text-ink-100">Models</h1>
        <p className="mt-1 text-sm text-ink-400">
          Bread never downloads weights on its own. Loading a model that is not already in your
          Hugging Face cache needs an explicit confirmation.
        </p>
      </header>

      {/* ---------------------------------------------------- GPU panel */}
      <section className="panel mb-5 p-4">
        <h2 className="mb-3 text-sm font-medium text-ink-200">Hardware</h2>
        {system.isLoading && <LoadingState label="Reading GPU status" />}
        {gpu && (
          <>
            {!gpu.torch_installed && (
              <InlineNotice tone="warning">
                PyTorch is not installed, so Bread cannot report VRAM or run the Transformers
                backend. Install the CUDA build first; see docs/WINDOWS_SETUP.md.
              </InlineNotice>
            )}
            {gpu.torch_installed && !gpu.cuda_available && (
              <InlineNotice tone="warning">
                torch.cuda.is_available() is false. Check that your NVIDIA driver is installed and
                that torch was built for a matching CUDA version.
              </InlineNotice>
            )}
            <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-4">
              <div>
                <dt className="text-ink-500">CUDA</dt>
                <dd className="text-ink-200">
                  {gpu.cuda_available ? gpu.cuda_version ?? "available" : "unavailable"}
                </dd>
              </div>
              <div>
                <dt className="text-ink-500">Torch</dt>
                <dd className="text-ink-200">{gpu.torch_version ?? "not installed"}</dd>
              </div>
              <div>
                <dt className="text-ink-500">Driver</dt>
                <dd className="text-ink-200">{gpu.driver_version ?? "unknown"}</dd>
              </div>
              <div>
                <dt className="text-ink-500">Devices</dt>
                <dd className="text-ink-200">{gpu.device_count}</dd>
              </div>
            </dl>
            {gpu.devices.map((device) => (
              <div key={device.index} className="mt-3 rounded-lg border border-ink-800 p-3 text-xs">
                <p className="font-medium text-ink-100">
                  GPU {device.index}: {device.name}
                </p>
                <p className="mt-1 text-ink-400">
                  {formatVram(device.free_memory_mb)} free of{" "}
                  {formatVram(device.total_memory_mb)} · {formatVram(device.allocated_memory_mb)}{" "}
                  allocated by this process
                </p>
              </div>
            ))}
          </>
        )}
      </section>

      {/* -------------------------------------------------- loaded model */}
      <section className="panel mb-5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium text-ink-200">Loaded model</h2>
            {status.data?.loaded ? (
              <p className="mt-1 text-sm text-ink-300">
                {status.data.model_id} · {status.data.backend} ·{" "}
                {status.data.quantization_mode ?? "unquantized"}
                {status.data.load_seconds !== null && status.data.load_seconds !== undefined
                  ? ` · loaded in ${status.data.load_seconds}s`
                  : ""}
              </p>
            ) : (
              <p className="mt-1 text-sm text-ink-400">
                Nothing is loaded. Chat requests will fail until you load one, unless the backend
                is set to mock.
              </p>
            )}
            {status.data?.detail && (
              <p className="mt-1 text-xs text-ink-500">{status.data.detail}</p>
            )}
          </div>
          <button
            type="button"
            className="btn-ghost"
            onClick={() => unload.mutate()}
            disabled={!status.data?.loaded || unload.isPending}
          >
            <Square className="h-4 w-4" aria-hidden />
            Unload
          </button>
        </div>
      </section>

      {load.isError && (
        <div className="mb-4">
          <ErrorState error={load.error} />
        </div>
      )}

      {/* ------------------------------------------------------ catalogue */}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-ink-200">Catalogue</h2>
        <button type="button" className="btn-ghost" onClick={() => setShowRegister((open) => !open)}>
          <Plus className="h-4 w-4" aria-hidden />
          Register a model
        </button>
      </div>

      {showRegister && (
        <form
          className="panel mb-4 space-y-3 p-4"
          onSubmit={async (event) => {
            event.preventDefault();
            await register.mutateAsync({
              ...form,
              adapter_path: form.adapter_path || undefined,
              gguf_path: form.gguf_path || undefined,
              notes: form.notes || undefined,
            });
            setShowRegister(false);
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="model-name">
                Display name
              </label>
              <input
                id="model-name"
                required
                className="field"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="My QLoRA Qwen"
              />
            </div>
            <div>
              <label className="label" htmlFor="model-id">
                Model id or path
              </label>
              <input
                id="model-id"
                required
                className="field"
                value={form.model_id}
                onChange={(event) => setForm({ ...form, model_id: event.target.value })}
                placeholder="Qwen/Qwen2.5-Coder-7B-Instruct"
              />
            </div>
            <div>
              <label className="label" htmlFor="model-backend">
                Backend
              </label>
              <select
                id="model-backend"
                className="field"
                value={form.backend}
                onChange={(event) => setForm({ ...form, backend: event.target.value })}
              >
                <option value="transformers">transformers</option>
                <option value="llama_cpp">llama_cpp (GGUF)</option>
                <option value="openai_compat">openai_compat</option>
                <option value="mock">mock</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="model-quant">
                Quantization
              </label>
              <select
                id="model-quant"
                className="field"
                value={form.quantization_mode}
                onChange={(event) => setForm({ ...form, quantization_mode: event.target.value })}
              >
                <option value="4bit">4-bit (NF4)</option>
                <option value="8bit">8-bit</option>
                <option value="none">none</option>
              </select>
            </div>
            <div>
              <label className="label" htmlFor="model-adapter">
                Adapter path (optional)
              </label>
              <input
                id="model-adapter"
                className="field"
                value={form.adapter_path}
                onChange={(event) => setForm({ ...form, adapter_path: event.target.value })}
                placeholder="data/runs/qlora-7b/adapter"
              />
            </div>
            <div>
              <label className="label" htmlFor="model-gguf">
                GGUF path (llama_cpp only)
              </label>
              <input
                id="model-gguf"
                className="field"
                value={form.gguf_path}
                onChange={(event) => setForm({ ...form, gguf_path: event.target.value })}
                placeholder="C:/models/model.gguf"
              />
            </div>
          </div>
          <button type="submit" className="btn-primary" disabled={register.isPending}>
            Save to catalogue
          </button>
          {register.isError && (
            <InlineNotice tone="danger">{describeError(register.error).message}</InlineNotice>
          )}
        </form>
      )}

      {models.isLoading && <LoadingState label="Loading catalogue" />}
      {models.isError && <ErrorState error={models.error} onRetry={() => void models.refetch()} />}

      <div className="grid gap-3 sm:grid-cols-2">
        {models.data?.map((model) => {
          const active = status.data?.loaded && status.data.model_id === model.model_id;
          return (
            <article key={model.id} className="panel flex flex-col p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="flex items-center gap-2 font-medium text-ink-100">
                    <Cpu className="h-4 w-4 text-ink-500" aria-hidden />
                    <span className="truncate">{model.name}</span>
                  </h3>
                  <p className="mt-0.5 truncate font-mono text-xs text-ink-500">{model.model_id}</p>
                </div>
                {!model.is_builtin && (
                  <button
                    type="button"
                    aria-label={`Delete ${model.name}`}
                    onClick={() => remove.mutate(model.id)}
                    className="rounded p-1.5 text-ink-500 hover:bg-ink-800 hover:text-red-300"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                )}
              </div>

              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="badge">{model.backend}</span>
                <span className="badge">{model.quantization_mode}</span>
                <span className="badge">{model.context_length.toLocaleString()} ctx</span>
                {active && (
                  <span className="badge border-emerald-900/60 text-emerald-300">loaded</span>
                )}
              </div>

              {model.notes && <p className="mt-2 flex-1 text-xs text-ink-400">{model.notes}</p>}

              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  className="btn-ghost flex-1"
                  disabled={load.isPending}
                  onClick={() =>
                    load.mutate({
                      model_id: model.model_id,
                      backend: model.backend,
                      quantization_mode: model.quantization_mode,
                    })
                  }
                >
                  <Play className="h-4 w-4" aria-hidden />
                  Load
                </button>
                <button
                  type="button"
                  className="btn-ghost"
                  title="Load and allow Bread to download the weights if they are not cached"
                  disabled={load.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Allow Bread to download "${model.model_id}" if it is not already ` +
                          "cached? A 7B model is roughly 15 GB.",
                      )
                    ) {
                      load.mutate({
                        model_id: model.model_id,
                        backend: model.backend,
                        quantization_mode: model.quantization_mode,
                        confirm_download: true,
                      });
                    }
                  }}
                >
                  <Download className="h-4 w-4" aria-hidden />
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
