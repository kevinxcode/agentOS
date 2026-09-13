// Real production Compose browser gate, deliberately excluded from fake-server tests.
import { chromium } from "@playwright/test";
import { createHmac } from "node:crypto";

function totp(secret) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits = [...secret.replaceAll(" ", "")].map((char) => alphabet.indexOf(char).toString(2).padStart(5, "0")).join("");
  const key = Buffer.from(bits.match(/.{8}/g).map((byte) => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const hash = createHmac("sha1", key).update(counter).digest();
  return String((hash.readUInt32BE(hash[19] & 15) & 0x7fffffff) % 1000000).padStart(6, "0");
}

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  const origin = process.env.AGENTOS_PUBLIC_ORIGIN;
  if (!/^http:\/\/(?:localhost|127\.0\.0\.1):\d+$/.test(origin ?? "")) throw new Error("Disposable loopback origin required");
  await page.goto(origin);
  await page.waitForURL(`${origin}/login`);
  await page.getByLabel("Email", { exact: true }).fill("admin@example.com");
  await page.getByLabel("Password", { exact: true }).fill("acceptance-password");
  await page.getByRole("button", { name: "Continue", exact: true }).click();
  await page.waitForURL(`${origin}/enroll`);
  const preauth = await page.request.get(`${origin}/api/auth/me`);
  if (preauth.status() !== 401) throw new Error("Pre-auth privilege leak");
  await page.locator(".manual-key").waitFor();
  await page.getByLabel("Authentication code").fill(totp(await page.locator(".manual-key").innerText()));
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await page.getByRole("heading", { name: "Save your recovery codes" }).waitFor();
  if (await page.locator(".recovery-codes li").count() !== 10) throw new Error("Missing recovery codes");
  const button = page.getByRole("button", { name: "Continue to Mission Control" });
  if (await button.isEnabled()) throw new Error("Missing acknowledgement gate");
  await page.getByLabel("I have saved these recovery codes").check();
  await button.click();
  await page.getByRole("heading", { name: "Mission Control", exact: true }).waitFor();
  await page.goto(`${origin}/audit`);
  await page.getByRole("heading", { name: "Audit", exact: true }).waitFor();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.waitForURL(`${origin}/login`);
  await page.goto(origin);
  await page.waitForURL(`${origin}/login`);
  console.log("Real Compose browser enrollment, dashboard, audit and logout passed");
} finally {
  await browser.close();
}
