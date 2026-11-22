import { expect, test } from "@playwright/test";
import { PASSWORD, loadDemo, registerAndOnboard } from "./helpers";

// The plan's happy path: register → onboard → check-in → chat → dashboard (+ what-if, export).
test("new user: onboard, check in, chat, dashboard, what-if, export", async ({ page }) => {
  await registerAndOnboard(page);

  await test.step("check-in: the day's first check-in is the full form", async () => {
    await expect(page.getByRole("tablist", { name: "Part of the day" })).toBeVisible();
    await expect(page.getByLabel("Sleep last night (hours)")).toBeVisible();
    await page.getByRole("group", { name: "Mood" }).getByRole("button", { name: "4" }).click();
    await page.getByRole("button", { name: "Save check-in" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  });

  await test.step("chat: the extraction card saves rows only after confirmation", async () => {
    await page.goto("/chat");
    const box = page.getByPlaceholder("How was today?", { exact: false });
    await box.fill("Studied 2h and went to lectures for 3 hours.");
    await box.press("Enter");
    await page.getByRole("button", { name: "Confirm & save" }).click();
    await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  });

  await test.step("dashboard: the learning state for a new twin", async () => {
    await page.goto("/dashboard");
    await expect(page.getByText("Your twin is learning")).toBeVisible();
  });

  await test.step("what-if is honest that there is nothing to simulate yet", async () => {
    await page.goto("/whatif");
    await expect(page.getByText("Nothing to simulate yet")).toBeVisible();
  });

  await test.step("export: the API answers with a JSON attachment (and a file downloads)", async () => {
    await page.goto("/settings");
    const res = page.waitForResponse((r) => r.url().endsWith("/privacy/export"));
    // Playwright can't receive downloads from the locally installed Edge (PW_CHANNEL);
    // the bundled Chromium used in CI can, so check the file there too.
    const download = process.env.PW_CHANNEL ? null : page.waitForEvent("download");
    await page.getByRole("button", { name: "Download my data" }).click();
    const r = await res;
    expect(r.status()).toBe(200);
    expect(r.headers()["content-disposition"]).toContain("attachment");
    if (download) expect((await download).suggestedFilename()).toMatch(/^twin-export-.*[.]json$/);
  });
});

test("demo twin: suggestions learn from 👎, what-if responds, delete removes the account", async ({
  page,
}) => {
  const email = await registerAndOnboard(page);

  await loadDemo(page, /Founder/, "60 days");

  // three suggestions with reasons; 👎 replaces one right away
  await page.goto("/dashboard");
  const card = page.locator("text=Suggestions for tomorrow").locator("xpath=ancestor::div[contains(@class,'rounded-lg')][1]");
  const items = card.getByRole("listitem");
  await expect(items).toHaveCount(3);
  const first = (await items.first().locator("p").first().innerText()).trim();
  await items.first().getByRole("button", { name: "Why?" }).click();
  await expect(items.first().getByText(/pattern|usually|average|goal|predicts/i).first()).toBeVisible();
  await items.first().getByRole("button", { name: "Not for me" }).click();
  await expect(card.getByText(first, { exact: true })).toHaveCount(0);
  await expect(items).toHaveCount(3);

  // what-if: moving a slider changes a learned prediction
  await page.goto("/whatif");
  const slider = page.getByRole("slider").first();
  await expect(slider).toBeVisible();
  const values = page.locator("span.text-\\[40px\\]");
  const before = await values.allInnerTexts();
  await slider.focus();
  for (let i = 0; i < 30; i++) await page.keyboard.press("ArrowRight");
  await expect.poll(async () => (await values.allInnerTexts()).join(","), { timeout: 15_000 }).not.toBe(before.join(","));
  await expect(page.getByText(/Updated in \d+ ms/)).toBeVisible();

  // delete twin: needs the email typed, then logs out and the login no longer works
  await page.goto("/settings");
  await page.getByLabel("Type your email to confirm").fill(email);
  await page.getByRole("button", { name: "Delete everything" }).click();
  await page.waitForURL("**/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText(/incorrect|invalid|wrong/i)).toBeVisible();
});
