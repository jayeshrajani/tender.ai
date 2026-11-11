export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fieldErrors: Record<string, string> = {},
  ) {
    super(message);
  }
}

type Detail = string | { loc?: (string | number)[]; msg?: string }[] | undefined;

function parseDetail(detail: Detail): { message: string; fields: Record<string, string> } {
  if (typeof detail === "string") return { message: detail, fields: {} };
  if (Array.isArray(detail)) {
    const fields: Record<string, string> = {};
    for (const d of detail) {
      const key = String(d.loc?.[d.loc.length - 1] ?? "form");
      fields[key] = (d.msg ?? "Invalid value").replace(/^Value error, /, "");
    }
    return { message: Object.values(fields)[0] ?? "Please check the highlighted fields.", fields };
  }
  return { message: "Something went wrong.", fields: {} };
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(path, {
    credentials: "same-origin",
    ...rest,
    headers: {
      Accept: "application/json",
      "X-Requested-With": "tenderos",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? (JSON.parse(text) as unknown) : undefined;
  if (!res.ok) {
    const { message, fields } = parseDetail((data as { detail?: Detail } | undefined)?.detail);
    throw new ApiError(res.status, message, fields);
  }
  return data as T;
}

export function qs(params: Record<string, string | number | boolean | string[] | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x));
    else sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
