export type LoginRequest = { email: string; password: string };
export type CodeRequest = { code: string };
export type LoginResponse = { next: "totp_enrollment" | "totp_verification" };
export type EnrollmentResponse = { otpauth_uri: string };
export type ConfirmationResponse = { recovery_codes: string[] };
export type AuthenticatedResponse = { authenticated: true };
export type MeResponse = {
  id: string;
  email: string;
  totp_enabled: boolean;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly retryAfter?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function authRequest<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`/api/auth/${path}`, {
    method: "POST",
    cache: "no-store",
    credentials: "same-origin",
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const message =
      response.status === 429
        ? "Too many attempts. Wait a minute and try again."
        : response.status === 409
          ? "TOTP is already enrolled. Sign in with an authentication code."
          : response.status === 401
            ? "Authentication failed"
            : "The authentication service is unavailable. Try again.";
    throw new ApiError(message, response.status, response.headers.get("retry-after") ?? undefined);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const login = (request: LoginRequest) => authRequest<LoginResponse>("login", request);
export const startTotpEnrollment = () => authRequest<EnrollmentResponse>("totp/enroll");
export const confirmTotp = (request: CodeRequest) =>
  authRequest<ConfirmationResponse>("totp/confirm", request);
export const verifyTotp = (request: CodeRequest) =>
  authRequest<AuthenticatedResponse>("totp/verify", request);
export const recoverSession = (request: CodeRequest) =>
  authRequest<AuthenticatedResponse>("recovery", request);
export const logout = () => authRequest<void>("logout");
