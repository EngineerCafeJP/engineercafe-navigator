/**
 * Shared utility for proxying requests to the FastAPI backend.
 *
 * Reads BACKEND_API_URL and BACKEND_API_KEY from environment variables
 * and attaches the X-API-Key header to every outgoing request.
 */

const BACKEND_API_URL = process.env.BACKEND_API_URL;

if (!BACKEND_API_URL) {
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
}

export interface BackendProxyResult<T = unknown> {
  readonly ok: boolean;
  readonly status: number;
  readonly data: T;
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
  const { method = "POST", body, headers = {}, params, signal } = opts;
  const apiKey = process.env.BACKEND_API_KEY || "";

  const url = buildUrl(path, params);

  const mergedHeaders: Record<string, string> = { ...headers };

  if (!(method === "GET" && body === undefined)) {
    mergedHeaders["Content-Type"] ??= "application/json";
  }

  if (apiKey) {
    mergedHeaders["X-API-Key"] = apiKey;
  }

  // 35s > backend's 30s workflow timeout, so the backend can return its
  // graceful timeout response before the frontend aborts the connection.
  const effectiveSignal = signal ?? AbortSignal.timeout(35_000);

  const fetchInit: RequestInit = {
    method,
    headers: mergedHeaders,
    signal: effectiveSignal,
  };

  if (body !== undefined && method !== "GET") {
    fetchInit.body = JSON.stringify(body);
  }

  const response = await fetch(url, fetchInit);
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
  if (!BACKEND_API_URL) {
    throw new Error(
      "BACKEND_API_URL environment variable is not set. Cannot proxy to backend.",
    );
  }
  const base = BACKEND_API_URL.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${base}${normalizedPath}`);

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      url.searchParams.set(key, value);
    }
  }

  return url.toString();
}
