import {expect, test, type Page} from '@playwright/test';
import type {Product, RestaurantSettings} from '../src/types';

const product: Product = {
  id: 42, name: 'Poulet de test', category: 'Poulet', description: 'Une recette à personnaliser.',
  price: 12, image: 'stc-menu-1', available: true,
  optionGroups: [{id: 'sauce', name: 'Sauce', min: 0, max: 1, choices: [{id: 'douce', name: 'Sauce douce', price: 0}]}],
};
const restaurant: RestaurantSettings = {
  name: 'STC', address: '24 rue du Test', city: 'Paris', hours: '11h30 – 23h', days: 'Tous les jours',
  deliveryFee: 3.9, minDeliveryTotal: 15, deliveryPostalCodes: ['75011'], orderingEnabled: true,
  isOpen: true, demoMode: true, paymentMode: 'simulation',
};

async function openCatalogue(page: Page, state: {product: Product; fail: boolean}) {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/products/' && state.fail) {
      await route.fulfill({status: 503, json: {detail: 'Indisponible temporairement.'}});
      return;
    }
    const data = path === '/api/products/' ? [state.product]
      : path === '/api/restaurant/' ? restaurant
      : path === '/api/categories/' ? [{name: 'Poulet', position: 0}]
      : path === '/api/auth/me/' ? {user: null} : [];
    await route.fulfill({json: data});
  });
  await page.goto('/');
  await expect(page.locator('.product-card')).toHaveCount(1);
}

test('la carte ouverte reçoit prix, photo et disponibilité sans perdre la recherche ni les choix', async ({page}) => {
  const state = {product: {...product}, fail: false};
  await openCatalogue(page, state);
  const search = page.getByRole('textbox', {name: 'Rechercher un plat'});
  await search.fill('Poulet');
  await page.getByRole('group', {name: 'Catégories', exact: true}).getByRole('button', {name: 'Poulet', exact: true}).click();
  await page.locator('.product-card').getByRole('button', {name: 'Poulet de test', exact: true}).click();
  const dialog = page.getByRole('dialog', {name: 'Poulet de test', exact: true});
  await dialog.getByRole('radio').check();
  await dialog.getByRole('button', {name: 'Augmenter la quantité', exact: true}).click();

  state.product = {...product, price: 14.5, image: 'stc-menu-3', available: false};
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(dialog.getByRole('button', {name: /Ajouter · 29,00/})).toBeDisabled();
  await expect(dialog.locator('.detail-image')).toHaveAttribute('src', '/images/stc-menu-3.jpg');
  await expect(dialog.getByRole('radio')).toBeChecked();
  await expect(dialog.locator('.quantity span')).toHaveText('2');
  await page.keyboard.press('Escape');
  await expect(search).toHaveValue('Poulet');
  await expect(page.getByRole('group', {name: 'Catégories', exact: true}).getByRole('button', {name: 'Poulet', exact: true})).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.product-card .card-price')).toContainText('14,50');

  state.fail = true;
  const failed = page.waitForResponse(response => response.url().endsWith('/api/products/') && response.status() === 503);
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await failed;
  await expect(page.locator('.product-card')).toHaveCount(1);
  await expect(page.getByRole('heading', {name: 'La carte n’a pas pu être chargée.'})).toHaveCount(0);
  await expect(page.locator('.skeleton')).toHaveCount(0);

  state.fail = false;
  state.product = {...product, price: 15.5};
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(page.locator('.product-card .card-price')).toContainText('15,50');
  await expect(search).toHaveValue('Poulet');
});

test('une option supprimée pendant une fiche ouverte ne revient pas dans le panier', async ({page}) => {
  const state = {product: {...product}, fail: false};
  await openCatalogue(page, state);
  await page.locator('.product-card').getByRole('button', {name: 'Poulet de test', exact: true}).click();
  const dialog = page.getByRole('dialog', {name: 'Poulet de test', exact: true});
  await dialog.getByRole('radio').check();
  await dialog.getByRole('button', {name: 'Augmenter la quantité', exact: true}).click();
  state.product = {...product, optionGroups: []};
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect(dialog.getByRole('radio')).toHaveCount(0);
  await expect(dialog.locator('.quantity span')).toHaveText('2');
  await dialog.getByRole('button', {name: /Ajouter · 24,00/}).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole('button', {name: 'Mon panier, 2 articles', exact: true}).click();
  await expect(page.getByRole('dialog', {name: 'Mon panier', exact: true})).toBeVisible();
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('stc-cart-v2') || '[]'));
  expect(saved).toHaveLength(1);
  expect(saved[0].choices).toEqual([]);
  expect(saved[0].quantity).toBe(2);
  expect(saved[0].unitPrice).toBe(12);
});
