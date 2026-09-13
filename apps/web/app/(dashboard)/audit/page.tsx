import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AuditTable } from "../../../components/audit/audit-table";
import { parseCursorTrail } from "../../../lib/audit/cursor";
import { AuditFetchError, loadAuditEvents } from "../../../lib/audit/server";
import type { AuditOutcome, AuditPage as AuditPageData } from "../../../lib/audit/types";

type SearchValue = string | string[] | undefined;

function first(value: SearchValue): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function isOutcome(value: string | undefined): value is AuditOutcome {
  return (
    value !== undefined &&
    ["success", "failure", "denied", "error", "rate_limited"].includes(value)
  );
}

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, SearchValue>>;
}) {
  const parameters = await searchParams;
  const action = first(parameters.action);
  const outcome = first(parameters.outcome);
  const cursor = first(parameters.cursor);
  const query = { action, outcome, cursor };
  let page: AuditPageData;
  try {
    const cookieStore = await cookies();
    page = await loadAuditEvents(cookieStore.toString(), query);
  } catch (error) {
    if (error instanceof AuditFetchError && error.status === 401) return redirect("/login");
    return (
      <main className="mission-control audit-page">
        <div className="page-heading"><h1>Audit</h1></div>
        <p className="error-message" role="alert">Audit history is unavailable. Try again.</p>
      </main>
    );
  }
  return (
    <main className="mission-control audit-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Security history</p>
          <h1>Audit</h1>
        </div>
      </div>
      <AuditTable
        page={page}
        filters={{
          action: action || undefined,
          outcome: isOutcome(outcome) ? outcome : undefined,
          cursor: cursor || undefined,
        }}
        trail={parseCursorTrail(first(parameters._trail))}
      />
    </main>
  );
}
