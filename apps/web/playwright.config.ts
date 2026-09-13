import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:3100",
    ...devices["Desktop Chrome"],
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  webServer: [
    {
      command: "node e2e/fake-auth-server.mjs",
      port: 4101,
      reuseExistingServer: false,
    },
    {
      command: "next dev -H 127.0.0.1 -p 3100",
      url: "http://127.0.0.1:3100/login",
      reuseExistingServer: false,
      env: {
        AGENTOS_API_URL: "http://127.0.0.1:4101",
        AGENTOS_PUBLIC_ORIGIN: "http://127.0.0.1:3100",
      },
    },
  ],
});
