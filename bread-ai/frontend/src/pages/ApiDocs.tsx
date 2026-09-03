/** A readable map of the local API, with a link to the generated OpenAPI docs. */

import { ExternalLink } from "lucide-react";

interface Endpoint {
  method: "GET" | "POST" | "PATCH" | "DELETE";
  path: string;
  summary: string;
}

const GROUPS: { title: string; description: string; endpoints: Endpoint[] }[] = [
  {
    title: "Health and system",
    description:
      "Probe the server, read GPU and VRAM state, and see which optional dependencies are installed.",
    endpoints: [
      { method: "GET", path: "/api/health", summary: "Liveness probe. Never needs an API key." },
      { method: "GET", path: "/api/system/gpu", summary: "CUDA availability, devices and VRAM." },
      { method: "GET", path: "/api/system/status", summary: "Everything at once, plus warnings." },
    ],
  },
  {
    title: "Models",
    description:
      "Manage the catalogue and control what is loaded. Weights are never downloaded without confirm_download.",
    endpoints: [
      { method: "GET", path: "/api/models", summary: "List registered models." },
      { method: "GET", path: "/api/models/status", summary: "What is loaded right now." },
      { method: "POST", path: "/api/models/load", summary: "Load a model into memory." },
      { method: "POST", path: "/api/models/unload", summary: "Release the loaded model." },
      { method: "POST", path: "/api/models/register", summary: "Add a model to the catalogue." },
    ],
  },
  {
    title: "Chat",
    description:
      "Buffered and streaming chat. The streaming endpoint emits Server-Sent Events: meta, token, done and error.",
    endpoints: [
      { method: "POST", path: "/api/chat", summary: "Send a message, wait for the whole reply." },
      { method: "POST", path: "/api/chat/stream", summary: "Stream the reply as SSE." },
      { method: "POST", path: "/api/chat/stop", summary: "Cancel a stream or a conversation." },
      { method: "GET", path: "/api/conversations", summary: "List conversations." },
      { method: "POST", path: "/api/conversations", summary: "Create a conversation." },
      { method: "GET", path: "/api/conversations/{id}", summary: "Fetch one with its messages." },
      { method: "PATCH", path: "/api/conversations/{id}", summary: "Rename or reconfigure." },
      { method: "DELETE", path: "/api/conversations/{id}", summary: "Delete it and its messages." },
    ],
  },
  {
    title: "Knowledge spaces",
    description: "One vector index per space so unrelated material stays separate.",
    endpoints: [
      { method: "GET", path: "/api/knowledge-spaces", summary: "List spaces." },
      { method: "POST", path: "/api/knowledge-spaces", summary: "Create a space." },
      { method: "PATCH", path: "/api/knowledge-spaces/{id}", summary: "Update a space." },
      { method: "DELETE", path: "/api/knowledge-spaces/{id}", summary: "Delete it and its documents." },
    ],
  },
  {
    title: "Documents and retrieval",
    description:
      "Upload, index and search. Uploaded code is read as data and never executed; filenames are sanitised.",
    endpoints: [
      { method: "POST", path: "/api/documents/upload", summary: "Upload files (multipart)." },
      { method: "POST", path: "/api/documents/index", summary: "(Re)build the vector index." },
      { method: "GET", path: "/api/documents", summary: "List documents." },
      { method: "DELETE", path: "/api/documents/{id}", summary: "Delete a document and its vectors." },
      { method: "POST", path: "/api/rag/search", summary: "Search a knowledge space." },
    ],
  },
  {
    title: "Datasets",
    description:
      "Collect and inspect training data. External sources require accept_terms; local folders do not.",
    endpoints: [
      { method: "GET", path: "/api/datasets", summary: "List collection runs." },
      { method: "GET", path: "/api/datasets/sources", summary: "Sources and their terms URLs." },
      { method: "POST", path: "/api/datasets/collect", summary: "Start a collection run." },
      { method: "POST", path: "/api/datasets/validate", summary: "Validate a JSONL file." },
      { method: "GET", path: "/api/datasets/report", summary: "Summarise a JSONL file." },
    ],
  },
  {
    title: "Training",
    description:
      "Fine-tuning runs execute in a separate process, so a CUDA crash cannot take the server down.",
    endpoints: [
      { method: "GET", path: "/api/training/runs", summary: "List runs." },
      { method: "GET", path: "/api/training/configs", summary: "List shipped configs." },
      { method: "POST", path: "/api/training/start", summary: "Start a run, or dry-run it." },
      { method: "POST", path: "/api/training/stop", summary: "Stop a running job." },
      { method: "GET", path: "/api/training/{id}", summary: "Fetch one run." },
      { method: "GET", path: "/api/training/{id}/logs", summary: "Tail the run log." },
    ],
  },
  {
    title: "Settings and security",
    description: "Runtime settings and API keys. Network binding is not editable over HTTP.",
    endpoints: [
      { method: "GET", path: "/api/settings", summary: "Current effective settings." },
      { method: "PATCH", path: "/api/settings", summary: "Update runtime settings." },
      { method: "POST", path: "/api/api-keys", summary: "Create a key (plaintext shown once)." },
      { method: "DELETE", path: "/api/api-keys/{id}", summary: "Revoke a key." },
    ],
  },
];

const METHOD_STYLES: Record<Endpoint["method"], string> = {
  GET: "border-sky-900/60 text-sky-300",
  POST: "border-emerald-900/60 text-emerald-300",
  PATCH: "border-amber-900/60 text-amber-300",
  DELETE: "border-red-900/60 text-red-300",
};

const CURL_EXAMPLE = `# Streaming chat from any local tool
curl -N http://127.0.0.1:8000/api/chat/stream \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: $BREAD_API_KEY" \\
  -d '{
        "message": "Write a Go function that reads a CSV into a struct slice.",
        "temperature": 0.2,
        "rag_enabled": false
      }'`;

export default function ApiDocs() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="text-lg font-semibold text-ink-100">API</h1>
        <p className="mt-1 text-sm text-ink-400">
          Bread's REST API is how other tools on this machine talk to it: an editor plugin, a
          script, a Discord bot. Everything the web interface does goes through these endpoints.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <a href="/docs" target="_blank" rel="noreferrer" className="btn-ghost">
            Interactive docs (Swagger)
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
          </a>
          <a href="/redoc" target="_blank" rel="noreferrer" className="btn-ghost">
            ReDoc
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
          </a>
          <a href="/openapi.json" target="_blank" rel="noreferrer" className="btn-ghost">
            openapi.json
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
          </a>
        </div>
        <p className="mt-2 text-xs text-ink-500">
          The Swagger and ReDoc pages are generated by FastAPI and load their own JavaScript
          from a CDN, so those two pages need an internet connection to render. The API itself,
          and every page in Bread, works offline.
        </p>
      </header>

      <section className="panel mb-6 p-4">
        <h2 className="mb-2 text-sm font-medium text-ink-200">Authentication</h2>
        <p className="text-sm text-ink-400">
          On localhost an API key is optional. Bind to any other address and key checks turn on
          automatically. Send the key as <code className="text-crust-200">X-API-Key</code> or as{" "}
          <code className="text-crust-200">Authorization: Bearer …</code>. Create one on the
          Settings page or with <code className="text-crust-200">python -m app.cli create-key</code>.
        </p>
        <pre className="mt-3 overflow-x-auto rounded-lg border border-ink-800 bg-ink-950 p-3 font-mono text-xs text-ink-200">
          {CURL_EXAMPLE}
        </pre>
      </section>

      <section className="panel mb-6 p-4">
        <h2 className="mb-2 text-sm font-medium text-ink-200">Errors</h2>
        <p className="text-sm text-ink-400">
          Every failure returns the same shape, so a client can branch on{" "}
          <code className="text-crust-200">code</code> instead of parsing prose.
        </p>
        <pre className="mt-3 overflow-x-auto rounded-lg border border-ink-800 bg-ink-950 p-3 font-mono text-xs text-ink-200">
{`{
  "error": {
    "code": "backend_unavailable",
    "message": "'Qwen/Qwen2.5-Coder-7B-Instruct' is not in the local Hugging Face cache.",
    "hint": "Run scripts/download_model.py --accept-download, or send confirm_download=true.",
    "details": { "model_id": "Qwen/Qwen2.5-Coder-7B-Instruct" }
  }
}`}
        </pre>
      </section>

      <div className="space-y-5">
        {GROUPS.map((group) => (
          <section key={group.title} className="panel p-4">
            <h2 className="text-sm font-medium text-ink-200">{group.title}</h2>
            <p className="mb-3 mt-1 text-xs text-ink-400">{group.description}</p>
            <ul className="divide-y divide-ink-800">
              {group.endpoints.map((endpoint) => (
                <li
                  key={`${endpoint.method} ${endpoint.path}`}
                  className="flex flex-wrap items-baseline gap-2 py-2"
                >
                  <span className={`badge shrink-0 font-mono ${METHOD_STYLES[endpoint.method]}`}>
                    {endpoint.method}
                  </span>
                  <code className="font-mono text-xs text-ink-100">{endpoint.path}</code>
                  <span className="w-full text-xs text-ink-400 sm:w-auto sm:flex-1">
                    {endpoint.summary}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
