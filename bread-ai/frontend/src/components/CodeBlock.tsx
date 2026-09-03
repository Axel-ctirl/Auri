/**
 * A fenced code block with a copy button.
 *
 * Highlighting is applied upstream by rehype-highlight, so this component only
 * owns the chrome: the language label, the copy affordance and the scroll box.
 */

import { Check, Copy } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

interface CodeBlockProps {
  children: ReactNode;
  language?: string;
}

export default function CodeBlock({ children, language }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);
  const resetTimer = useRef<number>();

  useEffect(() => () => window.clearTimeout(resetTimer.current), []);

  const copy = useCallback(async () => {
    // textContent, not innerText: it preserves the exact whitespace of the
    // block, and innerText is unimplemented in jsdom so tests could not see it.
    const text = preRef.current?.textContent ?? "";
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard access is blocked outside a secure context in some browsers.
      // Fall back to selecting the block so a manual copy still works.
      const range = document.createRange();
      if (preRef.current) {
        range.selectNodeContents(preRef.current);
        window.getSelection()?.removeAllRanges();
        window.getSelection()?.addRange(range);
      }
      return;
    }
    setCopied(true);
    resetTimer.current = window.setTimeout(() => setCopied(false), 1600);
  }, []);

  return (
    <div className="group relative my-3 overflow-hidden rounded-lg border border-ink-800 bg-ink-950">
      <div className="flex items-center justify-between border-b border-ink-800 bg-ink-900/60 px-3 py-1.5">
        <span className="font-mono text-xs text-ink-400">{language || "code"}</span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs text-ink-300
            transition-colors hover:bg-ink-800 hover:text-ink-100"
          aria-label={copied ? "Copied" : "Copy code"}
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5" aria-hidden />
              Copied
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" aria-hidden />
              Copy
            </>
          )}
        </button>
      </div>
      <pre ref={preRef} className="overflow-x-auto p-3 text-[13px] leading-relaxed">
        {children}
      </pre>
    </div>
  );
}
