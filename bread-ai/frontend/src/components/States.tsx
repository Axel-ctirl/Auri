/** Loading, empty and error states. Every async view uses all three. */

import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { describeError } from "../api/client";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div
      className="flex items-center justify-center gap-3 py-12 text-ink-400"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      <span className="text-sm">{label}…</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <div className="text-ink-600">{icon ?? <Inbox className="h-7 w-7" aria-hidden />}</div>
      <h3 className="text-sm font-medium text-ink-200">{title}</h3>
      {description && <p className="max-w-md text-sm text-ink-400">{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { message, hint } = describeError(error);
  return (
    <div className="m-4 rounded-xl border border-red-900/60 bg-red-950/30 p-4" role="alert">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-400" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-red-200">{message}</p>
          {hint && <p className="mt-1 text-sm text-red-300/80">{hint}</p>}
          {onRetry && (
            <button type="button" className="btn-ghost mt-3" onClick={onRetry}>
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function InlineNotice({
  tone = "info",
  children,
}: {
  tone?: "info" | "warning" | "danger" | "success";
  children: ReactNode;
}) {
  const tones = {
    info: "border-sky-900/60 bg-sky-950/30 text-sky-200",
    warning: "border-amber-900/60 bg-amber-950/30 text-amber-200",
    danger: "border-red-900/60 bg-red-950/30 text-red-200",
    success: "border-emerald-900/60 bg-emerald-950/30 text-emerald-200",
  } as const;
  return (
    <div className={`rounded-lg border px-3 py-2 text-sm ${tones[tone]}`}>{children}</div>
  );
}
