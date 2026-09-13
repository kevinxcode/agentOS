"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { logout } from "../../lib/api/client";

export function LogoutButton() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function signOut() {
    setError("");
    setSubmitting(true);
    try {
      await logout();
      router.replace("/login");
    } catch {
      setError("Could not sign out. Try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="logout-control">
      <button className="secondary-button" disabled={submitting} onClick={() => void signOut()} type="button">
        {submitting ? "Signing out…" : "Sign out"}
      </button>
      {error ? <span role="alert">{error}</span> : null}
    </div>
  );
}
