/** Uploading, indexing, searching and deleting documents. */

import { FileText, RefreshCw, Search, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { describeError } from "../api/client";
import {
  useDeleteDocument,
  useDocuments,
  useIndexDocuments,
  useKnowledgeSpaces,
  useRagSearch,
  useUploadDocuments,
} from "../api/hooks";
import { EmptyState, ErrorState, InlineNotice, LoadingState } from "../components/States";
import { formatBytes, formatRelativeTime, truncate } from "../lib/format";

const SUPPORTED = [
  ".txt", ".md", ".json", ".csv", ".py", ".java", ".js", ".jsx", ".ts", ".tsx",
  ".lua", ".luau", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".php",
  ".rb", ".sql", ".sh", ".html", ".css", ".yaml", ".yml", ".pdf",
];

const STATUS_STYLES: Record<string, string> = {
  indexed: "border-emerald-900/60 text-emerald-300",
  uploaded: "border-sky-900/60 text-sky-300",
  failed: "border-red-900/60 text-red-300",
  skipped: "border-amber-900/60 text-amber-300",
};

export default function Documents() {
  const [spaceId, setSpaceId] = useState("");
  const [query, setQuery] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const spaces = useKnowledgeSpaces();
  const documents = useDocuments(spaceId || undefined);
  const upload = useUploadDocuments();
  const reindex = useIndexDocuments();
  const remove = useDeleteDocument();
  const search = useRagSearch();

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    await upload.mutateAsync({ files: Array.from(files), spaceId: spaceId || undefined });
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="text-lg font-semibold text-ink-100">Documents</h1>
        <p className="mt-1 text-sm text-ink-400">
          Uploaded files are read, chunked and embedded on this machine. Bread treats source code
          as data: it is never imported or executed.
        </p>
      </header>

      <div className="panel mb-5 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[200px]">
            <label className="label" htmlFor="document-space">
              Knowledge space
            </label>
            <select
              id="document-space"
              value={spaceId}
              onChange={(event) => setSpaceId(event.target.value)}
              className="field"
            >
              <option value="">All spaces</option>
              {spaces.data?.map((space) => (
                <option key={space.id} value={space.id}>
                  {space.name}
                </option>
              ))}
            </select>
          </div>

          <input
            ref={fileRef}
            type="file"
            multiple
            accept={SUPPORTED.join(",")}
            className="hidden"
            onChange={(event) => void handleFiles(event.target.files)}
          />
          <button
            type="button"
            className="btn-primary"
            onClick={() => fileRef.current?.click()}
            disabled={upload.isPending}
          >
            <Upload className="h-4 w-4" aria-hidden />
            {upload.isPending ? "Uploading…" : "Upload files"}
          </button>

          <button
            type="button"
            className="btn-ghost"
            disabled={reindex.isPending}
            onClick={() =>
              reindex.mutate({ knowledge_space_id: spaceId || undefined, force: true })
            }
          >
            <RefreshCw className={`h-4 w-4 ${reindex.isPending ? "animate-spin" : ""}`} aria-hidden />
            Re-index
          </button>
        </div>

        <p className="mt-2 text-xs text-ink-500">
          Supported: {SUPPORTED.join(" ")}
        </p>

        {upload.isError && (
          <div className="mt-3">
            <InlineNotice tone="danger">{describeError(upload.error).message}</InlineNotice>
          </div>
        )}
        {upload.data && upload.data.skipped.length > 0 && (
          <div className="mt-3 space-y-1">
            {upload.data.skipped.map((item) => (
              <InlineNotice key={item.filename} tone="warning">
                <span className="font-medium">{item.filename}</span>: {item.reason}
              </InlineNotice>
            ))}
          </div>
        )}
        {reindex.data && (
          <div className="mt-3">
            <InlineNotice tone="success">
              Indexed {reindex.data.indexed_documents} document(s) into{" "}
              {reindex.data.created_chunks} chunks in {reindex.data.duration_ms} ms using{" "}
              {reindex.data.embedding_model_id}.
            </InlineNotice>
          </div>
        )}
      </div>

      {/* --------------------------------------------------- search box */}
      <form
        className="panel mb-5 p-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (query.trim()) {
            search.mutate({
              query: query.trim(),
              knowledge_space_id: spaceId || undefined,
              top_k: 5,
            });
          }
        }}
      >
        <label className="label" htmlFor="rag-query">
          Test retrieval
        </label>
        <div className="flex gap-2">
          <input
            id="rag-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="What would the model retrieve for this question?"
            className="field"
          />
          <button type="submit" className="btn-ghost" disabled={search.isPending}>
            <Search className="h-4 w-4" aria-hidden />
            Search
          </button>
        </div>

        {search.data && (
          <div className="mt-3 space-y-2">
            <p className="text-xs text-ink-500">
              {search.data.results.length} result(s) using {search.data.embedding_model_id}
              {search.data.reranked ? " with reranking" : ""}
            </p>
            {search.data.results.map((result, index) => (
              <div key={result.chunk_id} className="rounded-lg border border-ink-800 p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs text-ink-300">
                  <span className="font-mono text-crust-300">[{index + 1}]</span>
                  <span className="font-medium text-ink-200">{result.document_name}</span>
                  <span className="text-ink-500">
                    chunk {result.chunk_index}
                    {result.start_line ? `, lines ${result.start_line}–${result.end_line}` : ""}
                  </span>
                  <span className="badge">score {result.score.toFixed(3)}</span>
                </div>
                <pre className="mt-2 overflow-x-auto whitespace-pre-wrap font-mono text-[11px] text-ink-400">
                  {truncate(result.excerpt, 400)}
                </pre>
              </div>
            ))}
            {search.data.results.length === 0 && (
              <InlineNotice tone="warning">
                Nothing matched. Either this space has no documents indexed, or the query shares no
                vocabulary with them.
              </InlineNotice>
            )}
          </div>
        )}
        {search.isError && (
          <div className="mt-3">
            <InlineNotice tone="danger">{describeError(search.error).message}</InlineNotice>
          </div>
        )}
      </form>

      {/* ------------------------------------------------------ listing */}
      {documents.isLoading && <LoadingState label="Loading documents" />}
      {documents.isError && (
        <ErrorState error={documents.error} onRetry={() => void documents.refetch()} />
      )}

      {documents.data?.length === 0 && (
        <EmptyState
          icon={<FileText className="h-7 w-7" />}
          title="No documents indexed yet"
          description="Upload source files, notes or PDFs above. Bread indexes them straight away."
        />
      )}

      {documents.data && documents.data.length > 0 && (
        <div className="panel overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-ink-800 text-left text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-4 py-2 font-medium">File</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="hidden px-4 py-2 font-medium sm:table-cell">Chunks</th>
                <th className="hidden px-4 py-2 font-medium sm:table-cell">Size</th>
                <th className="hidden px-4 py-2 font-medium md:table-cell">Indexed</th>
                <th className="px-4 py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {documents.data.map((document) => (
                <tr key={document.id} className="hover:bg-ink-800/40">
                  <td className="px-4 py-2">
                    <p className="font-medium text-ink-100">{document.filename}</p>
                    <p className="text-xs text-ink-500">{document.language ?? document.extension}</p>
                    {document.error && (
                      <p className="mt-1 text-xs text-red-300">{document.error}</p>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`badge ${STATUS_STYLES[document.status] ?? "text-ink-300"}`}
                    >
                      {document.status}
                    </span>
                  </td>
                  <td className="hidden px-4 py-2 font-mono text-ink-300 sm:table-cell">
                    {document.chunk_count}
                  </td>
                  <td className="hidden px-4 py-2 text-ink-400 sm:table-cell">
                    {formatBytes(document.size_bytes)}
                  </td>
                  <td className="hidden px-4 py-2 text-ink-400 md:table-cell">
                    {formatRelativeTime(document.indexed_at)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      type="button"
                      aria-label={`Delete ${document.filename}`}
                      onClick={() => remove.mutate(document.id)}
                      className="rounded p-1.5 text-ink-500 hover:bg-ink-800 hover:text-red-300"
                    >
                      <Trash2 className="h-4 w-4" aria-hidden />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
