"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import {
  serializeCursorTrail,
  type CursorTrail,
} from "../../lib/audit/cursor";
import type { AuditOutcome, AuditPage } from "../../lib/audit/types";

export type AuditFilters = {
  action?: string;
  outcome?: AuditOutcome;
  cursor?: string;
};

function auditHref(filters: AuditFilters, trail: CursorTrail = []): string {
  const parameters = new URLSearchParams();
  if (filters.action) parameters.set("action", filters.action);
  if (filters.outcome) parameters.set("outcome", filters.outcome);
  if (filters.cursor) parameters.set("cursor", filters.cursor);
  if (trail.length) parameters.set("_trail", serializeCursorTrail(trail));
  const query = parameters.toString();
  return `/audit${query ? `?${query}` : ""}`;
}

export function auditNextHref(
  filters: AuditFilters,
  trail: CursorTrail,
  nextCursor: string,
): string {
  const nextTrail = [...trail, filters.cursor ?? null];
  return auditHref({ ...filters, cursor: nextCursor }, nextTrail);
}

export function auditPreviousHref(filters: AuditFilters, trail: CursorTrail): string {
  if (!trail.length) return auditHref(filters);
  const previousCursor = trail.at(-1) ?? undefined;
  return auditHref({ ...filters, cursor: previousCursor }, trail.slice(0, -1));
}

function safeDetail(metadata: Record<string, unknown>): string {
  const detail = metadata.detail;
  if (typeof detail === "string") return detail;
  return Object.keys(metadata).length ? JSON.stringify(metadata) : "—";
}

type AuditTableProps = {
  page: AuditPage;
  filters: AuditFilters;
  trail?: CursorTrail;
  navigate?: (href: string) => void;
};

export function AuditTable(props: AuditTableProps) {
  const stateKey = JSON.stringify([
    props.filters.action ?? "",
    props.filters.outcome ?? "",
    props.filters.cursor ?? "",
    props.trail ?? [],
  ]);
  return <AuditTableView key={stateKey} {...props} />;
}

function AuditTableView({
  page,
  filters,
  trail = [],
  navigate,
}: AuditTableProps) {
  const router = useRouter();
  const go = navigate ?? ((href: string) => router.push(href));
  const [action, setAction] = useState(filters.action ?? "");
  const [outcome, setOutcome] = useState(filters.outcome ?? "");

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    go(
      auditHref({
        action: action.trim() || undefined,
        outcome: (outcome || undefined) as AuditOutcome | undefined,
      }),
    );
  }

  function clear() {
    setAction("");
    setOutcome("");
    go("/audit");
  }

  return (
    <section className="audit-panel" aria-label="Audit events">
      <form className="audit-filters" onSubmit={apply}>
        <label className="field">
          <span>Action</span>
          <input value={action} onChange={(event) => setAction(event.target.value)} />
        </label>
        <label className="field">
          <span>Outcome</span>
          <select value={outcome} onChange={(event) => setOutcome(event.target.value)}>
            <option value="">All outcomes</option>
            <option value="success">Success</option>
            <option value="failure">Failure</option>
            <option value="denied">Denied</option>
            <option value="error">Error</option>
            <option value="rate_limited">Rate limited</option>
          </select>
        </label>
        <div className="audit-filter-actions">
          <button className="primary-button" type="submit">Apply filters</button>
          <button className="secondary-button" type="button" onClick={clear}>Clear filters</button>
        </div>
      </form>

      <div className="audit-table-scroll">
        <table className="audit-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Action</th>
              <th>Target</th>
              <th>Outcome</th>
              <th>Request ID</th>
              <th>Safe detail</th>
            </tr>
          </thead>
          <tbody>
            {page.items.map((event) => (
              <tr key={event.id}>
                <td><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time></td>
                <td>{event.action}</td>
                <td>{event.target_type && event.target_id ? `${event.target_type} · ${event.target_id}` : "—"}</td>
                <td><span className={`outcome outcome-${event.outcome}`}>{event.outcome}</span></td>
                <td><code>{event.request_id}</code></td>
                <td>{safeDetail(event.safe_metadata)}</td>
              </tr>
            ))}
            {!page.items.length && (
              <tr><td className="audit-empty" colSpan={6}>No audit events match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pagination" aria-label="Audit pagination">
        <button
          className="secondary-button"
          type="button"
          disabled={!trail.length}
          onClick={() => go(auditPreviousHref(filters, trail))}
        >
          Previous
        </button>
        <button
          className="secondary-button"
          type="button"
          disabled={!page.next_cursor}
          onClick={() => page.next_cursor && go(auditNextHref(filters, trail, page.next_cursor))}
        >
          Next
        </button>
      </div>
    </section>
  );
}
