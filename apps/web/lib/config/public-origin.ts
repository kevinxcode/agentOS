const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

function canonicalHost(rawHost: string): string {
  const host = rawHost.toLowerCase();
  if (host.startsWith("[")) {
    if (host !== "[::1]") throw new Error("invalid");
    return host;
  }
  if (/^[0-9.]+$/.test(host)) {
    const parts = host.split(".");
    if (
      parts.length !== 4 ||
      parts.some(
        (part) =>
          !/^\d+$/.test(part) ||
          (part.length > 1 && part.startsWith("0")) ||
          Number(part) > 255,
      )
    ) {
      throw new Error("invalid");
    }
    return host;
  }
  if (host !== "localhost") {
    const labels = host.split(".");
    if (
      labels.length < 2 ||
      host.length > 253 ||
      /^\d+$/.test(labels.at(-1) ?? "") ||
      labels.some(
        (label) =>
          label.length > 63 || !/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label),
      )
    ) {
      throw new Error("invalid");
    }
  }
  return host;
}

export function parsePublicOrigin(
  value: string | undefined,
  environment = process.env.NODE_ENV,
): string {
  if (!value) {
    if (environment === "production") {
      throw new Error("AGENTOS_PUBLIC_ORIGIN is required in production");
    }
    return "http://localhost:3000";
  }
  try {
    const match = value.match(
      /^(https|http):\/\/(\[[0-9a-f:]+\]|[a-z0-9.-]+)(?::([0-9]{1,5}))?\/?$/i,
    );
    if (!match) throw new Error("invalid");
    const [, rawScheme, rawHost, rawPort] = match;
    const scheme = rawScheme.toLowerCase();
    const host = canonicalHost(rawHost);
    if (scheme === "http" && !LOOPBACK_HOSTS.has(host)) throw new Error("invalid");
    const port = rawPort === undefined ? undefined : Number(rawPort);
    if (port !== undefined && (port < 1 || port > 65535)) throw new Error("invalid");
    const defaultPort = scheme === "https" ? 443 : 80;
    return `${scheme}://${host}${port !== undefined && port !== defaultPort ? `:${port}` : ""}`;
  } catch {
    throw new Error("AGENTOS_PUBLIC_ORIGIN must be a single canonical HTTP(S) public origin");
  }
}

export function getPublicOrigin(): string {
  return parsePublicOrigin(process.env.AGENTOS_PUBLIC_ORIGIN);
}
