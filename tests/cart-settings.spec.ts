import {expect, test, type Page, type Route} from '@playwright/test';
import type {Product, RestaurantSettings} from '../src/types';

const product: Product = {id: 42, name: 'Poulet de test', category: 'Poulet', description: 'Recette de test.', price: 12, image: 'stc-menu-1', available: true, optionGroups: []};
const restaurant: RestaurantSettings = {
  name: 'STC', address: '24 rue du Test', city: 'Paris', hours: '11h30 – 23h', days: 'Tous les jours',
  deliveryFee: 3.9, minDeliveryTotal: 0, deliveryPostalCodes: ['75011'], orderingEnabled: true,
  pickupEnabled: true, deliveryEnabled: true, isOpen: true, demoMode: true, paymentMode: 'simulation',
  pickupDelay: '15–20 min', deliveryDelay: '30–40 min',
};

async function openCheckout(page: Page) {
  const state = {
    product: {...product}, restaurant: {...restaurant}, restaurantReads: 0, orderWrites: 0,
    holdNext: false, held: null as {route: Route; snapshot: RestaurantSettings} | null,
  };
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/orders/' && request.method() === 'POST') {
      state.orderWrites++;
      await route.fulfill({status: 503, json: {detail: 'Aucune écriture métier autorisée dans cette recette.'}});
      return;
    }
    if (path === '/api/restaurant/') {
      state.restaurantReads++;
      if (state.holdNext) {
        state.holdNext = false;
        state.held = {route, snapshot: {...state.restaurant}};
        return;
      }
    }
    const data = path === '/api/products/' ? [state.product]
      : path === '/api/restaurant/' ? state.restaurant
      : path === '/api/categories/' ? [{name: 'Poulet', position: 0}]
      : path === '/api/auth/me/' ? {user: null}
      : path === '/api/auth/csrf/' ? {detail: 'ok'} : [];
    await route.fulfill({json: data, ...(path === '/api/auth/csrf/' ? {headers: {'Set-Cookie': 'csrftoken=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; Path=/; SameSite=Lax'}} : {})});
  });
  await page.goto('/');
  await page.locator('.product-card').getByRole('button', {name: product.name, exact: true}).click();
  const detail = page.getByRole('dialog', {name: product.name, exact: true});
  await detail.getByRole('button', {name: 'Augmenter la quantité', exact: true}).click();
  await detail.getByRole('button', {name: /Ajouter ·/}).click();
  await page.getByRole('button', {name: 'Mon panier, 2 articles', exact: true}).click();
  const cart = page.getByRole('dialog', {name: 'Mon panier', exact: true});
  await cart.getByRole('button', {name: 'Livraison', exact: true}).click();
  await cart.getByRole('button', {name: /Passer commande/}).click();
  await cart.getByLabel('Nom complet', {exact: true}).fill('Client Audit');
  await cart.getByLabel('Adresse e-mail', {exact: true}).fill('audit@example.com');
  await cart.getByLabel('Téléphone', {exact: true}).fill('0612345678');
  await cart.getByLabel('Adresse de livraison', {exact: true}).fill('24 rue du Test');
  await cart.getByLabel('Code postal', {exact: true}).fill('75011');
  await cart.getByLabel('Ville', {exact: true}).fill('Paris');
  const confirm = cart.getByRole('button', {name: 'Valider la commande de démonstration', exact: true});
  // First prevalidation rejects a changed price; the checkout must remain mounted.
  state.product = {...state.product, price: 13};
  await confirm.click();
  await expect(cart.getByRole('alert')).toContainText('La carte ou les tarifs ont changé');
  await expect(cart.locator('.total')).toContainText('29,90');
  return {state, cart, confirm};
}

async function refresh(page: Page) {
  const received = page.waitForResponse(response => new URL(response.url()).pathname === '/api/restaurant/');
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await received;
}

test('le panier déjà contrôlé suit les frais, la pause et la réouverture sans perdre la saisie', async ({page}) => {
  const {state, cart, confirm} = await openCheckout(page);
  state.restaurant = {...state.restaurant, deliveryFee: 8.9, orderingEnabled: false};
  await refresh(page);
  await expect(cart.getByText('Le restaurant ne prend pas de commandes pour le moment.', {exact: true})).toBeVisible();
  await expect(confirm).toBeDisabled();
  await expect(cart.locator('.total')).toContainText('34,90');

  state.restaurant = {...state.restaurant, deliveryFee: 5.4, orderingEnabled: true, deliveryDelay: '45–50 min'};
  await refresh(page);
  await expect(confirm).toBeEnabled();
  await expect(cart.locator('.total')).toContainText('31,40');
  await expect(cart.locator('.delivery-note')).toContainText('45–50 min');
  await expect(cart.getByLabel('Nom complet', {exact: true})).toHaveValue('Client Audit');
  await expect(cart.getByLabel('Code postal', {exact: true})).toHaveValue('75011');
  await expect(cart.locator('.quantity span')).toHaveText('2');
  expect(state.orderWrites).toBe(0);
});

test('le panier déjà contrôlé reçoit modes, zone, minimum et délais actualisés', async ({page}) => {
  const {state, cart, confirm} = await openCheckout(page);
  state.restaurant = {...state.restaurant, deliveryEnabled: false, pickupDelay: '8–10 min'};
  await refresh(page);
  await expect(cart.getByRole('button', {name: 'Livraison', exact: true})).toBeDisabled();
  await cart.getByRole('button', {name: 'À emporter', exact: true}).click();
  await expect(cart.locator('.delivery-note')).toContainText('8–10 min');

  state.restaurant = {...state.restaurant, deliveryEnabled: true, pickupEnabled: false, deliveryPostalCodes: ['75012'], deliveryDelay: '55–60 min'};
  await refresh(page);
  await expect(cart.getByRole('button', {name: 'À emporter', exact: true})).toBeDisabled();
  await cart.getByRole('button', {name: 'Livraison', exact: true}).click();
  await expect(cart.locator('.delivery-note')).toContainText('55–60 min');
  await expect(cart.locator('.delivery-note')).toContainText('75012');
  await confirm.click();
  await expect(cart.getByRole('alert')).toContainText('hors de notre zone de livraison');

  state.restaurant = {...state.restaurant, deliveryPostalCodes: ['75011'], minDeliveryTotal: 40};
  await refresh(page);
  await confirm.click();
  await expect(cart.getByRole('alert')).toContainText('Le minimum de commande en livraison est de 40,00');
  await expect(cart.getByLabel('Adresse e-mail', {exact: true})).toHaveValue('audit@example.com');
  expect(state.orderWrites).toBe(0);
});

test('une lecture des réglages en échec conserve le brouillon et permet une reprise sans commande', async ({page}) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const {state, cart, confirm} = await openCheckout(page);
  const unavailable = async (route: Route) => route.fulfill({
    status: 503, json: {detail: 'Lecture des réglages indisponible, refus de recette prévu.'},
  });
  await page.route('**/api/restaurant/', unavailable);
  await confirm.click();
  await expect(cart.getByRole('alert')).toHaveText('Lecture des réglages indisponible, refus de recette prévu.');
  await expect(confirm).toBeEnabled();
  await expect(cart.getByLabel('Nom complet', {exact: true})).toHaveValue('Client Audit');
  await expect(cart.getByLabel('Code postal', {exact: true})).toHaveValue('75011');
  await expect(cart.locator('.quantity span')).toHaveText('2');
  await expect(cart.locator('.total')).toContainText('29,90');
  expect(state.orderWrites).toBe(0);

  // A fresh successful read must be possible after the rejected promise. The
  // restaurant is now paused, so this retry also remains free of order writes.
  state.restaurant = {...state.restaurant, orderingEnabled: false};
  await page.unroute('**/api/restaurant/', unavailable);
  await confirm.click();
  await expect(cart.getByText('Le restaurant ne prend pas de commandes pour le moment.', {exact: true})).toBeVisible();
  await expect(confirm).toBeDisabled();
  await expect(cart.getByLabel('Nom complet', {exact: true})).toHaveValue('Client Audit');
  expect(state.orderWrites).toBe(0);
  expect(errors).toEqual([]);
});

test('une confirmation attend le polling lent puis relit les réglages avant toute création', async ({page}) => {
  const {state, cart, confirm} = await openCheckout(page);
  state.holdNext = true;
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await expect.poll(() => state.held !== null).toBe(true);
  const readsWhilePolling = state.restaurantReads;
  state.restaurant = {...state.restaurant, deliveryFee: 8.9, orderingEnabled: false};
  await confirm.click();
  await expect(cart.getByRole('button', {name: 'Validation en cours…', exact: true})).toBeDisabled();
  // The confirmation must not share the old snapshot as its final authority.
  // A new read follows it, so a late polling response cannot replace the fresh result.
  const held = state.held!;
  await held.route.fulfill({json: held.snapshot});
  await expect.poll(() => state.restaurantReads).toBeGreaterThan(readsWhilePolling);
  await expect(cart.getByText('Le restaurant ne prend pas de commandes pour le moment.', {exact: true})).toBeVisible();
  await expect(confirm).toBeDisabled();
  await expect(cart.locator('.total')).toContainText('34,90');
  await expect(cart.getByLabel('Nom complet', {exact: true})).toHaveValue('Client Audit');
  expect(state.orderWrites).toBe(0);
});
