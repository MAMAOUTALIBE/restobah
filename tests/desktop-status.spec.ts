import {expect, test} from '@playwright/test';
import type {RestaurantSettings} from '../src/types';

const restaurant: RestaurantSettings = {
  name: 'STC', address: 'Adresse de recette', city: 'Paris', hours: '11h30 – 23h00', days: 'Tous les jours',
  deliveryFee: 3.9, minDeliveryTotal: 0, deliveryPostalCodes: ['75011'],
  orderingEnabled: true, isOpen: true, demoMode: true, paymentMode: 'simulation',
};

test('indicateur : horaires et pause manuelle donnent un statut cohérent sur ordinateur et mobile', async ({page}, info) => {
  let state = {isOpen: true, orderingEnabled: true};
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const data = path === '/api/restaurant/' ? {...restaurant, ...state}
      : path === '/api/auth/me/' ? {user: null} : [];
    await route.fulfill({json: data});
  });
  const desktopColors: {open: string; closed: string[]} = {open: '', closed: []};
  for (const width of [1440, 390]) {
    await page.setViewportSize({width, height: 900});
    for (const isOpen of [true, false]) {
      for (const orderingEnabled of [true, false]) {
        state = {isOpen, orderingEnabled};
        await page.goto('/');
        const indicator = page.locator('.open-status');
        const closed = !isOpen || !orderingEnabled;
        await expect(indicator).toHaveText(closed ? 'Commandes fermées' : 'Commandes ouvertes');
        if (closed) await expect(indicator).toHaveClass(/\bclosed\b/);
        else await expect(indicator).not.toHaveClass(/\bclosed\b/);
        if (width === 1440) {
          await expect(indicator).toBeVisible();
          const color = await indicator.locator('i').evaluate(node => getComputedStyle(node).backgroundColor);
          if (closed) desktopColors.closed.push(color);
          else desktopColors.open = color;
        } else await expect(indicator).toBeHidden();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        if (isOpen && !orderingEnabled) {
          await page.screenshot({path: info.outputPath(`pause-manuelle-${width}.png`), fullPage: false});
        }
      }
    }
  }
  expect(desktopColors.open).not.toBe('');
  expect(desktopColors.closed).toHaveLength(3);
  expect(new Set(desktopColors.closed).size).toBe(1);
  expect(desktopColors.closed.every(color => color !== desktopColors.open)).toBe(true);
});
