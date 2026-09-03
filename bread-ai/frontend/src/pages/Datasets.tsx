/** Dataset collection, validation and reporting. */

import { Database, FileCheck2, FileSearch, Play } from "lucide-react";
import { useState } from "react";

import { describeError } from "../api/client";
import {
  useCollectDataset,
  useDatasetReport,
  useDatasetRuns,
  useDatasetSources,
  useValidateDataset,
} from "../api/hooks";
import { EmptyState, ErrorState, InlineNotice, LoadingState } from "../components/States";
import { formatCount, formatRelativeTime } from "../lib/format";

const DEFAULT_LANGUAGES = ["python", "java", "typescript", "javascript", "lua", "luau", "go", "rust"];

export default function Datasets() {
  const runs = useDatasetRuns();
  const sources = useDatasetSources();
  const collect = useCollectDataset();
  const validate = useValidateDataset();
  const report = useDatasetReport();

  const [name, setName] = useState("my_projects");
  const [source, setSource] = useState("local_code");
  const [paths, setPaths] = useState("");
  const [languages, setLanguages] = useState<string[]>(DEFAULT_LANGUAGES);
  const [maxRecords, setMaxRecords] = useState(2000);
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [inspectPath, setInspectPath] = useState("");

  const isExternal = source !== "local_code" && source !== "local_english";
  const selectedExternal = sources.data?.external.find((item) => item.id === source);

  const startCollection = async (event: React.FormEvent) => {
    event.preventDefault();
    await collect.mutateAsync({
      name,
      source,
      input_paths: paths
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
      languages: source === "local_code" ? languages : [],
      max_records: maxRecords,
      accept_terms: acceptTerms,
    });
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
      <header className="mb-5">
        <h1 className="text-lg font-semibold text-ink-100">Datasets</h1>
        <p className="mt-1 text-sm text-ink-400">
          Build training data from code you own. Bread checks each project's license, skips files
          that look like they hold credentials, and writes a manifest recording where every record
          came from.
        </p>
      </header>

      {sources.data && (
        <div className="mb-5">
          <InlineNotice tone="info">{sources.data.notice}</InlineNotice>
        </div>
      )}

      {/* --------------------------------------------------- collect form */}
      <form onSubmit={startCollection} className="panel mb-6 space-y-3 p-4">
        <h2 className="text-sm font-medium text-ink-200">Collect</h2>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="dataset-name">
              Dataset name
            </label>
            <input
              id="dataset-name"
              className="field"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="dataset-source">
              Source
            </label>
            <select
              id="dataset-source"
              className="field"
              value={source}
              onChange={(event) => {
                setSource(event.target.value);
                setAcceptTerms(false);
              }}
            >
              {sources.data?.local.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title} (recommended)
                </option>
              ))}
              {sources.data?.external.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title} (external download)
                </option>
              ))}
            </select>
          </div>
        </div>

        {!isExternal && (
          <div>
            <label className="label" htmlFor="dataset-paths">
              Folders to read, one per line
            </label>
            <textarea
              id="dataset-paths"
              className="field h-24 font-mono text-xs"
              value={paths}
              onChange={(event) => setPaths(event.target.value)}
              placeholder={"C:/dev/minecraft-plugins\n~/projects/discord-bot"}
              required
            />
            <p className="mt-1 text-xs text-ink-500">
              Each subfolder with its own LICENSE file is treated as a separate project.
            </p>
          </div>
        )}

        {source === "local_code" && (
          <div>
            <span className="label">Languages</span>
            <div className="flex flex-wrap gap-1.5">
              {(sources.data?.languages ?? DEFAULT_LANGUAGES).map((language) => {
                const selected = languages.includes(language);
                return (
                  <button
                    key={language}
                    type="button"
                    onClick={() =>
                      setLanguages((current) =>
                        selected
                          ? current.filter((item) => item !== language)
                          : [...current, language],
                      )
                    }
                    className={`badge ${
                      selected ? "border-crust-600 text-crust-200" : "text-ink-400"
                    }`}
                  >
                    {language}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="dataset-max">
              Maximum records
            </label>
            <input
              id="dataset-max"
              type="number"
              min={1}
              max={1000000}
              className="field"
              value={maxRecords}
              onChange={(event) => setMaxRecords(Number(event.target.value))}
            />
          </div>
        </div>

        {isExternal && selectedExternal && (
          <div className="space-y-2 rounded-lg border border-amber-900/60 bg-amber-950/20 p-3">
            <p className="text-sm text-amber-200">
              This downloads from an external host: {selectedExternal.dataset_name}.
            </p>
            <p className="text-xs text-amber-200/80">
              Read the terms before accepting. A permissive dataset label does not make every
              record inside it safe for your use, and redistribution, commercial use and
              publishing fine-tuned weights are three separate questions.
            </p>
            <a
              href={selectedExternal.terms_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-block text-xs text-crust-300 underline"
            >
              {selectedExternal.terms_url}
            </a>
            <label className="flex items-center gap-2 text-sm text-amber-100">
              <input
                type="checkbox"
                checked={acceptTerms}
                onChange={(event) => setAcceptTerms(event.target.checked)}
                className="accent-crust-500"
              />
              I have read these terms and accept them.
            </label>
          </div>
        )}

        <button
          type="submit"
          className="btn-primary"
          disabled={collect.isPending || (isExternal && !acceptTerms)}
        >
          <Play className="h-4 w-4" aria-hidden />
          Start collection
        </button>

        {collect.isError && (
          <InlineNotice tone="danger">
            {describeError(collect.error).message} {describeError(collect.error).hint}
          </InlineNotice>
        )}
      </form>

      {/* ------------------------------------------------------ inspect */}
      <div className="panel mb-6 space-y-3 p-4">
        <h2 className="text-sm font-medium text-ink-200">Inspect a dataset file</h2>
        <div className="flex flex-wrap gap-2">
          <input
            className="field flex-1 font-mono text-xs"
            value={inspectPath}
            onChange={(event) => setInspectPath(event.target.value)}
            placeholder="data/datasets/my_projects.jsonl"
            aria-label="Dataset path"
          />
          <button
            type="button"
            className="btn-ghost"
            disabled={!inspectPath || validate.isPending}
            onClick={() => validate.mutate({ path: inspectPath, schema_name: "sft_chat" })}
          >
            <FileCheck2 className="h-4 w-4" aria-hidden />
            Validate
          </button>
          <button
            type="button"
            className="btn-ghost"
            disabled={!inspectPath || report.isPending}
            onClick={() => report.mutate(inspectPath)}
          >
            <FileSearch className="h-4 w-4" aria-hidden />
            Report
          </button>
        </div>

        {validate.isError && (
          <InlineNotice tone="danger">{describeError(validate.error).message}</InlineNotice>
        )}
        {validate.data && (
          <div className="rounded-lg border border-ink-800 p-3 text-sm">
            <p className="text-ink-200">
              {formatCount(validate.data.valid_records)} valid of{" "}
              {formatCount(validate.data.total_records)} records ·{" "}
              {validate.data.duplicate_records} duplicates · {validate.data.secret_hits} possible
              credentials
            </p>
            {validate.data.issues.length > 0 && (
              <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto text-xs text-ink-400">
                {validate.data.issues.slice(0, 30).map((issue, index) => (
                  <li key={`${issue.line}-${index}`}>
                    line {issue.line}: {issue.problem}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {report.isError && (
          <InlineNotice tone="danger">{describeError(report.error).message}</InlineNotice>
        )}
        {report.data && (
          <div className="space-y-3 rounded-lg border border-ink-800 p-3 text-sm">
            <div className="grid gap-2 sm:grid-cols-3">
              <div>
                <p className="text-xs text-ink-500">Records</p>
                <p className="font-mono text-ink-100">{formatCount(report.data.total_records)}</p>
              </div>
              <div>
                <p className="text-xs text-ink-500">Approx tokens</p>
                <p className="font-mono text-ink-100">{formatCount(report.data.approx_tokens)}</p>
              </div>
              <div>
                <p className="text-xs text-ink-500">Median length</p>
                <p className="font-mono text-ink-100">
                  {Math.round(report.data.length_percentiles.p50 ?? 0)} chars
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-xs text-ink-500">Licenses</p>
                <ul className="space-y-0.5 text-xs text-ink-300">
                  {Object.entries(report.data.license_counts).map(([license, count]) => (
                    <li key={license}>
                      {license}: {count}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="mb-1 text-xs text-ink-500">Languages</p>
                <ul className="space-y-0.5 text-xs text-ink-300">
                  {Object.entries(report.data.language_counts).map(([language, count]) => (
                    <li key={language}>
                      {language}: {count}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {report.data.warnings.map((warning) => (
              <InlineNotice key={warning} tone="warning">
                {warning}
              </InlineNotice>
            ))}
          </div>
        )}
      </div>

      {/* ----------------------------------------------------------- runs */}
      <h2 className="mb-3 text-sm font-medium text-ink-200">Collection runs</h2>
      {runs.isLoading && <LoadingState label="Loading runs" />}
      {runs.isError && <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />}
      {runs.data?.length === 0 && (
        <EmptyState
          icon={<Database className="h-7 w-7" />}
          title="No collection runs yet"
          description="Point Bread at a folder of your own projects above, or run scripts/collect_local_code.py."
        />
      )}

      <div className="space-y-2">
        {runs.data?.map((run) => (
          <article key={run.id} className="panel p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <h3 className="font-medium text-ink-100">{run.name}</h3>
                <p className="truncate font-mono text-xs text-ink-500">{run.output_path}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="badge">{run.source}</span>
                <span
                  className={`badge ${
                    run.status === "completed"
                      ? "border-emerald-900/60 text-emerald-300"
                      : run.status === "failed"
                        ? "border-red-900/60 text-red-300"
                        : "border-sky-900/60 text-sky-300"
                  }`}
                >
                  {run.status}
                </span>
              </div>
            </div>
            <p className="mt-2 text-xs text-ink-400">
              {formatCount(run.record_count)} records · started {formatRelativeTime(run.created_at)}
              {run.accepted_terms && run.terms_url ? " · terms accepted" : ""}
            </p>
            {run.error && (
              <p className="mt-2 rounded border border-red-900/60 bg-red-950/30 p-2 text-xs text-red-200">
                {run.error}
              </p>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
