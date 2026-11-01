import {expect, test} from '@playwright/test';

test('les grandes catégories mobiles gardent cinq choix visibles et les suivants accessibles au clavier', async ({page}) => {
  await page.goto('/');
  const rail = page.locator('.categories');
  const categories = rail.getByRole('button');
  await expect(categories).toHaveCount(7);
  const mobile = (page.viewportSize()?.width ?? 1280) <= 760;
  const visible = await rail.evaluate(el => {
    const rect = el.getBoundingClientRect();
    return Array.from(el.querySelectorAll('button')).filter(button => {
      const target = button.getBoundingClientRect();
      return target.left >= rect.left - 1 && target.right <= rect.right + 1;
    }).map(button => button.textContent?.trim());
  });
  expect(visible).toEqual(mobile
    ? ['Tout', 'Menus', 'Burgers', 'Poulet', 'Boissons']
    : ['Tout', 'Menus', 'Burgers', 'Poulet', 'Accompagnements', 'Boissons', 'Desserts']);
  if (mobile) {
    const circles = await rail.locator('.category-image').evaluateAll(els => els.map(el => el.getBoundingClientRect().width));
    expect(circles.every(width => width >= 44)).toBe(true);
  }

  const all = rail.getByRole('button', {name: 'Tout', exact: true});
  await all.focus();
  for (let index = 0; index < 6; index++) await page.keyboard.press('Tab');
  const desserts = rail.getByRole('button', {name: 'Desserts', exact: true});
  await expect(desserts).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(desserts).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.product-card')).toHaveCount(1);
  await expect(page.locator('.product-grid').getByRole('heading', {name: 'Le Cookie Choco', exact: true})).toBeVisible();
  if (mobile) expect(await rail.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);

  const verticalPosition = await page.evaluate(() => scrollY);
  await all.click();
  await expect(all).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => rail.evaluate(el => el.scrollLeft)).toBe(0);
  expect(await page.evaluate(() => scrollY)).toBeCloseTo(verticalPosition, 0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
