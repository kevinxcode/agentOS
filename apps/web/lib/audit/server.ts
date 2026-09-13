import { parseAuditPage, type AuditPage } from "./types";

const API_URL = process.env.AGENTOS_API_URL ?? "http://api:8000";

export type AuditQuery = {
  action?: string;
  outcome?: string;
  cursor?: string;
};

type Fetcher = typeof fetch;

export class AuditFetchError extends Error {
  constructor(readonly status: number) {
    super("Audit history is unavailable");
    this.name = "AuditFetchError";
  }
}

export function auditApiUrl(query: AuditQuery): string {
  const parameters = new URLSearchParams();
  for (const key of ["action", "outcome", "cursor"] as const) {
    if (query[key] !== undefined) parameters.set(key, query[key]);
  }
  const suffix = parameters.toString();
  return `${API_URL}/audit/events${suffix ? `?${suffix}` : ""}`;
}

export async function loadAuditEvents(
  cookieHeader: string,
  query: AuditQuery,
  fetcher: Fetcher = fetch,
): Promise<AuditPage> {
  let response: Response;
  try {
    response = await fetcher(auditApiUrl(query), {
      cache: "no-store",
      headers: { cookie: cookieHeader },
    });
  } catch {
    throw new AuditFetchError(0);
  }
  if (!response.ok) throw new AuditFetchError(response.status);
  try {
    const page = parseAuditPage(await response.json());
    if (page === null) throw new AuditFetchError(502);
    return page;
  } catch (error) {
    if (error instanceof AuditFetchError) throw error;
    throw new AuditFetchError(502);
  }
}
