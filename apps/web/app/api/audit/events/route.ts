import { NextRequest, NextResponse } from "next/server";

import { auditApiUrl } from "../../../../lib/audit/server";
import { parseAuditPage } from "../../../../lib/audit/types";

const NO_STORE = { "cache-control": "no-store" };

function failure(status: number) {
  const detail =
    status === 401
      ? "Authentication required"
      : status === 422
        ? "Invalid request"
        : "Audit service unavailable";
  return NextResponse.json({ detail }, { status, headers: NO_STORE });
}

export async function GET(request: NextRequest) {
  const action = request.nextUrl.searchParams.get("action");
  const outcome = request.nextUrl.searchParams.get("outcome");
  const cursor = request.nextUrl.searchParams.get("cursor");
  const cookie = request.headers.get("cookie");
  try {
    const upstream = await fetch(
      auditApiUrl({
        action: action ?? undefined,
        outcome: outcome ?? undefined,
        cursor: cursor ?? undefined,
      }),
      {
        cache: "no-store",
        headers: cookie ? { cookie } : undefined,
      },
    );
    if (!upstream.ok) return failure(upstream.status === 401 || upstream.status === 422 ? upstream.status : 502);
    const page = parseAuditPage(await upstream.json());
    if (page === null) return failure(502);
    return NextResponse.json(page, { status: 200, headers: NO_STORE });
  } catch {
    return failure(502);
  }
}
