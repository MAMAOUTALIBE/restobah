import {expect, test} from '@playwright/test';
import {randomUUID} from 'node:crypto';

// This independent audit mutates only the disposable recipe database.
test.skip(!process.env.STC_RUNTIME_DIR?.includes('stc-e2e-'), 'Recette du profil réservée à scripts/e2e.py.');

test('profil : une erreur réseau garde la saisie et permet un enregistrement réel, lisible à 320 px', async ({page}, info) => {
  const errors: string[] = [];
  const consoleErrors: string[] = [];
  let attempts = 0;
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    const expectedAbort = attempts === 1 && message.location().url.endsWith('/api/auth/me/') && message.text().includes('net::ERR_FAILED');
    if (message.type() === 'error' && !expectedAbort) consoleErrors.push(message.text());
  });
  const email = `profile-qa-${randomUUID()}@example.com`;
  await page.goto('/');
  await page.getByRole('button', {name: /^(Mon compte|Compte)$/}).click();
  await page.getByRole('button', {name: 'Créer un compte', exact: true}).click();
  await page.getByLabel('Nom complet', {exact: true}).fill('Camille Recette');
  await page.getByLabel('Adresse e-mail', {exact: true}).fill(email);
  await page.getByLabel('Mot de passe', {exact: true}).fill('Profil-Recette!97x2');
  await page.getByRole('button', {name: 'Créer mon compte', exact: true}).click();
  const profile = page.locator('.profile-card');
  await expect(profile).toBeVisible();
  await page.route('**/api/auth/me/', async route => {
    if (route.request().method() === 'PATCH' && ++attempts === 1) await route.abort();
    else await route.continue();
  });
  const name = profile.getByLabel('Nom du compte', {exact: true});
  const phone = profile.getByLabel('Téléphone du compte (facultatif)', {exact: true});
  const save = profile.getByRole('button', {name: 'Enregistrer mes informations', exact: true});
  await name.fill('Camille Coordonnées Conservées');
  await phone.fill('06 44 55 66 77');
  await save.click();
  await expect(profile.getByRole('alert')).toBeVisible();
  await expect(name).toHaveValue('Camille Coordonnées Conservées');
  await expect(phone).toHaveValue('06 44 55 66 77');
  await expect(save).toBeEnabled();
  expect((await (await page.request.get('/api/auth/me/')).json()).user.name).toBe('Camille Recette');
  await save.click();
  await expect(profile.getByRole('status')).toHaveText('Vos informations sont enregistrées.');
  expect((await (await page.request.get('/api/auth/me/')).json()).user).toMatchObject({name: 'Camille Coordonnées Conservées', phone: '06 44 55 66 77', email});
  await page.reload();
  await page.getByRole('button', {name: /^(Mon compte|Compte)$/}).click();
  await expect(name).toHaveValue('Camille Coordonnées Conservées');
  await expect(phone).toHaveValue('06 44 55 66 77');
  for (const width of [320, 768]) {
    await page.setViewportSize({width, height: 900});
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(save).toBeVisible();
    const box = await save.boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
    await page.screenshot({path: info.outputPath(`compte-profil-${width}.png`), fullPage: true});
  }
  expect(attempts).toBe(2);
  expect(errors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
