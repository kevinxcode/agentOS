"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import {
  login,
  type LoginRequest,
  type LoginResponse,
  recoverSession,
  verifyTotp,
} from "../../lib/api/client";
import { TotpForm } from "./totp-form";

type LoginFormProps = {
  authenticate?: (request: LoginRequest) => Promise<LoginResponse>;
  initialStep?: "password" | "totp";
  onAuthenticated?: () => void;
  onEnrollmentRequired?: () => void;
};

export function LoginForm({
  authenticate = login,
  initialStep = "password",
  onAuthenticated,
  onEnrollmentRequired,
}: LoginFormProps) {
  const router = useRouter();
  const complete = onAuthenticated ?? (() => router.replace("/"));
  const beginEnrollment = onEnrollmentRequired ?? (() => router.replace("/enroll"));
  const [step, setStep] = useState(initialStep);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (step === "totp") {
    return (
      <TotpForm
        mode="verify"
        verify={verifyTotp}
        recover={recoverSession}
        onAuthenticated={complete}
      />
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const result = await authenticate({ email: email.trim(), password });
      setPassword("");
      if (result.next === "totp_enrollment") beginEnrollment();
      else setStep("totp");
    } catch (reason) {
      setPassword("");
      setError(reason instanceof Error ? reason.message : "Authentication failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="auth-form" onSubmit={submit}>
      <div className="field">
        <label htmlFor="email">Email</label>
        <input
          autoComplete="username"
          id="email"
          inputMode="email"
          maxLength={254}
          name="email"
          onChange={(event) => setEmail(event.target.value)}
          required
          type="email"
          value={email}
        />
      </div>
      <div className="field">
        <label htmlFor="password">Password</label>
        <input
          autoComplete="current-password"
          id="password"
          name="password"
          onChange={(event) => setPassword(event.target.value)}
          required
          type="password"
          value={password}
        />
      </div>
      {error ? <p role="alert" className="error-message">{error}</p> : null}
      <button className="primary-button" disabled={submitting} type="submit">
        {submitting ? "Checking…" : "Continue"}
      </button>
    </form>
  );
}
