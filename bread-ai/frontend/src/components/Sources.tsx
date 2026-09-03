/** Citations panel shown under an assistant message that used retrieval. */

import { ChevronDown, FileText } from "lucide-react";
import { useState } from "react";

import type { Citation } from "../api/types";
import { truncate } from "../lib/format";

export default function Sources({ sources }: { sources: Citation[] }) {
  const [expanded, setExpanded] = useState(false);

  if (sources.length === 0) return null;

  return (
    <div className="mt-3 rounded-lg border border-ink-800 bg-ink-950/60">
      <button
        type="button"
        onClick={() => setExpanded((open) => !open)}
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs
          text-ink-300 hover:text-ink-100"
        aria-expanded={expanded}
      >
        <span className="inline-flex items-center gap-2">
          <FileText className="h-3.5 w-3.5" aria-hidden />
          {sources.length} source{sources.length === 1 ? "" : "s"} from your documents
        </span>
        <ChevronDown
          className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>

      {expanded && (
        <ol className="space-y-2 border-t border-ink-800 px-3 py-2">
          {sources.map((source, index) => (
            <li key={source.chunk_id} className="text-xs">
              <div className="flex flex-wrap items-center gap-2 text-ink-300">
                <span className="font-mono text-crust-300">[{index + 1}]</span>
                <span className="font-medium text-ink-200">{source.document_name}</span>
                <span className="text-ink-500">
                  chunk {source.chunk_index}
                  {source.start_line
                    ? `, lines ${source.start_line}–${source.end_line}`
                    : ""}
                </span>
                <span className="badge">score {source.score.toFixed(3)}</span>
              </div>
              <p className="mt-1 whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-ink-400">
                {truncate(source.excerpt, 320)}
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
