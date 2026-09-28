import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  timeout: 120000,
  workers: 1,
  use: {
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined },
    baseURL: "http://localhost:8097",
    viewport: { width: 1440, height: 1050 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  reporter: "list",
});
