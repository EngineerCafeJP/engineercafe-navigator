/**
 * Shared utility for proxying requests to the FastAPI backend.
 *
 * Reads BACKEND_API_URL and BACKEND_API_KEY from environment variables
 * and attaches the X-API-Key header to every outgoing request.
 */

export const BACKEND_PROXY_TIMEOUT_MS = 110_000;
export const VERCEL_VOICE_MAX_DURATION_MS = 120_000;
export const CLOUD_RUN_TIMEOUT_MS = 300_000;
export const ISSUE_696_WORST_OBSERVED_LATENCY_MS = 97_630;

if (!process.env.BACKEND_API_URL) {
  console.warn(
    "BACKEND_API_URL is not set. Backend proxy requests will fail.",
  );
}

export interface BackendProxyOptions {
  /** HTTP method (defaults to POST). */
  readonly method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  /** JSON-serialisable request body. */
  readonly body?: unknown;
  /** Extra headers to merge (Content-Type and X-API-Key are set automatically). */
  readonly headers?: Readonly<Record<string, string>>;
  /** Query string parameters for GET requests. */
  readonly params?: Readonly<Record<string, string>>;
  /** Abort signal for request cancellation. */
  readonly signal?: AbortSignal;
  /** Optional timeout for the generated abort signal when no explicit signal is provided. */
  readonly timeoutMs?: number;
}

export interface BackendProxyResult<T = unknown> {
  readonly ok: boolean;
  readonly status: number;
  readonly data: T;
}

const BACKEND_TIMEOUT_STATUS = 504;
const BACKEND_TIMEOUT_ERROR = "Backend request timed out";

function isAbortLikeError(error: unknown): boolean {
  if (!(error instanceof Error || error instanceof DOMException)) {
    return false;
  }

  return error.name === "TimeoutError" || error.name === "AbortError";
}

/**
 * Send a request to the backend, automatically attaching X-API-Key.
 *
 * @param path  - Path relative to BACKEND_API_URL (e.g. "/api/chat").
 * @param opts  - Request options.
 * @returns     Typed proxy result with status and parsed JSON body.
 */
export async function backendFetch<T = unknown>(
  path: string,
  opts: BackendProxyOptions = {},
): Promise<BackendProxyResult<T>> {
  const { method = "POST", body, headers = {}, params, signal, timeoutMs } = opts;
  const apiKey = process.env.BACKEND_API_KEY?.trim();

  if (!apiKey) {
    throw new Error(
      "BACKEND_API_KEY environment variable is not set. Refusing to proxy to backend.",
    );
  }

  const url = buildUrl(path, params);

  const mergedHeaders: Record<string, string> = { ...headers };

  if (!(method === "GET" && body === undefined)) {
    mergedHeaders["Content-Type"] ??= "application/json";
  }

  mergedHeaders["X-API-Key"] = apiKey;

  // Keep the default proxy timeout below Vercel's 120s route maxDuration and
  // above the Issue #696 observed 60-97s cold-start range. This lets the client
  // receive a controlled error instead of a platform-level silent timeout.
  const effectiveSignal = signal ?? AbortSignal.timeout(timeoutMs ?? BACKEND_PROXY_TIMEOUT_MS);

  const fetchInit: RequestInit = {
    method,
    headers: mergedHeaders,
    signal: effectiveSignal,
  };

  if (body !== undefined && method !== "GET") {
    fetchInit.body = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(url, fetchInit);
  } catch (error) {
    if (signal === undefined && isAbortLikeError(error)) {
      return {
        ok: false,
        status: BACKEND_TIMEOUT_STATUS,
        data: {
          error: BACKEND_TIMEOUT_ERROR,
          details:
            "The backend did not respond before the Vercel proxy timeout. Try again after the voice service finishes warming up.",
        } as T,
      };
    }
    throw error;
  }

  let data: T;
  try {
    data = (await response.json()) as T;
  } catch {
    data = undefined as unknown as T;
  }

  return { ok: response.ok, status: response.status, data };
}

/** Build full URL with optional query parameters. */
function buildUrl(
  path: string,
  params?: Readonly<Record<string, string>>,
): string {
  const backendApiUrl = process.env.BACKEND_API_URL?.trim();

  if (!backendApiUrl) {
    throw new Error(
      "BACKEND_API_URL environment variable is not set. Cannot proxy to backend.",
    );
  }
  const base = backendApiUrl.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${base}${normalizedPath}`);

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      url.searchParams.set(key, value);
    }
  }

  return url.toString();
}
