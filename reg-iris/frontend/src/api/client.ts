import type { ApiErrorBody } from "./types";

const TOKEN = import.meta.env.VITE_API_TOKEN;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public requestId: string | null = null,
  ) {
    super(message);
  }
}

type Primitive = string | number | boolean | undefined | null;
export type Query = Record<string, Primitive | Primitive[]>;

/** Builds `a=1&b=x&b=y` — arrays become repeated keys (FastAPI list params). Empty values are dropped. */
export function toQueryString(query: Query = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    for (const v of Array.isArray(value) ? value : [value]) {
      if (v !== undefined && v !== null && v !== "") params.append(key, String(v));
    }
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export function withAuth(headers: HeadersInit = {}): HeadersInit {
  return TOKEN ? { ...headers, Authorization: `Bearer ${TOKEN}` } : headers;
}

export async function request<T>(path: string, init: RequestInit & { query?: Query } = {}): Promise<T> {
  const { query, ...rest } = init;
  const resp = await fetch(`${path}${toQueryString(query)}`, { ...rest, headers: withAuth(rest.headers) });
  if (!resp.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await resp.json()) as ApiErrorBody;
    } catch {
      /* non-JSON error (e.g. gateway 502) */
    }
    throw new ApiError(
      resp.status,
      body?.error.code ?? `HTTP_${resp.status}`,
      body?.error.message ?? resp.statusText,
      body?.error.details ?? {},
      body?.error.request_id ?? resp.headers.get("X-Request-ID"),
    );
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const getJson = <T>(path: string, query?: Query) => request<T>(path, { query });

export const postJson = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function postForm<T>(path: string, fields: Record<string, string | Blob | undefined | null>) {
  const form = new FormData();
  for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== null && v !== "") form.append(k, v);
  return request<T>(path, { method: "POST", body: form });
}
