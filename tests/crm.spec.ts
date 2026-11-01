import {expect, test, type BrowserContext, type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';

// These scenarios write real records. Only scripts/e2e.py's disposable instance is allowed.
test.skip(!process.env.STC_RUNTIME_DIR?.includes('stc-e2e-'), 'Recette CRM réservée à scripts/e2e.py et sa base temporaire.');
test.describe.configure({mode: 'serial'});

function credentials() {
  const content = readFileSync(join(process.env.STC_RUNTIME_DIR!, 'admin-credentials.txt'), 'utf8');
  const email = content.match(/^E-mail\s*:\s*(.+)$/m)?.[1]?.trim();
  const password = content.match(/^Mot de passe\s*:\s*(.+)$/m)?.[1]?.trim();
  if (!email || !password) throw new Error('Les accès de recette isolée sont absents.');
  return {email, password};
}

async function login(page: Page) {
  await page.goto('/crm/connexion/');
  const access = credentials();
  await page.locator('input[name="username"]').fill(access.email);
  await page.locator('input[name="password"]').fill(access.password);
  await page.getByRole('button', {name: 'Se connecter', exact: true}).click();
  await expect(page).toHaveURL(/\/crm\/$/);
}

async function csrf(context: BrowserContext) {
  const value = (await context.cookies()).find(cookie => cookie.name === 'csrftoken')?.value;
  if (!value) throw new Error('La session de recette doit posséder un jeton CSRF.');
  return value;
}

async function removeTestProduct(page: Page, id: number) {
  // Existing Django admin supplies cleanup; the CRM itself never gets a destructive shortcut.
  await page.request.get(`/admin/shop/product/${id}/delete/`);
  const response = await page.request.post(`/admin/shop/product/${id}/delete/`, {
    headers: {'X-CSRFToken': await csrf(page.context())}, form: {post: 'yes'},
  });
  expect(response.ok()).toBe(true);
}

test('CRM : carte, photo, prix et disponibilité persistent et se synchronisent avec un site ouvert', async ({page, browser}) => {
  test.setTimeout(100_000);
  await login(page);
  const nav = page.getByRole('navigation', {name: 'Gestion du restaurant', exact: true});
  await expect(nav.getByRole('link')).toHaveCount(4);
  for (const name of ['Accueil', 'Commandes', 'Ma carte', 'Mon restaurant']) {
    await expect(nav.getByRole('link', {name, exact: true})).toBeVisible();
  }
  await nav.getByRole('link', {name: 'Ma carte', exact: true}).click();
  await expect(nav.getByRole('link', {name: 'Ma carte', exact: true})).toHaveAttribute('aria-current', 'page');

  const viewport = page.viewportSize()!;
  await page.setViewportSize({width: 320, height: 800});
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(nav.getByRole('link', {name: 'Mon restaurant', exact: true})).toBeVisible();
  await page.setViewportSize(viewport);

  const name = `Recette QA ${randomUUID().slice(0, 8)}`;
  const publicContext = await browser.newContext({baseURL: process.env.E2E_BASE_URL, viewport});
  const publicPage = await publicContext.newPage();
  let id: number | undefined;
  try {
    await publicPage.goto('/');
    await publicPage.getByRole('textbox', {name: 'Rechercher un plat', exact: true}).fill(name);
    await expect(publicPage.getByText('Aucun plat pour cette recherche.', {exact: true})).toBeVisible();

    await page.bringToFront();
    await page.getByRole('link', {name: 'Ajouter un plat', exact: true}).first().click();
    await page.locator('[name="name"]').fill(name);
    await page.locator('[name="category"]').selectOption({label: 'Burgers'});
    await page.locator('[name="price"]').fill('-2');
    await page.locator('[name="description"]').fill('Recette de validation préparée sur place.');
    await page.getByRole('button', {name: 'Enregistrer le plat', exact: true}).click();
    await expect(page.getByRole('alert')).toContainText('Le plat n’a pas été enregistré.');
    await expect(page.locator('[name="name"]')).toHaveValue(name);
    await page.locator('[name="price"]').fill('12,50');
    await page.locator('[name="available"]').check();
    await page.locator('[name="photo"]').setInputFiles(join(process.cwd(), 'public/images/burger.jpg'));
    await expect(page.locator('[data-photo-preview] img')).toBeVisible();
    await page.getByRole('button', {name: 'Enregistrer le plat', exact: true}).click();
    await expect(page).toHaveURL(/\/crm\/carte\/$/);
    const productsResponse = await page.request.get('/api/products/');
    const products = await productsResponse.json() as {id: number; name: string; image: string}[];
    id = products.find(product => product.name === name)?.id;
    expect(id).toBeDefined();
    const row = page.locator(`[data-product-id="${id}"]`);
    await expect(row).toContainText('12,50');
    await expect(row.locator('img')).toHaveAttribute('src', /\/media\/products\/.+\.jpg/);
    await page.reload();
    await expect(row).toContainText(name);

    await publicPage.bringToFront();
    const publicCard = publicPage.locator('.product-card').filter({hasText: name});
    await expect(publicCard).toBeVisible({timeout: 22_000});
    await expect(publicCard).toContainText('12,50');
    await expect(publicCard.locator('img')).toHaveAttribute('src', /\/media\/products\/.+\.jpg/);
    await expect(publicPage.getByRole('textbox', {name: 'Rechercher un plat', exact: true})).toHaveValue(name);

    await page.bringToFront();
    await row.getByRole('link', {name: `Modifier ${name}`, exact: true}).click();
    const renamed = `${name} modifiée`;
    await page.locator('[name="name"]').fill(renamed);
    await page.locator('[name="price"]').fill('13,40');
    await page.getByRole('button', {name: 'Enregistrer le plat', exact: true}).click();
    await expect(row).toContainText('13,40');
    await publicPage.bringToFront();
    await expect(publicCard).toContainText('13,40', {timeout: 22_000});
    await expect(publicCard).toContainText(renamed);

    await page.bringToFront();
    await row.getByRole('switch', {name: `Disponibilité de ${renamed}`, exact: true}).click();
    await expect(row.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
    await page.reload();
    await expect(row.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
    await publicPage.bringToFront();
    await expect(publicCard.getByRole('button', {name: `Ajouter ${renamed}`, exact: true})).toBeDisabled({timeout: 22_000});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  } finally {
    if (id !== undefined) await removeTestProduct(page, id);
    await publicContext.close();
  }
});

test('CRM : une commande client suit les étapes métier avec le même total et le même historique', async ({page, browser}) => {
  test.setTimeout(100_000);
  await login(page);
  const baseURL = process.env.E2E_BASE_URL;
  const guest = await browser.newContext({baseURL, viewport: page.viewportSize()!, extraHTTPHeaders: {Origin: baseURL!}});
  try {
    await guest.request.get('/api/auth/csrf/');
    const response = await guest.request.post('/api/orders/', {
      headers: {'X-CSRFToken': await csrf(guest), 'Idempotency-Key': randomUUID()},
      data: {mode: 'À emporter', items: [{productId: 6, quantity: 1, choices: []}], customer: {name: 'Camille CRM', email: 'camille-crm@example.com', phone: '0612345678'}, paymentMethod: 'simulation'},
    });
    expect(response.status()).toBe(201);
    const order = await response.json() as {id: string; accessToken: string; total: number};
    await guest.addInitScript(({id, accessToken}) => localStorage.setItem('stc-guest-orders', JSON.stringify([{id, accessToken}])), order);
    const clientPage = await guest.newPage();
    await clientPage.goto(`/?order_id=${order.id}`);
    await expect(clientPage.locator('.order-status')).toHaveText('Confirmée');

    await page.goto('/crm/commandes/');
    const card = page.locator(`[data-order-id="${order.id}"]`);
    await expect(card).toContainText('Camille CRM');
    for (const [label, status] of [['Préparer', 'preparing'], ['Marquer prête', 'ready'], ['Terminer', 'completed']]) {
      await page.bringToFront();
      await card.getByRole('button', {name: label, exact: true}).click();
      await expect.poll(async () => {
        const detail = await guest.request.get(`/api/orders/${order.id}/?token=${encodeURIComponent(order.accessToken)}`);
        return (await detail.json()).status;
      }).toBe(status);
      if (status === 'preparing') {
        await clientPage.bringToFront();
        await expect(clientPage.locator('.order-status')).toHaveText('En cuisine', {timeout: 36_000});
      }
    }
    const detailResponse = await guest.request.get(`/api/orders/${order.id}/?token=${encodeURIComponent(order.accessToken)}`);
    const detail = await detailResponse.json() as {total: number; history: {status: string}[]};
    expect(detail.total).toBe(order.total);
    expect(detail.history.map(event => event.status)).toEqual(['confirmed', 'preparing', 'ready', 'completed']);
    await clientPage.reload();
    await expect(clientPage.locator('.order-status')).toHaveText('Terminée');
  } finally {
    await guest.close();
  }
});

test('CRM : les horaires se modifient réellement, restent après rechargement et refusent une plage invalide', async ({page}) => {
  await login(page);
  await page.goto('/crm/restaurant/');
  const form = page.locator('.crm-restaurant-form');
  const original = await form.evaluate(el => [...new FormData(el as HTMLFormElement).entries()].filter((entry): entry is [string, string] => typeof entry[1] === 'string'));
  try {
    const opens = page.locator('[name="hours-0-opens"]');
    const closes = page.locator('[name="hours-0-closes"]');
    const closingTime = await closes.inputValue();
    await opens.fill(closingTime);
    await page.getByRole('button', {name: 'Enregistrer les changements', exact: true}).click();
    await expect(page.getByRole('alert')).toContainText('Les changements n’ont pas été enregistrés.');
    await opens.fill('12:00');
    await page.getByRole('button', {name: 'Enregistrer les changements', exact: true}).click();
    await expect(page).toHaveURL(/\/crm\/restaurant\/$/);
    await page.reload();
    await expect(opens).toHaveValue('12:00');
    const restaurant = await (await page.request.get('/api/restaurant/')).json() as {openingHours: {weekday: number; opens: string}[]};
    expect(restaurant.openingHours.some(period => period.weekday === 0 && period.opens === '12:00')).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  } finally {
    await page.goto('/crm/restaurant/');
    const freshRevision = await form.locator('[name="revision"]').inputValue();
    const data = Object.fromEntries(original);
    data.revision = freshRevision;
    data.csrfmiddlewaretoken = await csrf(page.context());
    const restored = await page.request.post('/crm/restaurant/', {headers: {'X-CSRFToken': data.csrfmiddlewaretoken}, form: data});
    expect(restored.ok()).toBe(true);
  }
});
