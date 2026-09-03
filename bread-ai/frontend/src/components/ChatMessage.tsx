/** One turn in the conversation. */

import { AlertCircle, Copy, RefreshCw, User } from "lucide-react";
import { useState } from "react";

import type { ChatMessage as ChatMessageType } from "../api/types";
import { formatDuration } from "../lib/format";
import Markdown from "./Markdown";
import Sources from "./Sources";

function BreadMark() {
  return (
    <div
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg
        bg-gradient-to-br from-crust-300 to-crust-600 text-sm"
      aria-hidden
    >
      🍞
    </div>
  );
}

interface ChatMessageProps {
  message: ChatMessageType;
  streaming?: boolean;
  onRegenerate?: () => void;
}

export default function ChatMessage({ message, streaming, onRegenerate }: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const copyMessage = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable; the text is still selectable */
    }
  };

  return (
    <article className="animate-fade-in px-4 py-4 sm:px-6" data-role={message.role}>
      <div className="mx-auto flex max-w-3xl gap-3">
        {isUser ? (
          <div
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg
              border border-ink-700 bg-ink-800 text-ink-300"
            aria-hidden
          >
            <User className="h-4 w-4" />
          </div>
        ) : (
          <BreadMark />
        )}

        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2 text-xs text-ink-500">
            <span className="font-medium text-ink-300">{isUser ? "You" : "Bread"}</span>
            {message.model_id && !isUser && <span>· {message.model_id}</span>}
            {message.latency_ms ? <span>· {formatDuration(message.latency_ms)}</span> : null}
            {message.stopped_early && <span className="text-amber-400">· stopped early</span>}
          </div>

          {isUser ? (
            <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-ink-100">
              {message.content}
            </p>
          ) : (
            <>
              <Markdown content={message.content} />
              {streaming && (
                <span
                  className="ml-0.5 inline-block h-4 w-2 animate-blink bg-crust-400 align-middle"
                  aria-label="Bread is still writing"
                />
              )}
            </>
          )}

          {message.error && (
            <div
              className="mt-2 flex items-start gap-2 rounded-lg border border-red-900/60
                bg-red-950/30 px-3 py-2 text-sm text-red-200"
              role="alert"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{message.error}</span>
            </div>
          )}

          <Sources sources={message.sources} />

          {!isUser && !streaming && (
            <div className="mt-2 flex items-center gap-1 opacity-0 transition-opacity focus-within:opacity-100 hover:opacity-100 [article:hover_&]:opacity-100">
              <button
                type="button"
                onClick={copyMessage}
                className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs
                  text-ink-400 hover:bg-ink-800 hover:text-ink-100"
              >
                <Copy className="h-3.5 w-3.5" aria-hidden />
                {copied ? "Copied" : "Copy"}
              </button>
              {onRegenerate && (
                <button
                  type="button"
                  onClick={onRegenerate}
                  className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs
                    text-ink-400 hover:bg-ink-800 hover:text-ink-100"
                >
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden />
                  Regenerate
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </article>
  );
}
