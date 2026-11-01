import {expect, test, type BrowserContext, type Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';

// Accounts and orders created here must never reach a business database.
test.skip(!process.env.STC_RUNTIME_DIR?.includes('stc-e2e-'), 'Clients CRM : uniquement la base jetable de scripts/e2e.py.');

async function csrf(context: BrowserContext) {
  const token = (await context.cookies()).find(cookie => cookie.name === 'csrftoken')?.value;
  if (!token) throw new Error('Jeton CSRF de recette absent.');
  return token;
}

async function loginManager(page: Page) {
  const content = readFileSync(join(process.env.STC_RUNTIME_DIR!, 'admin-credentials.txt'), 'utf8');
  const email = content.match(/^E-mail\s*:\s*(.+)$/m)?.[1]?.trim();
  const password = content.match(/^Mot de passe\s*:\s*(.+)$/m)?.[1]?.trim();
  if (!email || !password) throw new Error('Accès gérant jetables absents.');
  await page.goto('/crm/connexion/');
  await page.locator('input[name="username"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', {name: 'Se connecter', exact: true}).click();
  await expect(page).toHaveURL(/\/crm\/$/);
}

test('Clients : profil et commandes rattachés au compte, invités séparés, fiche lisible à 320 px', async ({page, browser}, info) => {
  test.setTimeout(90_000);
  const baseURL = process.env.E2E_BASE_URL!;
  const options = {baseURL, extraHTTPHeaders: {Origin: baseURL}};
  const accountContext = await browser.newContext(options);
  const guestContext = await browser.newContext(options);
  const email = `crm-client-${randomUUID()}@example.com`;
  const name = `Camille CRM ${randomUUID().slice(0, 8)}`;
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await accountContext.request.get('/api/auth/csrf/');
    const registration = await accountContext.request.post('/api/auth/register/', {
      headers: {'X-CSRFToken': await csrf(accountContext)},
      data: {name, email, password: 'CRM-Customer!42Long'},
    });
    expect(registration.status()).toBe(201);
    const {user} = await registration.json() as {user: {id: number}};
    const profile = await accountContext.request.patch('/api/auth/me/', {
      headers: {'X-CSRFToken': await csrf(accountContext)}, data: {phone: '06 12 34 56 78'},
    });
    expect(profile.ok()).toBe(true);
    const paymentMethod = process.env.STC_PAYMENT_MODE === 'on_site' ? 'on_site' : 'simulation';
    const orderResponse = await accountContext.request.post('/api/orders/', {
      headers: {'X-CSRFToken': await csrf(accountContext), 'Idempotency-Key': randomUUID()},
      data: {mode: 'À emporter', items: [{productId: 6, quantity: 1, choices: []}], customer: {name, email, phone: '0699999999'}, paymentMethod},
    });
    expect(orderResponse.status()).toBe(201);
    const order = await orderResponse.json() as {id: string};
    await guestContext.request.get('/api/auth/csrf/');
    const guestResponse = await guestContext.request.post('/api/orders/', {
      headers: {'X-CSRFToken': await csrf(guestContext), 'Idempotency-Key': randomUUID()},
      data: {mode: 'À emporter', items: [{productId: 6, quantity: 1, choices: []}], customer: {name: 'Contact invité', email, phone: '0612345678'}, paymentMethod},
    });
    expect(guestResponse.status()).toBe(201);
    const guestOrder = await guestResponse.json() as {id: string};
    expect((await accountContext.request.get('/crm/restaurant/clients/')).status()).toBe(403);
    expect((await accountContext.request.get(`/crm/restaurant/clients/${user.id}/`)).status()).toBe(403);

    await loginManager(page);
    const nav = page.getByRole('navigation', {name: 'Gestion du restaurant', exact: true});
    await expect(nav.getByRole('link')).toHaveCount(4);
    await nav.getByRole('link', {name: 'Mon restaurant', exact: true}).click();
    await page.getByRole('navigation', {name: 'Rubriques de Mon restaurant'}).getByRole('link', {name: 'Clients', exact: true}).click();
    const search = page.getByRole('textbox', {name: 'Nom, e-mail ou téléphone du client', exact: true});
    await search.fill(email);
    await page.getByRole('button', {name: 'Rechercher', exact: true}).click();
    const row = page.locator(`[data-customer-id="${user.id}"]`);
    await expect(row).toContainText(name);
    await expect(row).toContainText('06 12 34 56 78');
    await expect(page.locator('[data-customer-id]')).toHaveCount(1);
    await search.fill('0612345678');
    await page.getByRole('button', {name: 'Rechercher', exact: true}).click();
    await expect(row).toContainText(name);
    await expect(row).toContainText('06 12 34 56 78');
    await search.fill(email);
    await page.getByRole('button', {name: 'Rechercher', exact: true}).click();
    await row.getByRole('link', {name: `Voir la fiche de ${name}`, exact: true}).click();
    await expect(page.getByRole('heading', {name: 'Fiche client', exact: true})).toBeVisible();
    await expect(page.locator('.crm-customer-contact')).toContainText('06 12 34 56 78');
    await expect(page.locator('.crm-customer-contact')).not.toContainText('0699999999');
    await expect(page.locator('.crm-customer-history [data-order-id]')).toHaveCount(1);
    await expect(page.locator(`[data-order-id="${order.id}"]`)).toBeVisible();
    await expect(page.locator(`[data-order-id="${guestOrder.id}"]`)).toHaveCount(0);
    const settled = page.locator('.crm-customer-summary > div').filter({hasText: 'Montant réglé sur place'});
    await expect(settled).toContainText('0,00 €');
    const response = await page.request.get(page.url());
    expect(response.headers()['cache-control']).toContain('no-store');
    const widths = info.project.name === 'mobile' ? [320, 390, 430] : [page.viewportSize()!.width];
    for (const width of widths) {
      await page.setViewportSize({width, height: 844});
      await page.evaluate(() => document.fonts.ready);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect(nav.getByRole('link', {name: 'Mon restaurant', exact: true})).toHaveAttribute('aria-current', 'page');
      await page.screenshot({path: info.outputPath(`fiche-client-${width}.png`), fullPage: true});
    }
    await page.getByRole('link', {name: 'Retour aux clients', exact: true}).click();
    await expect(search).toHaveValue(email);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: info.outputPath('liste-clients.png'), fullPage: true});
    await page.goto(`/crm/commandes/?status=all&q=${encodeURIComponent(order.id)}`);
    await page.locator(`[data-order-id="${order.id}"]`).getByText('Détails et suivi', {exact: true}).click();
    await page.getByRole('link', {name: 'Voir la fiche client', exact: true}).click();
    await expect(page.getByRole('heading', {name, exact: true})).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    await accountContext.close();
    await guestContext.close();
  }
});
