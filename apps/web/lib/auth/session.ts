import { cookies } from "next/headers";

import type { MeResponse } from "../api/client";

const API_URL = process.env.AGENTOS_API_URL ?? "http://api:8000";

export type AuthState =
  | { status: "anonymous" }
  | { status: "totp_enrollment" }
  | { status: "totp_verification" }
  | { status: "authenticated"; user: MeResponse };

type Fetcher = typeof fetch;

export class AuthStateError extends Error {
  constructor(readonly status: number) {
    super("Authentication state is unavailable");
    this.name = "AuthStateError";
  }
}

function headers(cookieHeader: string): HeadersInit {
  return { cookie: cookieHeader };
}

function isFullState(value: unknown): value is MeResponse & { stage: "full" } {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<MeResponse>;
  return (
    (candidate as Partial<{ stage: string }>).stage === "full" &&
    typeof candidate.id === "string" &&
    typeof candidate.email === "string" &&
    typeof candidate.totp_enabled === "boolean"
  );
}

export async function getAuthState(
  cookieHeader: string,
  fetcher: Fetcher = fetch,
): Promise<AuthState> {
  if (!cookieHeader.includes("agentos_session=")) return { status: "anonymous" };

  let response: Response;
  try {
    response = await fetcher(`${API_URL}/auth/state`, {
      cache: "no-store",
      headers: headers(cookieHeader),
    });
  } catch {
    throw new AuthStateError(0);
  }
  if (!response.ok) throw new AuthStateError(response.status);
  const state: unknown = await response.json();
  if (isFullState(state)) {
    const { id, email, totp_enabled } = state;
    return { status: "authenticated", user: { id, email, totp_enabled } };
  }
  if (typeof state === "object" && state !== null) {
    const candidate = state as Partial<{ stage: string; next: string }>;
    if (candidate.stage === "anonymous") return { status: "anonymous" };
    if (candidate.stage === "preauth" && candidate.next === "totp_enrollment") {
      return { status: "totp_enrollment" };
    }
    if (candidate.stage === "preauth" && candidate.next === "totp_verification") {
      return { status: "totp_verification" };
    }
  }
  throw new AuthStateError(502);
}

export async function getRequestAuthState(): Promise<AuthState> {
  const cookieStore = await cookies();
  return getAuthState(cookieStore.toString());
}
