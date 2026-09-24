let token: string | null = null;
let workspace: string | null = null;
const base = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");
if (!base.startsWith("/") && !/^https?:\/\//.test(base))
  throw new Error(
    "VITE_API_URL must be an HTTP URL or a relative path starting with /.",
  );
export function configureApi(
  nextToken: string | null,
  nextWorkspace: string | null,
) {
  token = nextToken;
  workspace = nextWorkspace;
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      ...options,
      headers: {
        ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(workspace ? { "X-Workspace-Id": workspace } : {}),
        ...options.headers,
      },
    });
  } catch {
    throw new ApiError(
      "Unable to reach the server. Check your connection and try again.",
      0,
    );
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && path != "/auth/login")
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(
      data?.message || `Request failed (${response.status}).`,
      response.status,
      data?.details || {},
    );
  }
  return data as T;
}
export const write = (path: string, body: unknown, method = "POST") =>
  api(path, { method, body: JSON.stringify(body) });
export const upload = <T = any>(path: string, files: File[]) => {
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  return api<T>(path, { method: "POST", body });
};
