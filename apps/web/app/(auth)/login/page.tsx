import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { LoginForm } from "../../../components/auth/login-form";
import { getRequestAuthState } from "../../../lib/auth/session";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage() {
  const state = await getRequestAuthState();
  if (state.status === "authenticated") redirect("/");
  if (state.status === "totp_enrollment") redirect("/enroll");

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="login-heading">
        <div className="brand-mark" aria-hidden="true">AO</div>
        <p className="eyebrow">AgentOS · Private control plane</p>
        <h1 id="login-heading">
          {state.status === "totp_verification" ? "Complete sign in" : "Welcome back"}
        </h1>
        <p className="auth-intro">
          {state.status === "totp_verification"
            ? "Confirm this sign-in with your authenticator or a recovery code."
            : "Sign in to open your secure Mission Control workspace."}
        </p>
        <LoginForm initialStep={state.status === "totp_verification" ? "totp" : "password"} />
      </section>
    </main>
  );
}
