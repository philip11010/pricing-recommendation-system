import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a real API.
 *
 * Deliberately not mocked. What these tests are for is the agreement between
 * this application and the pricing API: the field names it sends, the shapes
 * it reads back, and the statuses it acts on. A mocked API agrees with
 * whatever the mock was written to say, which is the one thing that cannot go
 * wrong in production.
 *
 * So the API has to be running, with the demonstration mentors seeded. See
 * web/README.md for the four commands.
 */

const WEB_URL = process.env.E2E_WEB_URL ?? "http://127.0.0.1:3000";

export default defineConfig({
  testDir: "./e2e",
  // One worker: the tests write to the API's database, and two of them
  // answering prices for the same demonstration mentor at once would be
  // racing over which recommendation is the latest.
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  timeout: 90_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: WEB_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: WEB_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
