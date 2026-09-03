/**
 * Thin fetch wrapper for Bread's API.
 *
 * Two things it exists to guarantee: every error surfaces the server's
 * structured body rather than a bare status code, and the API key (when the
 * server requires one) is attached to every request from one place.
 */

import type { ApiErrorBody } from "./types";

const API_KEY_STORAGE_KEY = "bread.apiKey";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly hint?: string;
  readonly details?: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.hint = body.hint;
    this.details = body.details;
  }
}

export function getApiKey(): string {
  try {
    return window.localStorage.getItem(API_KEY_STORAGE_KEY) ?? "";
  } catch {
    // Private browsing and locked-down profiles both throw here. Losing the
    // stored key is survivable; crashing the app is not.
    return "";
  }
}

export function setApiKey(key: string): void {
  try {
    if (key) {
      window.localStorage.setItem(API_KEY_STORAGE_KEY, key);
    } else {
      window.localStorage.removeItem(API_KEY_STORAGE_KEY);
    }
  } catch {
    /* ignore */
  }
}

export function authHeaders(): Record<string, string> {
  const key = getApiKey();
  return key ? { "X-API-Key": key } : {};
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = {
    code: `http_${response.status}`,
    message: response.statusText || "The request failed.",
  };
  try {
    const parsed = (await response.json()) as { error?: ApiErrorBody };
    if (parsed?.error) {
      body = parsed.error;
    }
  } catch {
    /* the response was not JSON; the default body already says enough */
  }
  return new ApiError(response.status, body);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...authHeaders(),
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (init.body && !(init.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch (cause) {
    throw new ApiError(0, {
      code: "network_unreachable",
      message: "Could not reach the Bread server.",
      hint:
        "Start it with `python -m app.cli serve` from the backend directory, " +
        "then reload this page.",
      details: { cause: String(cause) },
    });
  }

  if (!response.ok) {
    throw await toApiError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),
};

export function describeError(error: unknown): { message: string; hint?: string } {
  if (error instanceof ApiError) {
    return { message: error.message, hint: error.hint };
  }
  if (error instanceof Error) {
    return { message: error.message };
  }
  return { message: "Something went wrong." };
}
