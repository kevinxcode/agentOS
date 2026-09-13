import type { AuthState } from "./session";

export function authRedirect(state: AuthState): string | null {
  switch (state.status) {
    case "anonymous":
      return "/login";
    case "totp_enrollment":
      return "/enroll";
    case "totp_verification":
      return "/login?step=totp";
    case "authenticated":
      return null;
  }
}
