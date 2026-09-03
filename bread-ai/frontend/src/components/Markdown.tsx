/**
 * Markdown renderer for assistant output.
 *
 * GitHub-flavoured Markdown plus syntax highlighting, with every fenced block
 * routed through CodeBlock so it gets a copy button. Raw HTML is not enabled:
 * model output is untrusted text and should never become live markup.
 */

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

import CodeBlock from "./CodeBlock";

function extractLanguage(node: unknown): string | undefined {
  const element = node as { children?: { properties?: { className?: string[] } }[] } | undefined;
  const classNames = element?.children?.[0]?.properties?.className ?? [];
  const match = classNames.find((name) => name.startsWith("language-"));
  return match?.replace("language-", "");
}

function MarkdownBody({ content }: { content: string }) {
  return (
    <div
      className="prose-bread max-w-none text-[15px] leading-relaxed text-ink-100
        [&_a]:text-crust-300 [&_a]:underline [&_a]:underline-offset-2
        [&_blockquote]:border-l-2 [&_blockquote]:border-ink-700 [&_blockquote]:pl-3
        [&_blockquote]:text-ink-300
        [&_h1]:mb-2 [&_h1]:mt-5 [&_h1]:text-lg [&_h1]:font-semibold
        [&_h2]:mb-2 [&_h2]:mt-5 [&_h2]:text-base [&_h2]:font-semibold
        [&_h3]:mb-1 [&_h3]:mt-4 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:uppercase
        [&_h3]:tracking-wide [&_h3]:text-ink-300
        [&_hr]:my-4 [&_hr]:border-ink-800
        [&_li]:my-1 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5
        [&_p]:my-2
        [&_table]:my-3 [&_table]:w-full [&_table]:text-sm
        [&_td]:border [&_td]:border-ink-800 [&_td]:px-2 [&_td]:py-1
        [&_th]:border [&_th]:border-ink-800 [&_th]:bg-ink-900 [&_th]:px-2 [&_th]:py-1
        [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5"
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{
          pre: ({ node, children }) => (
            <CodeBlock language={extractLanguage(node)}>{children}</CodeBlock>
          ),
          code: ({ className, children, ...props }) => {
            const isInline = !className?.includes("language-");
            if (isInline) {
              return (
                <code
                  className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[13px] text-crust-200"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default memo(MarkdownBody);
