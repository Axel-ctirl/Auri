/**
 * Server-Sent Events over a POST request.
 *
 * The browser's EventSource only does GET, and a chat turn needs a body, so
 * this reads the response stream directly and parses the SSE framing.
 */

import { ApiError, authHeaders } from "./client";
import type { ChatRequestBody, Citation } from "./types";

export interface StreamMeta {
  conversation_id: string;
  stream_id: string;
  model_id: string;
  backend: string;
  sources: Citation[];
}

export interface StreamDone {
  conversation_id: string;
  message_id: string;
  latency_ms: number;
  stopped_early: boolean;
  characters: number;
  error: string | null;
}

export interface StreamHandlers {
  onMeta?: (meta: StreamMeta) => void;
  onToken?: (delta: string) => void;
  onDone?: (done: StreamDone) => void;
  onError?: (error: { code: string; message: string; hint?: string }) => void;
}

export async function streamChat(
  body: ChatRequestBody,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    let parsed: { error?: { code: string; message: string; hint?: string } } = {};
    try {
      parsed = await response.json();
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, {
      code: parsed.error?.code ?? `http_${response.status}`,
      message: parsed.error?.message ?? "The server refused the chat request.",
      hint: parsed.error?.hint,
    });
  }

  if (!response.body) {
    throw new ApiError(0, {
      code: "stream_unsupported",
      message: "This browser did not give Bread a readable response stream.",
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line. Keep the trailing partial frame
    // in the buffer until its terminator arrives.
    let separator = buffer.indexOf("\n\n");
    while (separator !== -1) {
      const frame = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      dispatch(frame, handlers);
      separator = buffer.indexOf("\n\n");
    }
  }

  if (buffer.trim()) {
    dispatch(buffer, handlers);
  }
}

function dispatch(frame: string, handlers: StreamHandlers): void {
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (dataLines.length === 0) return;

  let payload: unknown;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    return;
  }

  switch (eventName) {
    case "meta":
      handlers.onMeta?.(payload as StreamMeta);
      break;
    case "token":
      handlers.onToken?.((payload as { delta: string }).delta);
      break;
    case "done":
      handlers.onDone?.(payload as StreamDone);
      break;
    case "error":
      handlers.onError?.(payload as { code: string; message: string; hint?: string });
      break;
    default:
      break;
  }
}

export async function stopStream(streamId?: string, conversationId?: string): Promise<void> {
  await fetch("/api/chat/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ stream_id: streamId, conversation_id: conversationId }),
  });
}
