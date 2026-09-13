export type AuditOutcome = "success" | "failure" | "denied" | "error" | "rate_limited";

export type AuditEvent = {
  id: string;
  request_id: string;
  actor_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  outcome: string;
  safe_metadata: Record<string, unknown>;
  created_at: string;
};

export type AuditPage = {
  items: AuditEvent[];
  next_cursor: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

function isAuditEvent(value: unknown): value is AuditEvent {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "string" &&
    typeof value.request_id === "string" &&
    nullableString(value.actor_id) &&
    typeof value.action === "string" &&
    nullableString(value.target_type) &&
    nullableString(value.target_id) &&
    typeof value.outcome === "string" &&
    isRecord(value.safe_metadata) &&
    typeof value.created_at === "string"
  );
}

export function parseAuditPage(value: unknown): AuditPage | null {
  if (!isRecord(value) || !Array.isArray(value.items) || !nullableString(value.next_cursor)) {
    return null;
  }
  return value.items.every(isAuditEvent)
    ? { items: value.items, next_cursor: value.next_cursor }
    : null;
}
