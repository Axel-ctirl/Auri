/** Knowledge spaces: separate indexes so unrelated material stays unmixed. */

import { Boxes, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { describeError } from "../api/client";
import { useCreateSpace, useDeleteSpace, useKnowledgeSpaces } from "../api/hooks";
import { EmptyState, ErrorState, InlineNotice, LoadingState } from "../components/States";
import { formatCount, formatRelativeTime } from "../lib/format";

const EXAMPLE_SPACES = [
  "Minecraft Paper Docs",
  "Minecraft Fabric Docs",
  "Roblox Luau Docs",
  "Discord Bot Project",
  "School Notes",
  "Bread Source Code",
  "Personal Plugin Projects",
];

export default function KnowledgeSpaces() {
  const spaces = useKnowledgeSpaces();
  const create = useCreateSpace();
  const remove = useDeleteSpace();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [chunkSize, setChunkSize] = useState(900);
  const [chunkOverlap, setChunkOverlap] = useState(150);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    await create.mutateAsync({
      name: name.trim(),
      description: description.trim() || undefined,
      chunk_size: chunkSize,
      chunk_overlap: chunkOverlap,
    });
    setName("");
    setDescription("");
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="text-lg font-semibold text-ink-100">Knowledge spaces</h1>
        <p className="mt-1 text-sm text-ink-400">
          Each space is its own vector index. Keeping your Paper docs apart from your school notes
          means a question about one does not retrieve the other.
        </p>
      </header>

      <form onSubmit={submit} className="panel mb-6 space-y-3 p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="space-name">
              Name
            </label>
            <input
              id="space-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Minecraft Paper Docs"
              className="field"
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="space-description">
              Description
            </label>
            <input
              id="space-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Event API reference and my plugin sources"
              className="field"
            />
          </div>
          <div>
            <label className="label" htmlFor="chunk-size">
              Chunk size (characters)
            </label>
            <input
              id="chunk-size"
              type="number"
              min={100}
              max={8000}
              step={50}
              value={chunkSize}
              onChange={(event) => setChunkSize(Number(event.target.value))}
              className="field"
            />
          </div>
          <div>
            <label className="label" htmlFor="chunk-overlap">
              Chunk overlap (characters)
            </label>
            <input
              id="chunk-overlap"
              type="number"
              min={0}
              max={2000}
              step={25}
              value={chunkOverlap}
              onChange={(event) => setChunkOverlap(Number(event.target.value))}
              className="field"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" className="btn-primary" disabled={create.isPending}>
            <Plus className="h-4 w-4" aria-hidden />
            Create space
          </button>
          <span className="text-xs text-ink-500">Examples:</span>
          {EXAMPLE_SPACES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setName(example)}
              className="badge hover:border-crust-600 hover:text-crust-200"
            >
              {example}
            </button>
          ))}
        </div>

        {create.isError && <InlineNotice tone="danger">{describeError(create.error).message}</InlineNotice>}
      </form>

      {spaces.isLoading && <LoadingState label="Loading spaces" />}
      {spaces.isError && <ErrorState error={spaces.error} onRetry={() => void spaces.refetch()} />}

      {spaces.data?.length === 0 && (
        <EmptyState
          icon={<Boxes className="h-7 w-7" />}
          title="No knowledge spaces yet"
          description="Create one above, then upload documents into it from the Documents page."
        />
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {spaces.data?.map((space) => (
          <article key={space.id} className="panel p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h2 className="truncate font-medium text-ink-100">{space.name}</h2>
                {space.description && (
                  <p className="mt-0.5 text-sm text-ink-400">{space.description}</p>
                )}
              </div>
              <button
                type="button"
                aria-label={`Delete ${space.name}`}
                onClick={() => {
                  if (
                    window.confirm(
                      `Delete "${space.name}"? Its ${space.document_count} document(s), their ` +
                        "chunks, their vectors and the uploaded files are all removed.",
                    )
                  ) {
                    remove.mutate(space.id);
                  }
                }}
                className="rounded p-1.5 text-ink-500 hover:bg-ink-800 hover:text-red-300"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </div>

            <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div>
                <dt className="text-ink-500">Documents</dt>
                <dd className="font-mono text-ink-200">{formatCount(space.document_count)}</dd>
              </div>
              <div>
                <dt className="text-ink-500">Chunks</dt>
                <dd className="font-mono text-ink-200">{formatCount(space.chunk_count)}</dd>
              </div>
              <div>
                <dt className="text-ink-500">Chunk size</dt>
                <dd className="font-mono text-ink-200">
                  {space.chunk_size} / {space.chunk_overlap}
                </dd>
              </div>
              <div>
                <dt className="text-ink-500">Updated</dt>
                <dd className="text-ink-200">{formatRelativeTime(space.updated_at)}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}
