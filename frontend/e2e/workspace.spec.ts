import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const env = Object.fromEntries(
  fs
    .readFileSync(path.resolve("../.env"), "utf8")
    .split("\n")
    .filter(Boolean)
    .map((l) => {
      const i = l.indexOf("=");
      return [l.slice(0, i), l.slice(i + 1)];
    }),
);

test("login, case intake, upload, investigate, inspect evidence, chat and approved report", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Email address").fill(env.CPE_ADMIN_EMAIL);
  await page
    .getByLabel("Password", { exact: true })
    .fill(env.CPE_ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your investigations" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Create new case", exact: true })
    .click();
  await page
    .getByLabel("Case title")
    .fill("Synthetic · storage dependency investigation");
  await page
    .getByLabel("Customer", { exact: true })
    .fill("Demonstration — no customer data");
  await page
    .getByLabel("Incident description")
    .fill(
      "Synthetic fixture: processor write errors correlate with storage no-space failures.",
    );
  await page
    .getByRole("button", { name: "Create case & add evidence" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Build your evidence set" }),
  ).toBeVisible();
  await page
    .getByLabel("NFS product logs", { exact: true })
    .setInputFiles("../samples/synthetic-incident.zip");
  await expect(page.getByText("Ready", { exact: true }).first()).toBeVisible({
    timeout: 45000,
  });
  await page
    .getByLabel("Import config", { exact: true })
    .setInputFiles("../samples/investigation-config.json");
  await page
    .getByRole("checkbox", { name: "demo.processor", exact: true })
    .check();
  await page
    .getByRole("button", { name: "Save configuration & selection" })
    .click();
  await expect(
    page.getByRole("button", { name: "Create investigation", exact: true }),
  ).toBeEnabled({ timeout: 15000 });
  await page
    .getByRole("button", { name: "Create investigation", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Storage write failed: no space left on device",
    }),
  ).toBeVisible({ timeout: 45000 });
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Pods & containers" }),
  ).toBeVisible();
  await expect(
    page.getByText("Synthetic demonstration", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("demo/storage:1.0", { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: "../docs/dashboard.png", fullPage: true });
  await page
    .getByRole("button", { name: "Investigation", exact: true })
    .click();
  await page
    .getByRole("button", { name: /nfs\/storage.log:1/ })
    .first()
    .click();
  await expect(
    page.getByText("SOURCE EVIDENCE", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close evidence" }).click();
  await page
    .getByLabel("Ask the assistant")
    .fill("What caused the storage failure?");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message.assistant").last()).toContainText(
    "Evidence:",
  );
  await page
    .getByRole("button", { name: "Approve findings & create report" })
    .click();
  const link = page.getByRole("link", { name: "Download approved HTML" });
  await expect(link).toBeVisible({ timeout: 15000 });
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    link.click(),
  ]);
  await download.saveAs("../docs/synthetic-approved-report.html");
  expect(
    fs.readFileSync("../docs/synthetic-approved-report.html", "utf8"),
  ).toContain("no space left");
  expect(errors).toEqual([]);
  await page.screenshot({ path: "../docs/investigation.png", fullPage: true });
});

test("mobile launcher is usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Email address").fill(env.CPE_ADMIN_EMAIL);
  await page
    .getByLabel("Password", { exact: true })
    .fill(env.CPE_ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Your investigations" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({ path: "../docs/mobile.png", fullPage: true });
});
