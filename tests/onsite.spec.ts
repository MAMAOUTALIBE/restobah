import {expect, test, type BrowserContext, type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import type {Order, OrderPayload, Product, RestaurantSettings} from '../src/types';

const product: Product = {id: 42, name: 'Poulet de recette', category: 'Poulet', description: 'Recette de validation.', price: 12, image: 'stc-menu-1', available: true, optionGroups: []};
const settings: RestaurantSettings = {
  name: 'STC', address: '24 rue du Test', city: 'Paris', hours: 'Tous les jours', days: 'Tous les jours',
  deliveryFee: 3.9, minDeliveryTotal: 0, deliveryPostalCodes: ['75011'], orderingEnabled: true,
  pickupEnabled: true, deliveryEnabled: true, isOpen: true, demoMode: false, paymentMode: 'on_site',
};
function fixtureOrder(mode: OrderPayload['mode'] = 'À emporter'): Order {
  const date = new Date().toISOString();
  const fee = mode === 'Livraison' ? 3.9 : 0;
  return {id: 'STC-ONSITE-FIXTURE', date, total: 12 + fee, subtotal: 12, deliveryFee: fee, mode,
    items: ['1 × Poulet de recette'], status: 'confirmed', paymentMethod: 'on_site', paymentStatus: 'due',
    accessToken: 'fixture-not-a-real-order', demoMode: false,
    lines: [{name: product.name, quantity: 1, unitPrice: 12, total: 12, choices: []}], history: [{status: 'confirmed', date}]};
}
async function mockedRestaurant(page: Page) {
  const state = {settings: {...settings}, order: fixtureOrder(), payloads: [] as OrderPayload[], keys: [] as string[], failed: false, paymentCalls: 0};
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/payment/')) {state.paymentCalls++; await route.fulfill({status: 400, json: {detail: 'Aucun paiement en ligne attendu.'}}); return;}
    if (path === '/api/orders/' && request.method() === 'POST') {
      const payload = request.postDataJSON() as OrderPayload;
      state.payloads.push(payload); state.keys.push(request.headers()['idempotency-key']);
      if (state.failed) {state.failed = false; await route.fulfill({status: 503, json: {detail: 'Connexion interrompue. Réessayez.'}}); return;}
      state.order = fixtureOrder(payload.mode);
      await route.fulfill({status: 201, json: state.order}); return;
    }
    const data = path === '/api/products/' ? [product] : path === '/api/restaurant/' ? state.settings
      : path === '/api/categories/' ? [{name: 'Poulet', position: 0}] : path === '/api/auth/me/' ? {user: null}
      : path === '/api/auth/csrf/' ? {detail: 'ok'} : path.startsWith('/api/orders/') ? state.order : [];
    await route.fulfill({json: data, ...(path === '/api/auth/csrf/' ? {headers: {'Set-Cookie': 'csrftoken=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; Path=/; SameSite=Lax'}} : {})});
  });
  return state;
}
async function fillCustomer(page: Page, email = 'onsite@example.com') {
  await page.getByLabel('Nom complet', {exact: true}).fill('Client Recette');
  await page.getByLabel('Adresse e-mail', {exact: true}).fill(email);
  await page.getByLabel('Téléphone', {exact: true}).fill('0612345678');
}

for (const mode of ['À emporter', 'Livraison'] as const) {
  test(`sur place avec fixtures : ${mode}, engagement explicite et reprise sans doublon`, async ({page}) => {
    const state = await mockedRestaurant(page);
    state.failed = true;
    await page.goto('/');
    await page.locator('.product-card').getByRole('button', {name: product.name, exact: true}).click();
    const details = page.getByRole('dialog', {name: product.name, exact: true});
    await details.getByRole('button', {name: /Ajouter ·/}).click();
    // Open the basket while the product remains underneath; success must close both.
    await page.locator('.product-card').getByRole('button', {name: product.name, exact: true}).click();
    await page.getByRole('button', {name: 'Voir le panier', exact: true}).click();
    await expect(page.locator('[role="dialog"]')).toHaveCount(2);
    const cart = page.getByRole('dialog', {name: 'Mon panier', exact: true});
    await cart.getByRole('button', {name: mode, exact: true}).click();
    await cart.getByRole('button', {name: /Passer commande/}).click();
    await fillCustomer(page);
    if (mode === 'Livraison') {
      await cart.getByLabel('Adresse de livraison', {exact: true}).fill('24 rue du Test');
      await cart.getByLabel('Code postal', {exact: true}).fill('75011');
      await cart.getByLabel('Ville', {exact: true}).fill('Paris');
    }
    const place = mode === 'Livraison' ? 'à la livraison' : 'au restaurant';
    const submit = cart.getByRole('button', {name: `Commander et régler ${place}`, exact: true});
    await expect(cart.locator('.simulation')).toContainText(`sera à régler ${place}`);
    await expect(cart.locator('.simulation')).toContainText(mode === 'Livraison' ? '15,90' : '12,00');
    await expect(cart).not.toContainText('Paiement simulé');
    await expect(cart).not.toContainText('Stripe');
    await expect(cart).not.toContainText('Aucun repas ne sera préparé');
    await submit.click();
    await expect(cart.getByRole('alert')).toHaveText('Connexion interrompue. Réessayez.');
    await expect(cart.getByLabel('Nom complet', {exact: true})).toHaveValue('Client Recette');
    await submit.click();
    await expect(page.getByRole('heading', {name: `Commande ${state.order.id}`, exact: true})).toBeVisible();
    await expect(page.locator('[role="dialog"]')).toHaveCount(0);
    await expect(page.locator('.payment-note')).toHaveText(`À régler ${place}`);
    expect(state.payloads).toHaveLength(2);
    expect(state.payloads.every(payload => payload.paymentMethod === 'on_site')).toBe(true);
    expect(state.keys[0]).toBeTruthy(); expect(state.keys[1]).toBe(state.keys[0]);
    expect(state.paymentCalls).toBe(0);
    expect(await page.evaluate(() => sessionStorage.getItem('stc-checkout-key'))).toBeNull();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('sur place avec fixtures : un changement de mode exige une nouvelle confirmation puis le suivi distingue les règlements', async ({page}) => {
  const state = await mockedRestaurant(page);
  state.settings = {...state.settings, paymentMode: 'simulation', demoMode: true};
  await page.goto('/');
  await page.locator('.product-card').getByRole('button', {name: product.name, exact: true}).click();
  await page.getByRole('dialog').getByRole('button', {name: /Ajouter ·/}).click();
  await page.getByRole('button', {name: 'Voir le panier', exact: true}).click();
  const cart = page.getByRole('dialog', {name: 'Mon panier', exact: true});
  await cart.getByRole('button', {name: /Passer commande/}).click();
  await fillCustomer(page);
  state.settings = {...settings};
  await cart.getByRole('button', {name: 'Valider la commande de démonstration', exact: true}).click();
  await expect(cart.getByRole('alert')).toContainText('Le mode de paiement a changé');
  expect(state.payloads).toHaveLength(0);
  await cart.getByRole('button', {name: 'Commander et régler au restaurant', exact: true}).click();
  await expect(page.locator('.payment-note')).toHaveText('À régler au restaurant');
  for (const [status, label] of [['paid', 'Réglé sur place'], ['refunded', 'Remboursé sur place'], ['cancelled', 'Règlement annulé']] as const) {
    state.order = {...state.order, paymentStatus: status};
    await page.getByRole('button', {name: 'Actualiser', exact: true}).click();
    await expect(page.locator('.payment-note')).toHaveText(label);
    await expect(page.getByRole('button', {name: /paiement test/})).toHaveCount(0);
  }
  // An inconsistent API response must still never offer Stripe for an on-site origin.
  state.order = {...state.order, paymentStatus: 'pending'};
  await page.getByRole('button', {name: 'Actualiser', exact: true}).click();
  await expect(page.getByRole('button', {name: /paiement test/})).toHaveCount(0);
  expect(state.paymentCalls).toBe(0);
  await page.getByRole('contentinfo').getByRole('button', {name: 'Questions fréquentes', exact: true}).click();
  await expect(page.getByRole('dialog')).toContainText('Votre commande vous engage à régler le total affiché.');
});

const isolatedOnSite = process.env.STC_RUNTIME_DIR?.includes('stc-e2e-') && process.env.STC_PAYMENT_MODE === 'on_site' && process.env.STC_DEMO_MODE === '0';
async function csrf(context: BrowserContext) {
  const value = (await context.cookies()).find(cookie => cookie.name === 'csrftoken')?.value;
  if (!value) throw new Error('Protection CSRF de recette absente.');
  return value;
}
async function manager(page: Page) {
  const content = readFileSync(join(process.env.STC_RUNTIME_DIR!, 'admin-credentials.txt'), 'utf8');
  const email = content.match(/^E-mail\s*:\s*(.+)$/m)?.[1]?.trim();
  const password = content.match(/^Mot de passe\s*:\s*(.+)$/m)?.[1]?.trim();
  if (!email || !password) throw new Error('Accès de recette isolée absents.');
  await page.goto('/crm/connexion/');
  await page.locator('[name="username"]').fill(email);
  await page.locator('[name="password"]').fill(password);
  await page.getByRole('button', {name: 'Se connecter', exact: true}).click();
  await expect(page).toHaveURL(/\/crm\/$/);
  await page.goto('/crm/restaurant/');
  // Two contiguous periods cover every minute, including midnight, in every timezone.
  while (await page.locator('[data-hours-row]').count() < 14) await page.getByRole('button', {name: 'Ajouter un créneau', exact: true}).click();
  for (let index = 0; index < 14; index++) {
    await page.locator(`[name="hours-${index}-weekday"]`).selectOption(String(Math.floor(index / 2)));
    await page.locator(`[name="hours-${index}-opens"]`).fill(index % 2 ? '12:00' : '00:00');
    await page.locator(`[name="hours-${index}-closes"]`).fill(index % 2 ? '00:00' : '12:00');
  }
  await page.getByRole('button', {name: 'Enregistrer les changements', exact: true}).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect((await (await page.request.get('/api/restaurant/')).json()).isOpen).toBe(true);
}
async function refreshClient(page: Page, label: string) {
  await page.getByRole('button', {name: 'Actualiser', exact: true}).click();
  await expect(page.locator('.payment-note')).toHaveText(label);
}

test.describe('commandes réelles sur la base jetable', () => {
  test.skip(!isolatedOnSite, 'Recette réelle réservée à STC_E2E_PAYMENT_MODE=on_site STC_E2E_DEMO_MODE=0 via scripts/e2e.py.');
  test.describe.configure({mode: 'serial'});

  test('invité : options et total exacts, réponse perdue, encaissement, service et remboursement complet', async ({page, browser}) => {
    test.setTimeout(120_000);
    page.setDefaultTimeout(15_000);
    await manager(page);
    const baseURL = process.env.E2E_BASE_URL!;
    const guest = await browser.newContext({baseURL, viewport: page.viewportSize()!, extraHTTPHeaders: {Origin: baseURL}});
    const client = await guest.newPage();
    client.setDefaultTimeout(15_000);
    const errors: string[] = []; client.on('pageerror', error => errors.push(error.message));
    try {
      await client.goto('/');
      await client.getByRole('button', {name: 'Ajouter Le Bucket STC', exact: true}).click();
      const details = client.getByRole('dialog', {name: 'Le Bucket STC', exact: true});
      await details.getByRole('radio', {name: /^Sauce maison/}).check();
      await details.getByRole('checkbox', {name: /Cheddar supplémentaire/}).check();
      await details.getByRole('button', {name: 'Augmenter la quantité', exact: true}).click();
      await details.getByRole('button', {name: /Ajouter · 26,80/}).click();
      await client.getByRole('button', {name: 'Voir le panier', exact: true}).click();
      await client.getByRole('button', {name: 'Passer commande', exact: true}).click();
      await fillCustomer(client, `invited-${randomUUID()}@example.com`);
      const keys: string[] = []; const created: Order[] = [];
      await client.route('**/api/orders/', async route => {
        if (route.request().method() !== 'POST') {await route.continue(); return;}
        keys.push(route.request().headers()['idempotency-key']);
        const response = await route.fetch();
        expect(response.status()).toBe(created.length === 0 ? 201 : 200);
        created.push(await response.json() as Order);
        if (created.length === 1) await route.fulfill({status: 503, json: {detail: 'Réponse interrompue après enregistrement. Réessayez.'}});
        else await route.fulfill({response});
      });
      const submit = client.getByRole('button', {name: 'Commander et régler au restaurant', exact: true});
      await submit.click();
      await expect(client.getByRole('alert')).toContainText('Réponse interrompue après enregistrement');
      await submit.click();
      await expect(client.getByRole('dialog')).toHaveCount(0);
      await expect(client.locator('.payment-note')).toHaveText('À régler au restaurant');
      expect(created).toHaveLength(2); expect(created[0].id).toBe(created[1].id);
      expect(keys[0]).toBeTruthy(); expect(keys[0]).toBe(keys[1]);
      const order = created[1];
      expect(order).toMatchObject({status: 'confirmed', paymentMethod: 'on_site', paymentStatus: 'due', subtotal: 26.8, total: 26.8, deliveryFee: 0, demoMode: false});
      expect(order.lines[0]).toMatchObject({quantity: 2, unitPrice: 13.4, total: 26.8});
      expect([...order.lines[0].choices].sort()).toEqual(['Cheddar supplémentaire', 'Sauce maison']);
      expect(Object.keys(order).some(key => /actor|onsite.*event|ledger/i.test(key))).toBe(false);
      await client.reload(); await client.getByRole('contentinfo').getByRole('button', {name: 'Mes commandes', exact: true}).click();
      await expect(client.getByRole('heading', {name: `Commande ${order.id}`, exact: true})).toBeVisible();
      await page.goto(`/crm/commandes/?status=all&q=${order.id}`);
      const card = page.locator(`[data-order-id="${order.id}"]`);
      await expect(card.locator('.crm-order-total')).toContainText('26,80');
      await expect(card.locator('.crm-payment-label')).toHaveText('À régler au restaurant');
      await card.getByRole('button', {name: 'Préparer', exact: true}).click();
      await card.getByRole('button', {name: 'Marquer prête', exact: true}).click();
      await expect(card.getByRole('button', {name: 'Terminer', exact: true})).toHaveCount(0);
      await expect(card).toContainText('Enregistrez l’encaissement avant de terminer');
      page.once('dialog', dialog => dialog.accept());
      await card.getByRole('button', {name: /Enregistrer l’encaissement/}).click();
      await expect(card.locator('.crm-payment-label')).toHaveText('Réglé sur place');
      const repeatedCollection = await page.request.post(`/crm/commandes/${order.id}/encaissement/`, {
        headers: {'X-CSRFToken': await csrf(page.context())},
        form: {expected_status: 'ready', expected_payment_status: 'due', return_q: order.id, return_filter: 'all'},
      });
      expect(repeatedCollection.status()).toBe(200);
      expect(await repeatedCollection.text()).toContain('encaissement déjà enregistré');
      await refreshClient(client, 'Réglé sur place');
      await card.getByRole('button', {name: 'Terminer', exact: true}).click();
      await expect(card.locator('.crm-order-status')).toHaveText('Terminée');
      page.once('dialog', dialog => dialog.accept());
      await card.getByRole('button', {name: 'Confirmer le remboursement', exact: true}).click();
      await expect(card.locator('.crm-payment-label')).toHaveText('Remboursé sur place');
      await expect(card.locator('.crm-order-status')).toHaveText('Terminée');
      await refreshClient(client, 'Remboursé sur place');
      const final = await (await guest.request.get(`/api/orders/${order.id}/?token=${encodeURIComponent(order.accessToken!)}`)).json() as Order;
      expect(final).toMatchObject({total: 26.8, paymentMethod: 'on_site', paymentStatus: 'refunded', status: 'completed'});
      expect(final.history.map(event => event.status)).toEqual(['confirmed', 'preparing', 'ready', 'completed']);
      await card.getByText('Détails et suivi', {exact: true}).click();
      await expect(card.getByText('Règlements sur place', {exact: true})).toBeVisible();
      await expect(card.locator('.crm-order-history').nth(1).locator('li')).toHaveCount(2);
      expect(await client.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
    } finally {await guest.close();}
  });

  test('compte : livraison réelle, accès client puis lecteur refusés et remboursement actif annule la commande', async ({page, browser}) => {
    test.setTimeout(120_000);
    page.setDefaultTimeout(15_000);
    await manager(page);
    const baseURL = process.env.E2E_BASE_URL!;
    const customer = await browser.newContext({baseURL, viewport: page.viewportSize()!, extraHTTPHeaders: {Origin: baseURL}});
    const client = await customer.newPage();
    client.setDefaultTimeout(15_000);
    try {
      const email = `onsite-account-${randomUUID()}@example.com`;
      await client.goto('/');
      await client.getByRole('button', {name: /^(Mon compte|Compte)$/}).click();
      await client.getByRole('button', {name: 'Créer un compte', exact: true}).click();
      await client.getByLabel('Nom complet', {exact: true}).fill('Client Livraison');
      await client.getByLabel('Adresse e-mail', {exact: true}).fill(email);
      await client.getByLabel('Mot de passe', {exact: true}).fill('Recette-Physique!74xq');
      await client.getByLabel('Confirmer le mot de passe', {exact: true}).fill('Recette-Physique!74xq');
      const registration = client.waitForResponse(response => response.url().endsWith('/api/auth/register/'));
      await client.getByRole('button', {name: 'Créer mon compte', exact: true}).click();
      const user = (await (await registration).json()).user as {id: number};
      await expect(client.getByRole('button', {name: 'Se déconnecter', exact: true})).toBeVisible();
      await client.getByRole('button', {name: /^(Notre carte|Carte)$/}).click();
      await client.getByRole('button', {name: 'Ajouter Le Cookie Choco', exact: true}).click();
      await client.getByRole('dialog').getByRole('button', {name: /Ajouter ·/}).click();
      await client.getByRole('button', {name: 'Voir le panier', exact: true}).click();
      await client.getByRole('button', {name: 'Livraison', exact: true}).click();
      await client.getByRole('button', {name: 'Passer commande', exact: true}).click();
      await expect(client.getByLabel('Adresse e-mail', {exact: true})).toHaveValue(email);
      await client.getByLabel('Téléphone', {exact: true}).fill('0612345678');
      await client.getByLabel('Adresse de livraison', {exact: true}).fill('24 rue du Test');
      await client.getByLabel('Code postal', {exact: true}).fill('99999');
      await client.getByLabel('Ville', {exact: true}).fill('Paris');
      const submit = client.getByRole('button', {name: 'Commander et régler à la livraison', exact: true});
      await submit.click(); await expect(client.getByRole('alert')).toContainText('hors de notre zone de livraison');
      await client.getByLabel('Code postal', {exact: true}).fill('75011');
      const response = client.waitForResponse(result => result.url().endsWith('/api/orders/') && result.request().method() === 'POST');
      await submit.click();
      const order = await (await response).json() as Order;
      expect(order).toMatchObject({status: 'confirmed', paymentMethod: 'on_site', paymentStatus: 'due', subtotal: 3.9, deliveryFee: 3.9, total: 7.8, demoMode: false});
      await expect(client.locator('.payment-note')).toHaveText('À régler à la livraison');
      const financialForm = {expected_status: 'confirmed', expected_payment_status: 'due'};
      const deniedCustomer = await customer.request.post(`/crm/commandes/${order.id}/encaissement/`, {headers: {'X-CSRFToken': await csrf(customer)}, form: financialForm});
      expect(deniedCustomer.status()).toBe(403);
      await page.goto(`/admin/shop/user/${user.id}/change/`);
      await page.locator('#id_is_staff').check();
      const permissions = await page.locator('#id_user_permissions_from option').evaluateAll(options => options.map(option => ({value: (option as HTMLOptionElement).value, text: option.textContent || ''})));
      const viewOrder = permissions.find(option => /\bCan view order\b/i.test(option.text));
      if (!viewOrder) throw new Error('Permission de lecture des commandes absente de la recette.');
      await page.locator('#id_user_permissions_from').selectOption(viewOrder.value);
      await page.locator('#id_user_permissions_add').click();
      await page.locator('input[name="_save"]').click();
      await client.goto(`/crm/commandes/?status=all&q=${order.id}`);
      await expect(client.locator(`[data-order-id="${order.id}"]`)).toBeVisible();
      await expect(client.getByRole('button', {name: /Enregistrer l’encaissement|Confirmer le remboursement|Préparer/})).toHaveCount(0);
      const deniedReader = await customer.request.post(`/crm/commandes/${order.id}/encaissement/`, {headers: {'X-CSRFToken': await csrf(customer)}, form: financialForm});
      expect(deniedReader.status()).toBe(403);
      const deniedRefund = await customer.request.post(`/crm/commandes/${order.id}/remboursement/`, {headers: {'X-CSRFToken': await csrf(customer)}, form: financialForm});
      expect(deniedRefund.status()).toBe(403);
      await page.goto(`/crm/commandes/?status=all&q=${order.id}`);
      const card = page.locator(`[data-order-id="${order.id}"]`);
      await expect(card.locator('.crm-payment-label')).toHaveText('À régler à la livraison');
      page.once('dialog', dialog => dialog.accept());
      await card.getByRole('button', {name: /Enregistrer l’encaissement/}).click();
      page.once('dialog', dialog => dialog.accept());
      await card.getByRole('button', {name: 'Confirmer le remboursement et annuler', exact: true}).click();
      await expect(card.locator('.crm-order-status')).toHaveText('Annulée');
      const final = await (await customer.request.get(`/api/orders/${order.id}/`)).json() as Order;
      expect(final).toMatchObject({paymentStatus: 'refunded', paymentMethod: 'on_site', total: 7.8, status: 'cancelled'});
      await client.goto(`/?order_id=${order.id}`);
      await expect(client.locator('.payment-note')).toHaveText('Remboursé sur place');
      await expect(client.getByRole('button', {name: /paiement test/})).toHaveCount(0);
      expect(await client.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    } finally {await customer.close();}
  });
});
