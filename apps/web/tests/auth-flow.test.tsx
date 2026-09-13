import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "../app/api/auth/[...path]/route";
import { LoginForm } from "../components/auth/login-form";
import { TotpForm } from "../components/auth/totp-form";
import { getAuthState } from "../lib/auth/session";
import { parsePublicOrigin } from "../lib/config/public-origin";

const publicOriginCases = JSON.parse(
  readFileSync(resolve(process.cwd(), "../../tests/fixtures/public_origins.json"), "utf8"),
) as Array<{ input: string; canonical: string | null }>;

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("authentication forms", () => {
  it("continues from password to TOTP without storing credentials", async () => {
    const user = userEvent.setup();
    const authenticate = vi.fn().mockResolvedValue({ next: "totp_verification" });
    render(<LoginForm authenticate={authenticate} onAuthenticated={() => undefined} />);

    await user.type(screen.getByLabelText(/email/i), "admin@example.com");
    await user.type(screen.getByLabelText(/password/i), "valid-password");
    await user.click(screen.getByRole("button", { name: /continue/i }));

    expect(await screen.findByLabelText(/authentication code/i)).toBeVisible();
    expect(authenticate).toHaveBeenCalledWith({
      email: "admin@example.com",
      password: "valid-password",
    });
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });

  it("supports one-time recovery sign-in and clears a rejected code", async () => {
    const user = userEvent.setup();
    const recover = vi.fn().mockRejectedValue(new Error("Authentication failed"));
    render(
      <TotpForm
        mode="verify"
        verify={vi.fn()}
        recover={recover}
        onAuthenticated={() => undefined}
      />,
    );

    await user.click(screen.getByRole("button", { name: /use a recovery code/i }));
    const input = screen.getByLabelText(/recovery code/i);
    await user.type(input, "secret-recovery-value");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Authentication failed");
    expect(input).toHaveValue("");
    expect(recover).toHaveBeenCalledWith({ code: "secret-recovery-value" });
  });

  it("shows enrollment QR and manual key, then requires recovery-code acknowledgement", async () => {
    const user = userEvent.setup();
    const enroll = vi.fn().mockResolvedValue({
      otpauth_uri:
        "otpauth://totp/AgentOS%3Aadmin%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=AgentOS",
    });
    const confirm = vi.fn().mockResolvedValue({
      recovery_codes: ["alpha-one", "bravo-two"],
    });
    const finish = vi.fn();
    render(
      <TotpForm
        mode="enroll"
        initialEnrollment={{
          otpauth_uri:
            "otpauth://totp/AgentOS%3Aadmin%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=AgentOS",
        }}
        enroll={enroll}
        confirm={confirm}
        onAuthenticated={finish}
      />,
    );

    expect(await screen.findByRole("img", { name: /qr code/i })).toHaveAttribute(
      "src",
      expect.stringMatching(/^data:image\/svg\+xml/),
    );
    expect(enroll).not.toHaveBeenCalled();
    expect(screen.getByText("JBSW Y3DP EHPK 3PXP")).toBeVisible();
    await user.type(screen.getByLabelText(/authentication code/i), "123456");
    await user.click(screen.getByRole("button", { name: /confirm/i }));

    expect(await screen.findByText("alpha-one")).toBeVisible();
    const continueButton = screen.getByRole("button", { name: /continue to mission control/i });
    expect(continueButton).toBeDisabled();
    await user.click(screen.getByLabelText(/saved these recovery codes/i));
    expect(continueButton).toBeEnabled();
    await user.click(continueButton);
    expect(finish).toHaveBeenCalledOnce();
  });

  it("announces recovery-code copy success", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    render(
      <TotpForm
        mode="enroll"
        initialEnrollment={{ otpauth_uri: "otpauth://totp/AgentOS?secret=AAAA" }}
        confirm={vi.fn().mockResolvedValue({ recovery_codes: ["alpha-one"] })}
        onAuthenticated={() => undefined}
      />,
    );
    await user.type(await screen.findByLabelText(/authentication code/i), "123456");
    await user.click(screen.getByRole("button", { name: /confirm/i }));
    await user.click(await screen.findByRole("button", { name: /copy codes/i }));

    expect(screen.getByRole("status")).toHaveTextContent("Recovery codes copied");
    expect(writeText).toHaveBeenCalledWith("alpha-one");
  });

  it("retains recovery codes and announces clipboard failure", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    render(
      <TotpForm
        mode="enroll"
        initialEnrollment={{ otpauth_uri: "otpauth://totp/AgentOS?secret=AAAA" }}
        confirm={vi.fn().mockResolvedValue({ recovery_codes: ["alpha-one"] })}
        onAuthenticated={() => undefined}
      />,
    );
    await user.type(await screen.findByLabelText(/authentication code/i), "123456");
    await user.click(screen.getByRole("button", { name: /confirm/i }));
    await user.click(await screen.findByRole("button", { name: /copy codes/i }));

    expect(screen.getByRole("alert")).toHaveTextContent("Could not copy recovery codes");
    expect(screen.getByText("alpha-one")).toBeVisible();
  });
});

describe("public origin configuration", () => {
  it("accepts one canonical HTTP origin and rejects URLs with ambient authority", () => {
    expect(parsePublicOrigin("https://agentos.example:8443", "production")).toBe(
      "https://agentos.example:8443",
    );
    for (const invalid of [
      "https://user:password@agentos.example",
      "https://agentos.example/path",
      "https://agentos.example?query=1",
      "https://agentos.example/#fragment",
      "ftp://agentos.example",
      "http://agentos.example",
    ]) {
      expect(() => parsePublicOrigin(invalid, "production")).toThrow(/public origin/i);
    }
    expect(() => parsePublicOrigin("", "production")).toThrow(/required/i);
  });

  it.each([
    ["https://AgentOS.EXAMPLE:443/", "https://agentos.example"],
    ["http://LOCALHOST:80", "http://localhost"],
    ["http://127.0.0.1:80", "http://127.0.0.1"],
  ])("normalizes %s to %s", (supplied, canonical) => {
    expect(parsePublicOrigin(supplied, "production")).toBe(canonical);
  });

  it.each(publicOriginCases)("shares the canonical policy for $input", ({ input, canonical }) => {
    if (canonical === null) {
      expect(() => parsePublicOrigin(input, "production")).toThrow(/public origin/i);
    } else {
      expect(parsePublicOrigin(input, "production")).toBe(canonical);
    }
  });
});

describe("same-origin auth proxy", () => {
  it("rejects cookie-authenticated cross-site mutations before forwarding", async () => {
    const upstream = vi.fn();
    vi.stubGlobal("fetch", upstream);
    const request = new NextRequest("https://agentos.example/api/auth/logout", {
      method: "POST",
      headers: {
        cookie: "agentos_session=opaque",
        origin: "https://attacker.example",
        "sec-fetch-site": "cross-site",
      },
    });

    const response = await POST(request, { params: Promise.resolve({ path: ["logout"] }) });

    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ detail: "Cross-site request blocked" });
    expect(upstream).not.toHaveBeenCalled();
  });

  it("rejects hostile Fetch Metadata even when the Origin value matches", async () => {
    const upstream = vi.fn();
    vi.stubGlobal("fetch", upstream);
    const request = new NextRequest("https://agentos.example/api/auth/logout", {
      method: "POST",
      headers: {
        cookie: "agentos_session=opaque",
        origin: "https://agentos.example",
        "sec-fetch-site": "cross-site",
      },
    });

    const response = await POST(request, { params: Promise.resolve({ path: ["logout"] }) });

    expect(response.status).toBe(403);
    expect(upstream).not.toHaveBeenCalled();
  });

  it("accepts the configured public origin even when Next is bound to an internal host", async () => {
    vi.stubEnv("AGENTOS_PUBLIC_ORIGIN", "https://agentos.example");
    const upstream = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ authenticated: true }), {
        status: 200,
        headers: {
          "content-type": "application/json",
          "set-cookie": "agentos_session=replaced; HttpOnly; SameSite=Strict; Path=/",
        },
      }),
    );
    vi.stubGlobal("fetch", upstream);
    const request = new NextRequest("http://0.0.0.0:3000/api/auth/totp/verify", {
      method: "POST",
      body: JSON.stringify({ code: "123456" }),
      headers: {
        "content-type": "application/json",
        origin: "https://agentos.example",
        "sec-fetch-site": "same-origin",
      },
    });

    const response = await POST(request, {
      params: Promise.resolve({ path: ["totp", "verify"] }),
    });

    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toContain("agentos_session=replaced");
    const [, options] = upstream.mock.calls[0] as [string, RequestInit];
    expect(new TextDecoder().decode(options.body as Uint8Array)).toBe('{"code":"123456"}');
  });

  it("authenticates Cloudflare client identity and ignores browser proxy-header spoofing", async () => {
    vi.stubEnv("AGENTOS_AUTH_PROXY_SECRET", "s".repeat(32));
    const upstream = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ next: "totp_verification" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", upstream);
    const request = new NextRequest("https://agentos.example/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: "admin@example.com", password: "valid-password" }),
      headers: {
        "cf-connecting-ip": "198.51.100.42",
        "content-type": "application/json",
        origin: "https://agentos.example",
        "sec-fetch-site": "same-origin",
        "x-agentos-client-ip": "203.0.113.99",
        "x-agentos-proxy-secret": "attacker-value",
      },
    });

    expect(
      (await POST(request, { params: Promise.resolve({ path: ["login"] }) })).status,
    ).toBe(200);
    const [, options] = upstream.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(options.headers);
    expect(headers.get("x-agentos-client-ip")).toBe("198.51.100.42");
    expect(headers.get("x-agentos-proxy-secret")).toBe("s".repeat(32));
  });

  it("rejects oversized declared auth bodies before reading or forwarding", async () => {
    const upstream = vi.fn();
    vi.stubGlobal("fetch", upstream);
    const request = new NextRequest("https://agentos.example/api/auth/login", {
      method: "POST",
      body: "{}",
      headers: {
        "content-length": "20000",
        "content-type": "application/json",
        origin: "https://agentos.example",
        "sec-fetch-site": "same-origin",
      },
    });
    const arrayBuffer = vi.spyOn(request, "arrayBuffer");

    const response = await POST(request, { params: Promise.resolve({ path: ["login"] }) });

    expect(response.status).toBe(413);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(arrayBuffer).not.toHaveBeenCalled();
    expect(upstream).not.toHaveBeenCalled();
  });

  it("enforces a cumulative body limit when Content-Length is absent", async () => {
    const upstream = vi.fn();
    vi.stubGlobal("fetch", upstream);
    const chunk = new Uint8Array(9_000);
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(chunk);
        controller.enqueue(chunk);
        controller.close();
      },
    });
    const init = {
      method: "POST",
      body,
      duplex: "half",
      headers: {
        "content-type": "application/json",
        origin: "https://agentos.example",
        "sec-fetch-site": "same-origin",
      },
    } as unknown as ConstructorParameters<typeof NextRequest>[1];
    const request = new NextRequest("https://agentos.example/api/auth/login", init);

    const response = await POST(request, { params: Promise.resolve({ path: ["login"] }) });

    expect(response.status).toBe(413);
    expect(upstream).not.toHaveBeenCalled();
  });

  it("forwards an allowed path and the opaque cookie without exposing the API address", async () => {
    const upstream = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "1", email: "admin@example.com", totp_enabled: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", upstream);
    const request = new NextRequest("https://agentos.example/api/auth/me", {
      headers: { cookie: "agentos_session=opaque" },
    });

    const response = await GET(request, { params: Promise.resolve({ path: ["me"] }) });

    expect(response.status).toBe(200);
    expect(upstream).toHaveBeenCalledOnce();
    const [url, options] = upstream.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api:8000/auth/me");
    expect(options.cache).toBe("no-store");
    expect(new Headers(options.headers).get("cookie")).toBe("agentos_session=opaque");
    expect(await response.json()).toEqual({
      id: "1",
      email: "admin@example.com",
      totp_enabled: true,
    });
  });

  it("rejects paths outside the accepted Task 5 auth contract", async () => {
    const response = await GET(
      new NextRequest("https://agentos.example/api/auth/debug"),
      { params: Promise.resolve({ path: ["debug"] }) },
    );

    expect(response.status).toBe(404);
  });
});

describe("server session state", () => {
  it("uses the read-only state endpoint to route every authentication stage", async () => {
    const fullFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ stage: "full", id: "1", email: "admin@example.com", totp_enabled: true }), {
        status: 200,
      }),
    );
    await expect(getAuthState("agentos_session=full", fullFetch)).resolves.toMatchObject({
      status: "authenticated",
      user: { email: "admin@example.com" },
    });

    const enrollFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ stage: "preauth", next: "totp_enrollment" }), { status: 200 }),
    );
    await expect(getAuthState("agentos_session=pre", enrollFetch)).resolves.toEqual({
      status: "totp_enrollment",
    });

    const verifyFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ stage: "preauth", next: "totp_verification" }), { status: 200 }),
    );
    await expect(getAuthState("agentos_session=pre", verifyFetch)).resolves.toEqual({
      status: "totp_verification",
    });

    await expect(getAuthState("", vi.fn())).resolves.toEqual({ status: "anonymous" });
    expect(enrollFetch).toHaveBeenCalledOnce();
    expect(String(enrollFetch.mock.calls[0][0])).toContain("/auth/state");
  });

  it("preserves rate-limit and service failures instead of treating them as anonymous", async () => {
    await expect(
      getAuthState(
        "agentos_session=pre",
        vi.fn().mockResolvedValue(new Response(null, { status: 429 })),
      ),
    ).rejects.toMatchObject({ status: 429 });
    await expect(
      getAuthState(
        "agentos_session=pre",
        vi.fn().mockResolvedValue(new Response(null, { status: 503 })),
      ),
    ).rejects.toMatchObject({ status: 503 });
  });
});

describe("secret-safe interactions", () => {
  it("never writes submitted credentials to console output", async () => {
    const user = userEvent.setup();
    const log = vi.spyOn(console, "log");
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <LoginForm
        authenticate={vi.fn().mockRejectedValue(new Error("Authentication failed"))}
        onAuthenticated={() => undefined}
      />,
    );
    await user.type(screen.getByLabelText(/email/i), "admin@example.com");
    await user.type(screen.getByLabelText(/password/i), "password-sentinel");
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeVisible());

    expect(JSON.stringify(log.mock.calls) + JSON.stringify(error.mock.calls)).not.toContain(
      "password-sentinel",
    );
  });
});
