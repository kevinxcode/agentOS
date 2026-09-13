import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET as proxyAudit } from "../app/api/audit/events/route";
import AuditPageComponent from "../app/(dashboard)/audit/page";
import {
  AuditTable,
  auditNextHref,
  auditPreviousHref,
} from "../components/audit/audit-table";
import { PrimaryNavigation } from "../components/navigation/primary-navigation";
import { parseCursorTrail } from "../lib/audit/cursor";
import { loadAuditEvents } from "../lib/audit/server";
import type { AuditPage } from "../lib/audit/types";

vi.mock("next/headers", () => ({ cookies: vi.fn() }));

const PAGE: AuditPage = {
  items: [
    {
      id: "00000000-0000-0000-0000-000000000001",
      request_id: "request-1",
      actor_id: "00000000-0000-0000-0000-000000000002",
      action: "task.executed",
      target_type: "task",
      target_id: "42",
      outcome: "success",
      safe_metadata: { detail: "Completed safely" },
      created_at: "2030-01-01T12:00:00Z",
    },
  ],
  next_cursor: "cursor-next",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("read-only audit table", () => {
  it("renders the safe event fields and exposes no mutation controls", () => {
    render(<AuditTable page={PAGE} filters={{ action: "task.executed", outcome: "success" }} />);

    expect(screen.getByRole("columnheader", { name: "Timestamp" })).toBeVisible();
    expect(screen.getByText("task.executed")).toBeVisible();
    expect(screen.getByText("task · 42")).toBeVisible();
    expect(screen.getByText("request-1")).toBeVisible();
    expect(screen.getByText("Completed safely")).toBeVisible();
    expect(screen.queryByRole("button", { name: /edit|delete/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
  });

  it("synchronizes filters with navigation and clearing", async () => {
    const user = userEvent.setup();
    const navigate = vi.fn();
    const { rerender } = render(
      <AuditTable page={PAGE} filters={{ action: "old.action", outcome: "failure" }} navigate={navigate} />,
    );
    await user.clear(screen.getByLabelText("Action"));
    await user.type(screen.getByLabelText("Action"), "task / created");
    await user.selectOptions(screen.getByLabelText("Outcome"), "denied");
    await user.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(navigate).toHaveBeenLastCalledWith("/audit?action=task+%2F+created&outcome=denied");

    rerender(
      <AuditTable
        page={PAGE}
        filters={{ action: "history.action", outcome: "error", cursor: "history-cursor" }}
        navigate={navigate}
      />,
    );
    expect(screen.getByLabelText("Action")).toHaveValue("history.action");
    expect(screen.getByLabelText("Outcome")).toHaveValue("error");

    await user.clear(screen.getByLabelText("Action"));
    await user.type(screen.getByLabelText("Action"), "unsubmitted draft");
    rerender(
      <AuditTable
        page={PAGE}
        filters={{ action: "history.action", outcome: "error", cursor: "next-history-cursor" }}
        navigate={navigate}
      />,
    );
    expect(screen.getByLabelText("Action")).toHaveValue("history.action");

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByLabelText("Action")).toHaveValue("");
    expect(screen.getByLabelText("Outcome")).toHaveValue("");
    expect(navigate).toHaveBeenLastCalledWith("/audit");
  });

  it("offers rate-limited audit outcomes", () => {
    render(<AuditTable page={PAGE} filters={{}} />);
    expect(screen.getByRole("option", { name: "Rate limited" })).toHaveValue("rate_limited");
  });

  it("uses a bounded explicit cursor trail for next and previous", () => {
    const filters = { action: "task / created", outcome: "success" as const, cursor: "current" };
    let href = auditNextHref(filters, Array.from({ length: 50 }, (_, index) => `cursor-${index}`), "next");
    const nextUrl = new URL(href, "https://agentos.example");
    expect(nextUrl.searchParams.get("action")).toBe("task / created");
    expect(nextUrl.searchParams.get("outcome")).toBe("success");
    expect(nextUrl.searchParams.get("cursor")).toBe("next");
    const trail = parseCursorTrail(nextUrl.searchParams.get("_trail"));
    expect(trail).toHaveLength(50);
    expect(trail[0]).toBe("cursor-1");
    expect(trail[49]).toBe("current");

    href = auditPreviousHref(filters, trail);
    const previousUrl = new URL(href, "https://agentos.example");
    expect(previousUrl.searchParams.get("cursor")).toBe("current");
    expect(previousUrl.searchParams.get("action")).toBe("task / created");
    expect(parseCursorTrail(previousUrl.searchParams.get("_trail"))).toEqual(trail.slice(0, -1));
  });

  it("keeps Previous usable after navigating past page 51", () => {
    let cursor: string | undefined;
    let trail: Array<string | null> = [];
    for (let page = 1; page <= 52; page += 1) {
      const href = auditNextHref({ action: "task.executed", cursor }, trail, `cursor-${page}`);
      const url = new URL(href, "https://agentos.example");
      cursor = url.searchParams.get("cursor") ?? undefined;
      trail = parseCursorTrail(url.searchParams.get("_trail"));
    }
    expect(trail).toHaveLength(50);
    expect(auditPreviousHref({ action: "task.executed", cursor }, trail)).toContain(
      "cursor=cursor-51",
    );
  });
});

describe("audit server fetch and same-origin proxy", () => {
  it("forwards cookies and encoded filters with no-store on the server", async () => {
    const upstream = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(PAGE), { status: 200, headers: { "content-type": "application/json" } }),
    );

    await expect(
      loadAuditEvents(
        "agentos_session=opaque",
        { action: "task / created", outcome: "success", cursor: "cursor+/=" },
        upstream,
      ),
    ).resolves.toEqual(PAGE);

    const [url, options] = upstream.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      "http://api:8000/audit/events?action=task+%2F+created&outcome=success&cursor=cursor%2B%2F%3D",
    );
    expect(options.cache).toBe("no-store");
    expect(new Headers(options.headers).get("cookie")).toBe("agentos_session=opaque");
  });

  it("surfaces 401 for a server-page redirect and rejects malformed success payloads", async () => {
    await expect(
      loadAuditEvents("agentos_session=expired", {}, vi.fn().mockResolvedValue(new Response(null, { status: 401 }))),
    ).rejects.toMatchObject({ status: 401 });
    await expect(
      loadAuditEvents(
        "agentos_session=opaque",
        {},
        vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: "wrong" }), { status: 200 })),
      ),
    ).rejects.toMatchObject({ status: 502 });
  });

  it("redirects an upstream 401 from the server page", async () => {
    vi.mocked(cookies).mockResolvedValue({ toString: () => "agentos_session=expired" } as never);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

    await AuditPageComponent({ searchParams: Promise.resolve({}) });

    expect(redirect).toHaveBeenCalledWith("/login");
  });

  it("renders a generic server-page error for malformed upstream data", async () => {
    vi.mocked(cookies).mockResolvedValue({ toString: () => "agentos_session=opaque" } as never);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: "wrong" }), { status: 200 })),
    );

    render(await AuditPageComponent({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("alert")).toHaveTextContent("Audit history is unavailable");
    expect(screen.getByRole("alert")).not.toHaveTextContent("http://api:8000");
  });

  it("renders a successful server page with its cursor trail through the real client boundary", async () => {
    vi.mocked(cookies).mockResolvedValue({ toString: () => "agentos_session=opaque" } as never);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(PAGE), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    render(
      await AuditPageComponent({
        searchParams: Promise.resolve({
          action: "task.executed",
          outcome: "success",
          cursor: "cursor-current",
          _trail: JSON.stringify(["cursor-previous"]),
        }),
      }),
    );

    expect(screen.getByRole("heading", { name: "Audit" })).toBeVisible();
    expect(screen.getByText("task.executed")).toBeVisible();
    expect(screen.getByRole("button", { name: "Previous" })).toBeEnabled();
  });

  it("preserves a rate-limited outcome in the server-rendered filter", async () => {
    vi.mocked(cookies).mockResolvedValue({ toString: () => "agentos_session=opaque" } as never);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(PAGE), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    render(
      await AuditPageComponent({
        searchParams: Promise.resolve({ outcome: "rate_limited" }),
      }),
    );

    expect(screen.getByLabelText("Outcome")).toHaveValue("rate_limited");
  });

  it("proxies only the public response without leaking the internal API URL", async () => {
    const upstream = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(PAGE), { status: 200, headers: { "content-type": "application/json" } }),
    );
    vi.stubGlobal("fetch", upstream);
    const response = await proxyAudit(
      new NextRequest(
        "https://agentos.example/api/audit/events?action=task+%2F+created&outcome=success&cursor=cursor%2B%2F%3D",
        { headers: { cookie: "agentos_session=opaque" } },
      ),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    const [url, options] = upstream.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      "http://api:8000/audit/events?action=task+%2F+created&outcome=success&cursor=cursor%2B%2F%3D",
    );
    expect(new Headers(options.headers).get("cookie")).toBe("agentos_session=opaque");
    expect(options.cache).toBe("no-store");
    const body = await response.text();
    expect(JSON.parse(body)).toEqual(PAGE);
    expect(body).not.toContain("http://api:8000");
  });

  it("returns a no-store generic 502 for malformed upstream data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: "wrong" }), { status: 200 })),
    );
    const response = await proxyAudit(
      new NextRequest("https://agentos.example/api/audit/events", {
        headers: { cookie: "agentos_session=opaque" },
      }),
    );

    expect(response.status).toBe(502);
    expect(response.headers.get("cache-control")).toBe("no-store");
    const body = await response.text();
    expect(JSON.parse(body)).toEqual({ detail: "Audit service unavailable" });
    expect(body).not.toContain("http://api:8000");
  });
});

describe("route-aware primary navigation", () => {
  it("marks only the current route and includes Audit in mobile navigation", () => {
    render(<PrimaryNavigation pathname="/audit" />);
    const auditLinks = screen.getAllByRole("link", { name: "Audit" });
    const overviewLinks = screen.getAllByRole("link", { name: "Overview" });
    expect(auditLinks).toHaveLength(2);
    expect(auditLinks.every((link) => link.getAttribute("aria-current") === "page")).toBe(true);
    expect(overviewLinks.every((link) => !link.hasAttribute("aria-current"))).toBe(true);
    expect(screen.getByRole("navigation", { name: "Mobile navigation" })).toContainElement(
      auditLinks[1],
    );
  });
});
