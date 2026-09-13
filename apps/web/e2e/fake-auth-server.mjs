import { createServer } from "node:http";

let enrolled = true;
let sequence = 0;
let sessions = new Map();

function body(request) {
  return new Promise((resolve) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      const value = Buffer.concat(chunks).toString("utf8");
      resolve(value ? JSON.parse(value) : {});
    });
  });
}

function cookie(request) {
  return /(?:^|;\s*)agentos_session=([^;]+)/.exec(request.headers.cookie ?? "")?.[1];
}

function response(reply, status, value, headers = {}) {
  const data = value === undefined ? "" : JSON.stringify(value);
  reply.writeHead(status, {
    "cache-control": "no-store",
    ...(data ? { "content-type": "application/json" } : {}),
    ...headers,
  });
  reply.end(data);
}

function issue(stage) {
  const token = `browser-fixture-${++sequence}`;
  sessions.set(token, stage);
  return token;
}

function sessionCookie(token) {
  return `agentos_session=${token}; HttpOnly; SameSite=Strict; Path=/`;
}

const server = createServer(async (request, reply) => {
  const url = new URL(request.url ?? "/", "http://127.0.0.1:4101");
  const payload = request.method === "POST" ? await body(request) : {};

  if (url.pathname === "/__test/reset") {
    enrolled = payload.enrolled !== false;
    sequence = 0;
    sessions = new Map();
    return response(reply, 204);
  }
  if (url.pathname === "/__test/expire") {
    sessions = new Map();
    return response(reply, 204);
  }

  const token = cookie(request);
  const stage = token ? sessions.get(token) : undefined;
  if (url.pathname === "/auth/state" && request.method === "GET") {
    if (stage === "full") {
      return response(reply, 200, { stage: "full", id: "00000000-0000-0000-0000-000000000001", email: "admin@example.com", totp_enabled: true });
    }
    if (stage === "preauth") {
      return response(reply, 200, { stage: "preauth", next: enrolled ? "totp_verification" : "totp_enrollment" });
    }
    return response(reply, 200, { stage: "anonymous" });
  }
  if (url.pathname === "/auth/login" && request.method === "POST") {
    if (payload.email !== "admin@example.com" || payload.password !== "valid-password") {
      return response(reply, 401, { detail: "Authentication required or credentials invalid" });
    }
    const nextToken = issue("preauth");
    return response(
      reply,
      200,
      { next: enrolled ? "totp_verification" : "totp_enrollment" },
      { "set-cookie": sessionCookie(nextToken) },
    );
  }
  if (url.pathname === "/auth/me" && request.method === "GET") {
    return stage === "full"
      ? response(reply, 200, { id: "00000000-0000-0000-0000-000000000001", email: "admin@example.com", totp_enabled: true })
      : response(reply, 401, { detail: "Authentication required or credentials invalid" });
  }
  if (url.pathname === "/auth/totp/enroll" && request.method === "POST") {
    if (stage !== "preauth") return response(reply, 401, { detail: "Authentication required or credentials invalid" });
    if (enrolled) return response(reply, 409, { detail: "TOTP is already enrolled" });
    return response(reply, 200, {
      otpauth_uri: "otpauth://totp/AgentOS%3Aadmin%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=AgentOS",
    });
  }
  if (url.pathname === "/auth/totp/confirm" && request.method === "POST") {
    if (stage !== "preauth" || enrolled || payload.code !== "123456") {
      return response(reply, 401, { detail: "Authentication required or credentials invalid" });
    }
    sessions.delete(token);
    enrolled = true;
    const nextToken = issue("full");
    return response(
      reply,
      200,
      { recovery_codes: ["ALPHA-ONE", "BRAVO-TWO"] },
      { "set-cookie": sessionCookie(nextToken) },
    );
  }
  if (url.pathname === "/auth/totp/verify" && request.method === "POST") {
    if (stage !== "preauth" || !enrolled || payload.code !== "123456") {
      return response(reply, 401, { detail: "Authentication required or credentials invalid" });
    }
    sessions.delete(token);
    const nextToken = issue("full");
    return response(reply, 200, { authenticated: true }, { "set-cookie": sessionCookie(nextToken) });
  }
  if (url.pathname === "/auth/recovery" && request.method === "POST") {
    if (stage !== "preauth" || payload.code !== "RECOVERY-ONE") {
      return response(reply, 401, { detail: "Authentication required or credentials invalid" });
    }
    sessions.delete(token);
    const nextToken = issue("full");
    return response(reply, 200, { authenticated: true }, { "set-cookie": sessionCookie(nextToken) });
  }
  if (url.pathname === "/auth/logout" && request.method === "POST") {
    if (token) sessions.delete(token);
    return response(reply, 204, undefined, {
      "set-cookie": "agentos_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0",
    });
  }
  return response(reply, 404, { detail: "Not found" });
});

server.listen(4101, "127.0.0.1");
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
