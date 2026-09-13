"use client";

import QRCode from "qrcode";
import { FormEvent, useEffect, useId, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";

import {
  confirmTotp,
  type AuthenticatedResponse,
  type CodeRequest,
  type ConfirmationResponse,
  type EnrollmentResponse,
  recoverSession,
  startTotpEnrollment,
  verifyTotp,
} from "../../lib/api/client";

type TotpFormProps = {
  mode: "enroll" | "verify";
  initialEnrollment?: EnrollmentResponse;
  enroll?: () => Promise<EnrollmentResponse>;
  confirm?: (request: CodeRequest) => Promise<ConfirmationResponse>;
  verify?: (request: CodeRequest) => Promise<AuthenticatedResponse>;
  recover?: (request: CodeRequest) => Promise<AuthenticatedResponse>;
  onAuthenticated?: () => void;
};

function safeMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "Authentication failed";
}

function manualSecret(uri: string): string {
  try {
    const secret = new URL(uri).searchParams.get("secret") ?? "";
    return secret.match(/.{1,4}/g)?.join(" ") ?? secret;
  } catch {
    return "";
  }
}

export function TotpForm({
  mode,
  initialEnrollment,
  enroll = startTotpEnrollment,
  confirm = confirmTotp,
  verify = verifyTotp,
  recover = recoverSession,
  onAuthenticated,
}: TotpFormProps) {
  const router = useRouter();
  const complete = onAuthenticated ?? (() => router.replace("/"));
  const descriptionId = useId();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [recoveryMode, setRecoveryMode] = useState(false);
  const [uri, setUri] = useState("");
  const [qr, setQr] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [acknowledged, setAcknowledged] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"" | "copied" | "failed">("");

  useEffect(() => {
    if (mode !== "enroll") return;
    let active = true;
    const enrollment = initialEnrollment ? Promise.resolve(initialEnrollment) : enroll();
    void enrollment
      .then(async (result) => {
        const svg = await QRCode.toString(result.otpauth_uri, {
          type: "svg",
          margin: 1,
          errorCorrectionLevel: "M",
        });
        if (active) {
          setUri(result.otpauth_uri);
          setQr(`data:image/svg+xml,${encodeURIComponent(svg)}`);
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(safeMessage(reason));
      });
    return () => {
      active = false;
    };
  }, [enroll, initialEnrollment, mode]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (mode === "enroll") {
        const result = await confirm({ code });
        setRecoveryCodes(result.recovery_codes);
      } else if (recoveryMode) {
        await recover({ code });
        complete();
      } else {
        await verify({ code });
        complete();
      }
      setCode("");
    } catch (reason) {
      setCode("");
      setError(safeMessage(reason));
    } finally {
      setSubmitting(false);
    }
  }

  async function copyRecoveryCodes() {
    setCopyStatus("");
    try {
      await navigator.clipboard.writeText(recoveryCodes.join("\n"));
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
  }

  function downloadRecoveryCodes() {
    const blob = new Blob([`${recoveryCodes.join("\n")}\n`], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "agentos-recovery-codes.txt";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function finishEnrollment() {
    if (!acknowledged) return;
    setRecoveryCodes([]);
    complete();
  }

  if (recoveryCodes.length > 0) {
    return (
      <section aria-labelledby="recovery-heading" className="recovery-panel">
        <h2 id="recovery-heading">Save your recovery codes</h2>
        <p>Each code works once. Store them somewhere private; they will not be shown again.</p>
        <ul className="recovery-codes" aria-label="Recovery codes">
          {recoveryCodes.map((recoveryCode) => <li key={recoveryCode}>{recoveryCode}</li>)}
        </ul>
        <div className="button-row">
          <button type="button" className="secondary-button" onClick={() => void copyRecoveryCodes()}>
            Copy codes
          </button>
          <button type="button" className="secondary-button" onClick={downloadRecoveryCodes}>
            Download codes
          </button>
        </div>
        {copyStatus === "copied" ? <p role="status">Recovery codes copied</p> : null}
        {copyStatus === "failed" ? (
          <p role="alert" className="error-message">Could not copy recovery codes. Use Download codes instead.</p>
        ) : null}
        <label className="check-row">
          <input
            checked={acknowledged}
            onChange={(event) => setAcknowledged(event.target.checked)}
            type="checkbox"
          />
          I have saved these recovery codes
        </label>
        <button
          className="primary-button"
          disabled={!acknowledged}
          onClick={finishEnrollment}
          type="button"
        >
          Continue to Mission Control
        </button>
      </section>
    );
  }

  const label = recoveryMode ? "Recovery code" : "Authentication code";
  return (
    <div>
      {mode === "enroll" ? (
        <section className="enrollment-setup" aria-labelledby="setup-heading">
          <h2 id="setup-heading">Connect an authenticator</h2>
          <p id={descriptionId}>Scan this QR code, or enter the manual key in your authenticator app.</p>
          {qr ? (
            <Image
              className="qr-code"
              src={qr}
              alt="QR code for authenticator setup"
              height={208}
              unoptimized
              width={208}
            />
          ) : <p>Preparing secure setup…</p>}
          {uri ? <code className="manual-key">{manualSecret(uri)}</code> : null}
        </section>
      ) : (
        <div className="step-heading">
          <p className="eyebrow">Second factor</p>
          <h2>{recoveryMode ? "Use a recovery code" : "Enter your authentication code"}</h2>
        </div>
      )}
      <form className="auth-form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="auth-code">{label}</label>
          <input
            autoComplete={recoveryMode ? "off" : "one-time-code"}
            id="auth-code"
            inputMode={recoveryMode ? "text" : "numeric"}
            name="code"
            onChange={(event) => setCode(event.target.value)}
            required
            type="text"
            value={code}
          />
        </div>
        {error ? <p role="alert" className="error-message">{error}</p> : null}
        <button className="primary-button" disabled={submitting || (mode === "enroll" && !uri)} type="submit">
          {submitting ? "Checking…" : mode === "enroll" ? "Confirm" : "Sign in"}
        </button>
      </form>
      {mode === "verify" ? (
        <button
          className="text-button"
          onClick={() => {
            setCode("");
            setError("");
            setRecoveryMode((current) => !current);
          }}
          type="button"
        >
          {recoveryMode ? "Use an authentication code" : "Use a recovery code"}
        </button>
      ) : null}
    </div>
  );
}
