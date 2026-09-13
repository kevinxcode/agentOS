import { expect, test } from "@playwright/test";

const backend = "http://127.0.0.1:4101";

test.beforeEach(async ({ context, request }) => {
  await context.clearCookies();
  await request.post(`${backend}/__test/reset`, { data: { enrolled: true } });
});

async function enterPassword(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@example.com");
  await page.getByLabel("Password").fill("valid-password");
  await page.getByRole("button", { name: "Continue" }).click();
}

test("password and TOTP login reaches Mission Control and can log out", async ({ page }) => {
  await enterPassword(page);
  await page.getByLabel("Authentication code").fill("123456");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL("/login");
});

test("enrollment shows QR and manual key and gates recovery-code acknowledgement", async ({ page, request }) => {
  await request.post(`${backend}/__test/reset`, { data: { enrolled: false } });
  await enterPassword(page);
  await expect(page).toHaveURL("/enroll");
  await expect(page.getByRole("img", { name: /QR code/i })).toBeVisible();
  await expect(page.getByText("JBSW Y3DP EHPK 3PXP")).toBeVisible();
  await page.getByLabel("Authentication code").fill("123456");
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("ALPHA-ONE")).toBeVisible();
  const continueButton = page.getByRole("button", { name: "Continue to Mission Control" });
  await expect(continueButton).toBeDisabled();
  await page.getByLabel("I have saved these recovery codes").check();
  await expect(continueButton).toBeEnabled();
  await continueButton.click();
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
});

test("invalid TOTP is rejected without retaining the submitted code", async ({ page }) => {
  await enterPassword(page);
  const code = page.getByLabel("Authentication code");
  await code.fill("000000");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert", { name: "Authentication failed", exact: true })).toHaveText(
    "Authentication failed",
  );
  await expect(code).toHaveValue("");
});

test("a recovery code can complete the password-gated second factor", async ({ page }) => {
  await enterPassword(page);
  await page.getByRole("button", { name: "Use a recovery code" }).click();
  await page.getByLabel("Recovery code").fill("RECOVERY-ONE");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
});

test("an expired session returns to sign in", async ({ page, request }) => {
  await enterPassword(page);
  await page.getByLabel("Authentication code").fill("123456");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Mission Control" })).toBeVisible();
  await request.post(`${backend}/__test/expire`);
  await page.reload();
  await expect(page).toHaveURL("/login");
});

test("an anonymous visitor is redirected away from the protected dashboard", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL("/login");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
});
