import {expect, test, type Page, type TestInfo} from '@playwright/test';
import {readFileSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';

// Real submissions are permitted only against scripts/e2e.py's disposable services.
test.skip(!process.env.STC_RUNTIME_DIR?.includes('stc-e2e-'), 'Recette CSRF réservée à la base et aux médias temporaires.');
test.use({reducedMotion: 'reduce'});

function credentials() {
  const content = readFileSync(join(process.env.STC_RUNTIME_DIR!, 'admin-credentials.txt'), 'utf8');
  const email = content.match(/^E-mail\s*:\s*(.+)$/m)?.[1]?.trim();
  const password = content.match(/^Mot de passe\s*:\s*(.+)$/m)?.[1]?.trim();
  if (!email || !password) throw new Error('Les accès privés de recette isolée sont absents.');
  return {email, password};
}

async function signIn(page: Page) {
  const access = credentials();
  await page.locator('[name="username"]').fill(access.email);
  await page.locator('[name="password"]').fill(access.password);
  await page.getByRole('button', {name: 'Se connecter', exact: true}).click();
  await expect(page).toHaveURL(/\/crm\/$/);
}

function observeErrors(page: Page, refusedPath: string) {
  const jsErrors: string[] = [];
  const unexpectedHttp: {path: string; status: number}[] = [];
  const expected403: string[] = [];
  page.on('pageerror', error => jsErrors.push(error.message));
  page.on('response', response => {
    if (response.status() < 400) return;
    const path = new URL(response.url()).pathname;
    if (response.status() === 403 && response.request().method() === 'POST' && path === refusedPath) {
      expected403.push(path);
    } else unexpectedHttp.push({path, status: response.status()});
  });
  return {jsErrors, unexpectedHttp, expected403};
}

async function corruptToken(page: Page, formSelector = 'form') {
  return page.locator(`${formSelector} [name="csrfmiddlewaretoken"]`).first().evaluate(input => {
    const field = input as HTMLInputElement;
    // Keep the normal format; alter the mask so it cannot match the cookie secret.
    field.value = (field.value[0] === 'a' ? 'b' : 'a') + field.value.slice(1);
    return field.value;
  });
}

async function assertRecoveryPage(page: Page, info: TestInfo, name: string, sensitive: string[]) {
  await expect(page.getByRole('heading', {name: 'Votre demande n’a pas été enregistrée', exact: true})).toBeVisible();
  await expect(page.locator('form, script, .crm-sidebar, [data-product-id], [data-order-id]')).toHaveCount(0);
  const html = await page.content();
  for (const value of [...sensitive, 'CSRF token from POST', 'Origin checking failed', 'Referer checking failed']) {
    expect(html.includes(value), 'La page d’erreur ne doit exposer aucune saisie ni raison technique.').toBe(false);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const path = info.outputPath(`${name}.png`);
  await page.screenshot({path, fullPage: true});
  await info.attach(name, {path, contentType: 'image/png'});
}

async function assertObservedErrors(info: TestInfo, observed: ReturnType<typeof observeErrors>) {
  expect(observed.expected403).toHaveLength(1);
  expect(observed.unexpectedHttp).toEqual([]);
  expect(observed.jsErrors).toEqual([]);
  const path = info.outputPath('csrf-observed-errors.json');
  writeFileSync(path, JSON.stringify({project: info.project.name, expected403Count: observed.expected403.length, unexpectedHttp: observed.unexpectedHttp, jsErrors: observed.jsErrors}));
  await info.attach('Refus attendu et erreurs inattendues', {path, contentType: 'application/json'});
}

test('CRM : une connexion avec un jeton expiré propose une reprise GET puis une connexion valide', async ({page}, info) => {
  const path = '/crm/connexion/';
  const observed = observeErrors(page, path);
  await page.goto(path);
  const draftEmail = 'csrf-draft@example.com';
  const draftPassword = 'CSRF-Draft-Only-9x!';
  await page.locator('[name="username"]').fill(draftEmail);
  await page.locator('[name="password"]').fill(draftPassword);
  const invalidToken = await corruptToken(page);
  const rejected = page.waitForResponse(response => new URL(response.url()).pathname === path && response.request().method() === 'POST');
  await page.getByRole('button', {name: 'Se connecter', exact: true}).click();
  const response = await rejected;
  expect(response.status()).toBe(403);
  expect(response.headers()['content-type']).toContain('text/html');
  expect(response.headers()['cache-control']).toContain('no-store');
  await assertRecoveryPage(page, info, 'crm-csrf-login', [draftEmail, draftPassword, invalidToken]);
  const session = await (await page.request.get('/api/auth/me/')).json() as {user: unknown};
  expect(session.user).toBeNull();

  const resume = page.getByRole('link', {name: 'Revenir à la connexion', exact: true});
  await expect(resume).toHaveAttribute('href', path);
  await resume.click();
  await expect(page).toHaveURL(/\/crm\/connexion\/$/);
  await expect(page.locator('[name="username"]')).toHaveValue('');
  expect(await page.locator('[name="csrfmiddlewaretoken"]').inputValue()).not.toBe(invalidToken);
  await signIn(page);
  await expect(page.getByRole('navigation', {name: 'Gestion du restaurant', exact: true})).toBeVisible();
  await assertObservedErrors(info, observed);
});

test('CRM : une modification avec un jeton expiré reste sans effet et rouvre la fiche enregistrée', async ({page}, info) => {
  const path = '/crm/carte/6/modifier/';
  const observed = observeErrors(page, path);
  await page.goto('/crm/connexion/');
  await signIn(page);
  const before = await (await page.request.get('/api/products/')).json() as {id: number; name: string}[];
  const product = before.find(row => row.id === 6);
  expect(product).toBeDefined();
  await page.goto(path);
  const privateDraft = `Brouillon refusé ${randomUUID()}`;
  await page.locator('[name="name"]').fill(privateDraft);
  await page.locator('[name="price"]').fill('99,99');
  const invalidToken = await corruptToken(page, '.crm-product-form');
  const rejected = page.waitForResponse(response => new URL(response.url()).pathname === path && response.request().method() === 'POST');
  await page.getByRole('button', {name: 'Enregistrer le plat', exact: true}).click();
  const response = await rejected;
  expect(response.status()).toBe(403);
  expect(response.headers()['content-type']).toContain('text/html');
  expect(response.headers()['cache-control']).toContain('no-store');
  await assertRecoveryPage(page, info, 'crm-csrf-edit', [privateDraft, invalidToken, product!.name]);
  const after = await (await page.request.get('/api/products/')).json();
  expect(after).toEqual(before);

  const resume = page.getByRole('link', {name: 'Actualiser le formulaire', exact: true});
  await expect(resume).toHaveAttribute('href', path);
  await resume.click();
  await expect(page).toHaveURL(/\/crm\/carte\/6\/modifier\/$/);
  await expect(page.locator('[name="name"]')).toHaveValue(product!.name);
  await expect(page.locator('[name="name"]')).toBeEditable();
  await expect(page.getByRole('button', {name: 'Enregistrer le plat', exact: true})).toBeEnabled();
  expect(await page.locator('.crm-product-form').evaluate(form => (form as HTMLFormElement).checkValidity())).toBe(true);
  expect(await page.locator('.crm-product-form [name="csrfmiddlewaretoken"]').inputValue()).not.toBe(invalidToken);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await assertObservedErrors(info, observed);
});
