import {expect, test, type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';

// These genuine submissions belong only to the disposable recipe instance.
test.skip(!process.env.STC_RUNTIME_DIR?.includes('stc-e2e-'), 'Recette réservée à scripts/e2e.py et sa base temporaire.');
test.describe.configure({mode: 'serial'});

async function login(page: Page) {
  const content = readFileSync(join(process.env.STC_RUNTIME_DIR!, 'admin-credentials.txt'), 'utf8');
  const email = content.match(/^E-mail\s*:\s*(.+)$/m)?.[1]?.trim();
  const password = content.match(/^Mot de passe\s*:\s*(.+)$/m)?.[1]?.trim();
  if (!email || !password) throw new Error('Accès de recette isolée absents.');
  await page.goto('/crm/connexion/');
  await page.locator('[name="username"]').fill(email);
  await page.locator('[name="password"]').fill(password);
  await page.getByRole('button', {name: 'Se connecter', exact: true}).click();
  await expect(page).toHaveURL(/\/crm\/$/);
}

test('CRM : recherche et page persistent après une action puis un conflit réel', async ({page}) => {
  test.setTimeout(100_000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await login(page);
  const csrf = (await page.context().cookies()).find(cookie => cookie.name === 'csrftoken')?.value;
  if (!csrf) throw new Error('Protection CSRF de recette absente.');
  const query = `Alice Audit & Cie ${randomUUID().slice(0, 6)}`;
  for (let index = 0; index < 32; index++) {
    const response = await page.request.post('/api/orders/', {
      headers: {'X-CSRFToken': csrf, 'Idempotency-Key': randomUUID()},
      data: {
        mode: 'À emporter', paymentMethod: 'simulation',
        items: [{productId: 6, quantity: 1, choices: []}],
        customer: {name: index === 31 ? 'Bob hors recherche' : query, email: 'recette@example.com', phone: '0612345678'},
      },
    });
    expect(response.status()).toBe(201);
  }
  await page.goto(`/crm/commandes/?${new URLSearchParams({status: 'all', q: query, page: '2'})}`);
  await expect(page.getByRole('textbox', {name: 'Rechercher une commande', exact: true})).toHaveValue(query);
  await expect(page.locator('.crm-order-card')).toHaveCount(1);
  const row = page.locator('.crm-order-card').first();
  const oldForm = await row.locator('form').filter({has: page.getByRole('button', {name: 'Préparer', exact: true})}).evaluate(form => {
    const element = form as HTMLFormElement;
    return {action: element.action, fields: Array.from(new FormData(element).entries()).map(([name, value]) => [name, String(value)])};
  });
  const orderId = await row.getAttribute('data-order-id');
  await row.getByRole('button', {name: 'Préparer', exact: true}).click();
  await expect(page).toHaveURL(url => url.pathname === '/crm/commandes/' && url.searchParams.get('q') === query && url.searchParams.get('page') === '2');
  await expect(page.locator(`.crm-order-card[data-order-id="${orderId}"] .crm-order-status`)).toHaveText('En cuisine');
  await expect(page.locator('.crm-pagination')).toContainText('Page 2 sur 2');
  await expect(page.locator('.crm-order-card')).toHaveCount(1);

  const conflict = page.waitForResponse(response => response.url() === oldForm.action && response.request().method() === 'POST');
  await page.evaluate(saved => {
    const form = document.createElement('form');
    form.method = 'post';
    form.action = saved.action;
    for (const [name, value] of saved.fields) {
      const field = document.createElement('input');
      field.type = 'hidden'; field.name = name; field.value = value;
      form.append(field);
    }
    document.body.append(form);
    form.submit();
  }, oldForm);
  expect((await conflict).status()).toBe(409);
  await expect(page.getByRole('alert')).toContainText('Cette commande a déjà été mise à jour');
  await expect(page.getByRole('textbox', {name: 'Rechercher une commande', exact: true})).toHaveValue(query);
  await expect(page.locator('.crm-pagination')).toContainText('Page 2 sur 2');
  await expect(page.locator('.crm-order-card')).toHaveCount(1);
  await expect(page.locator(`.crm-order-card[data-order-id="${orderId}"] .crm-order-status`)).toHaveText('En cuisine');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('CRM : une pause refusée conserve le statut enregistré et le brouillon visible', async ({page}) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await login(page);
  const before = await (await page.request.get('/api/restaurant/')).json() as {orderingEnabled: boolean; deliveryFee: number};
  expect(before.orderingEnabled).toBe(true);
  await page.goto('/crm/restaurant/');
  const savedBadge = await page.locator('.crm-topbar .crm-status').innerText();
  await page.locator('[name="ordering_enabled"]').uncheck();
  await page.locator('[name="name"]').fill('Brouillon de recette conservé');
  await page.locator('[name="delivery_fee"]').fill('montant invalide');
  await page.getByRole('button', {name: 'Enregistrer les changements', exact: true}).click();
  await expect(page.locator('.crm-field.has-error [name="delivery_fee"]')).toBeVisible();
  await expect(page.locator('.crm-topbar .crm-status')).toHaveText(savedBadge);
  await expect(page.locator('[name="ordering_enabled"]')).not.toBeChecked();
  await expect(page.locator('[name="name"]')).toHaveValue('Brouillon de recette conservé');
  const after = await (await page.request.get('/api/restaurant/')).json();
  expect(after).toEqual(before);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
