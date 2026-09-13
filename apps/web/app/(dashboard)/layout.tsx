import type { ReactNode } from "react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { LogoutButton } from "../../components/auth/logout-button";
import { PrimaryNavigation } from "../../components/navigation/primary-navigation";
import { authRedirect } from "../../lib/auth/redirects";
import { getRequestAuthState } from "../../lib/auth/session";

export default async function DashboardLayout({ children }: Readonly<{ children: ReactNode }>) {
  const state = await getRequestAuthState();
  const destination = authRedirect(state);
  if (destination) redirect(destination);
  if (state.status !== "authenticated") return null;

  return (
    <div className="dashboard-shell">
      <header className="topbar">
        <Link className="wordmark" href="/" aria-label="AgentOS Mission Control">
          <span className="brand-mark brand-mark-small" aria-hidden="true">AO</span>
          <span>AgentOS</span>
        </Link>
        <div className="account-area">
          <span className="account-email">{state.user.email}</span>
          <LogoutButton />
        </div>
      </header>
      <div className="dashboard-body">
        <PrimaryNavigation />
        {children}
      </div>
    </div>
  );
}
