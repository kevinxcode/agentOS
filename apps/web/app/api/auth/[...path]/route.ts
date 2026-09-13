import { NextRequest, NextResponse } from "next/server";
import { isIP } from "node:net";

import { getPublicOrigin } from "../../../../lib/config/public-origin";

const API_URL = process.env.AGENTOS_API_URL ?? "http://api:8000";
const GET_PATHS = new Set(["me", "state"]);
const POST_PATHS = new Set([
  "login",
  "totp/enroll",
  "totp/confirm",
  "totp/verify",
  "recovery",
  "logout",
]);
const RESPONSE_HEADERS = ["cache-control", "content-type", "retry-after", "set-cookie"];
const MAX_AUTH_BODY_BYTES = 16 * 1024;
const CLIENT_IP_HEADER = "x-agentos-client-ip";
const PROXY_SECRET_HEADER = "x-agentos-proxy-secret";

type RouteContext = { params: Promise<{ path: string[] }> };

class BodyTooLarge extends Error {}

function requestClientIp(request: NextRequest): string {
  const cloudflareAddress = request.headers.get("cf-connecting-ip");
  return cloudflareAddress !== null && isIP(cloudflareAddress) ? cloudflareAddress : "unknown";
}

async function readBody(request: NextRequest): Promise<Uint8Array | undefined> {
  const declared = request.headers.get("content-length");
  if (declared !== null && /^\d+$/.test(declared) && Number(declared) > MAX_AUTH_BODY_BYTES) {
    throw new BodyTooLarge();
  }
  if (request.body === null) return undefined;

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_AUTH_BODY_BYTES) {
      await reader.cancel();
      throw new BodyTooLarge();
    }
    chunks.push(value);
  }
  if (total === 0) return undefined;
  const result = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result;
}

function blockedByCsrf(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  if (origin !== getPublicOrigin()) return true;
  return fetchSite !== null && fetchSite !== "same-origin" && fetchSite !== "none";
}

function safeResponseHeaders(upstream: Response): Headers {
  const result = new Headers({ "cache-control": "no-store" });
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value !== null) result.set(name, value);
  }
  return result;
}

async function proxy(request: NextRequest, context: RouteContext, method: "GET" | "POST") {
  const segments = (await context.params).path;
  const path = segments.join("/");
  const allowed = method === "GET" ? GET_PATHS : POST_PATHS;
  if (!allowed.has(path)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  if (method === "POST" && blockedByCsrf(request)) {
    return NextResponse.json(
      { detail: "Cross-site request blocked" },
      { status: 403, headers: { "cache-control": "no-store" } },
    );
  }

  const headers = new Headers();
  const cookie = request.headers.get("cookie");
  const contentType = request.headers.get("content-type");
  const userAgent = request.headers.get("user-agent");
  if (cookie) headers.set("cookie", cookie);
  if (contentType) headers.set("content-type", contentType);
  if (userAgent) headers.set("user-agent", userAgent);
  const proxySecret = process.env.AGENTOS_AUTH_PROXY_SECRET;
  if (proxySecret) {
    headers.set(PROXY_SECRET_HEADER, proxySecret);
    headers.set(CLIENT_IP_HEADER, requestClientIp(request));
  }

  try {
    const bytes = method === "POST" ? await readBody(request) : undefined;
    const upstream = await fetch(`${API_URL}/auth/${path}`, {
      method,
      cache: "no-store",
      headers,
      body: bytes && bytes.byteLength > 0 ? bytes : undefined,
    });
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: safeResponseHeaders(upstream),
    });
  } catch (error) {
    if (error instanceof BodyTooLarge) {
      return NextResponse.json(
        { detail: "Request body too large" },
        { status: 413, headers: { "cache-control": "no-store" } },
      );
    }
    return NextResponse.json(
      { detail: "Authentication service unavailable" },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }
}

export function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, context, "GET");
}

export function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, context, "POST");
}
