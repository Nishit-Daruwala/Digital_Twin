import { defineConfig } from "@playwright/test";

/**
 * End-to-end tests against a running app (frontend on :3000, backend on :8000 with the fake
 * LLM). CI starts both servers; locally start them yourself, then `npm run e2e`.
 * PW_CHANNEL=msedge uses the installed Edge instead of a downloaded Chromium.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    channel: process.env.PW_CHANNEL || undefined,
    viewport: { width: 1366, height: 900 },
    acceptDownloads: !process.env.PW_CHANNEL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
