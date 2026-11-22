import { expect, type Page } from "@playwright/test";

export const PASSWORD = "password123";

export async function registerAndOnboard(page: Page) {
  const email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Name").fill("E2E Person");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/onboarding");
  await page.getByRole("button", { name: "Student", exact: true }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Less stress" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  for (const opt of ["Morning", "Mostly", "About right", "Mixed", "Workload"]) {
    await page.getByRole("button", { name: opt, exact: true }).click();
  }
  await page.getByRole("button", { name: "Create my twin" }).click();
  await page.waitForURL("**/checkin");
  return email;
}

/** Load a persona's synthetic history into the signed-in account (Settings → Demo data). */
export async function loadDemo(page: Page, persona: RegExp, days: string) {
  await page.goto("/settings");
  await page.getByRole("radio", { name: persona }).click();
  await page.getByRole("radio", { name: days }).click();
  await page.getByRole("button", { name: "Load demo data" }).click();
  await page.getByRole("button", { name: "Replace my data" }).click();
  await expect(page.getByText(/^Loaded/)).toBeVisible({ timeout: 150_000 });
}
