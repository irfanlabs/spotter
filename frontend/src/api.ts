import type { AnalysisResult, AnalyzeRequest, HeatmapResult, Place } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
    public fields: Record<string, string[] | string> = {},
    public retryable = false,
  ) {
    super(message);
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function request<T>(path: string, init: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const { timeoutMs = 60_000, signal, ...rest } = init;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(new DOMException("timeout", "TimeoutError")), timeoutMs);
  signal?.addEventListener("abort", () => ctrl.abort(signal.reason), { once: true });

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...rest,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", Accept: "application/json", ...rest.headers },
    });
  } catch (err) {
    if (signal?.aborted) throw err; // caller cancelled; let it propagate silently
    if ((err as DOMException).name === "TimeoutError" || ctrl.signal.reason?.name === "TimeoutError")
      throw new ApiError("The request took too long. Please try again.", "TIMEOUT", 0, {}, true);
    throw new ApiError("Can't reach the server. Check your connection and try again.", "NETWORK", 0, {}, true);
  } finally {
    clearTimeout(timer);
  }

  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON body handled below */
  }

  if (!res.ok) {
    const e = (body as { error?: { code?: string; message?: string; details?: { fields?: Record<string, string[] | string> } } } | null)?.error;
    throw new ApiError(
      e?.message ?? `Unexpected server response (HTTP ${res.status}).`,
      e?.code ?? "HTTP_ERROR",
      res.status,
      e?.details?.fields ?? {},
      res.status >= 500 || res.status === 429,
    );
  }
  if (body === null) throw new ApiError("The server returned an unreadable response.", "BAD_RESPONSE", res.status, {}, true);
  return body as T;
}

export const searchPlaces = (q: string, signal?: AbortSignal, strict = false) =>
  request<{ results: Place[] }>(`/geocode?q=${encodeURIComponent(q)}${strict ? "&strict=1" : ""}`, { signal, timeoutMs: 12_000 });

export const analyze = (body: AnalyzeRequest, signal?: AbortSignal) =>
  request<AnalysisResult>("/analyze", { method: "POST", body: JSON.stringify(body), signal, timeoutMs: 120_000 });

export const fetchHeatmap = (geometries: string[], departure: string, load_weight_lb: number, signal?: AbortSignal) =>
  request<HeatmapResult>("/heatmap", {
    method: "POST",
    body: JSON.stringify({ geometries, departure, load_weight_lb }),
    signal,
    timeoutMs: 90_000,
  });
