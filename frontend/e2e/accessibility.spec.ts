import { appendFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { loadDemo, registerAndOnboard } from "./helpers";

// Automated WCAG 2.1 A/AA scan (axe-core) of every page, with real data on screen.
// Serious and critical violations fail the test; minor ones are printed for review.
async function scan(page: Page, name: string) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(400); // let fade-in animations settle (contrast is measured)
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  for (const v of violations) {
    console.log(`[${name}] ${v.impact} ${v.id}: ${v.help}`);
    for (const n of v.nodes.slice(0, 5)) console.log(`    ${n.target.join(" ")}: ${n.any[0]?.message ?? ""}`);
  }
  await test.info().attach(`axe ${name}`, {
    body: JSON.stringify(violations, null, 2),
    contentType: "application/json",
  });
  if (process.env.AXE_DUMP) {
    const lines = violations.flatMap((v) =>
      v.nodes.map((n) => `${name}\t${v.id}\t${n.target.join(" ")}\t${n.any[0]?.message ?? ""}\t${n.html.slice(0, 140)}`),
    );
    appendFileSync(process.env.AXE_DUMP, lines.join("\n") + "\n");
  }
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect.soft(blocking.map((v) => `${v.id} (${v.nodes.length})`), `${name}: serious/critical issues`).toEqual([]);
}

test("public pages pass an axe scan", async ({ page }) => {
  for (const path of ["/login", "/register", "/reminders/off?token=expired-or-invalid-token"]) {
    await page.goto(path);
    await scan(page, path);
  }
});

test("every app page passes an axe scan with demo data", async ({ page }) => {
  await registerAndOnboard(page);
  await loadDemo(page, /Student/, "60 days");
  for (const path of ["/dashboard", "/checkin", "/log", "/chat", "/decisions", "/whatif", "/settings"]) {
    await test.step(path, async () => {
      await page.goto(path);
      await scan(page, path);
      await expect(page).toHaveTitle(/· Twin$/);
    });
  }
  // keyboard: the first Tab lands on the skip link, which moves focus to the content
  await page.goto("/dashboard");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
});
