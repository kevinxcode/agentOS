import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { TotpForm } from "../../../components/auth/totp-form";
import { getRequestAuthState } from "../../../lib/auth/session";

export const metadata: Metadata = { title: "Secure your account" };

export default async function EnrollPage() {
  const state = await getRequestAuthState();
  if (state.status === "authenticated") redirect("/");
  if (state.status === "anonymous") redirect("/login");
  if (state.status === "totp_verification") redirect("/login?step=totp");

  return (
    <main className="auth-shell">
      <section className="auth-card auth-card-wide" aria-labelledby="enroll-heading">
        <p className="eyebrow">Required security setup</p>
        <h1 id="enroll-heading">Protect your administrator account</h1>
        <p className="auth-intro">
          AgentOS requires a time-based authentication code after your password.
        </p>
        <TotpForm mode="enroll" />
      </section>
    </main>
  );
}
