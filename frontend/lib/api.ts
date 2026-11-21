/**
 * Backend endpoint configuration and JSON fetch helpers.
 *
 * The backend base URL is configurable via NEXT_PUBLIC_API_BASE_URL so the
 * frontend can be deployed separately from the FastAPI service (see the
 * README architecture: frontend on S3/CloudFront, backend on EC2/ECS).
 * Falls back to the local dev default.
 */
export function resolveApiBase(raw?: string): string {
  const trimmed = (raw ?? '').trim();
  return (trimmed || 'http://localhost:8000').replace(/\/+$/, '');
}

export const API_BASE = resolveApiBase(process.env.NEXT_PUBLIC_API_BASE_URL);

export function apiUrl(path: string): string {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

export class ApiRequestError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
  }
}

/**
 * Parse a fetch Response as JSON, throwing an ApiRequestError with the
 * server's error detail on non-2xx statuses instead of letting the caller
 * render an empty result. Non-JSON error bodies fall back to the raw text.
 */
export async function readJson<T = unknown>(res: Response): Promise<T> {
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!res.ok) {
    const detail =
      body && typeof (body as { detail?: unknown }).detail === 'string'
        ? ((body as { detail: string }).detail)
        : text.trim().slice(0, 200) || res.statusText || `HTTP ${res.status}`;
    throw new ApiRequestError(detail, res.status);
  }
  return body as T;
}
