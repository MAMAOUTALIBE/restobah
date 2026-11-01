import {expect, test, type Locator, type Page, type TestInfo} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';

// Authenticated visual review only; no business mutation is submitted by this file.
test.skip(!process.env.STC_RUNTIME_DIR?.includes('stc-e2e-'), 'Contrôle CRM réservé à l’instance temporaire de scripts/e2e.py.');
test.use({reducedMotion: 'reduce'});

async function login(page: Page) {
  const content = readFileSync(join(process.env.STC_RUNTIME_DIR!, 'admin-credentials.txt'), 'utf8');
  const email = content.match(/^E-mail\s*:\s*(.+)$/m)?.[1]?.trim();
  const password = content.match(/^Mot de passe\s*:\s*(.+)$/m)?.[1]?.trim();
  if (!email || !password) throw new Error('Les accès de l’instance de recette sont absents.');
  await page.goto('/crm/connexion/');
  await page.locator('[name="username"]').fill(email);
  await page.locator('[name="password"]').fill(password);
  await page.getByRole('button', {name: 'Se connecter', exact: true}).click();
  await expect(page).toHaveURL(/\/crm\/$/);
}

async function geometry(page: Page, active: string) {
  const nav = page.getByRole('navigation', {name: 'Gestion du restaurant', exact: true});
  await expect(nav.getByRole('link')).toHaveCount(4);
  for (const label of ['Accueil', 'Commandes', 'Ma carte', 'Mon restaurant']) {
    const link = nav.getByRole('link', {name: label, exact: true});
    await expect(link).toBeVisible();
    await link.click({trial: true});
  }
  await expect(nav.locator('[aria-current="page"]')).toHaveCount(1);
  await expect(nav.getByRole('link', {name: active, exact: true})).toHaveAttribute('aria-current', 'page');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${active} ne déborde pas horizontalement`).toBe(true);
}

async function reachable(control: Locator) {
  await expect(control).toBeVisible();
  await expect(control).toBeEnabled();
  // A trial checks hit testing and overlay interference without clicking or submitting.
  await control.click({trial: true});
}

async function capture(page: Page, info: TestInfo, name: string) {
  const width = page.viewportSize()!.width;
  const path = join(process.cwd(), 'screenshots', `crm-${name}-${width}.png`);
  await page.screenshot({path});
  await info.attach(`CRM ${name} ${width}px`, {path, contentType: 'image/png'});
}

const pages = [
  {path: '/crm/', active: 'Accueil', heading: 'Bonjour, chef.', slug: 'accueil'},
  {path: '/crm/commandes/?status=all', active: 'Commandes', heading: 'Commandes', slug: 'commandes'},
  {path: '/crm/carte/', active: 'Ma carte', heading: 'Ma carte', slug: 'carte'},
  {path: '/crm/restaurant/', active: 'Mon restaurant', heading: 'Mon restaurant', slug: 'restaurant'},
];

test('CRM visuel : quatre rubriques et fiche plat utilisables sur les écrans de recette', async ({page}, info) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const businessPosts: string[] = [];
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (request.method() === 'POST' && path.startsWith('/crm/') && path !== '/crm/connexion/') businessPosts.push(path);
  });
  await login(page);
  const originalWidth = page.viewportSize()!.width;
  const widths = info.project.name === 'mobile' ? [originalWidth, 320, 430] : [originalWidth];

  for (const width of widths) {
    await page.setViewportSize({width, height: width === originalWidth ? page.viewportSize()!.height : 844});
    for (const screen of pages) {
      const response = await page.goto(screen.path);
      expect(response?.status()).toBe(200);
      await expect(page.locator('main').getByRole('heading', {name: screen.heading, exact: true})).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      await geometry(page, screen.active);
      if (screen.slug === 'carte') {
        await reachable(page.locator('main').getByRole('link', {name: 'Ajouter un plat', exact: true}));
        await reachable(page.locator('[data-product-id]').first().getByRole('switch'));
        await reachable(page.locator('[data-product-id]').first().getByRole('link', {name: /^Modifier /}));
      } else if (screen.slug === 'restaurant') {
        await reachable(page.getByRole('button', {name: 'Enregistrer les changements', exact: true}));
        await reachable(page.getByRole('button', {name: 'Ajouter un créneau', exact: true}));
        await reachable(page.getByRole('button', {name: 'Ajouter la fermeture', exact: true}));
      } else {
        await reachable(page.locator('main').getByRole('button', {name: 'Actualiser', exact: true}));
      }
      await page.evaluate(() => scrollTo(0, 0));
      await capture(page, info, screen.slug);
    }

    const editResponse = await page.goto('/crm/carte/6/modifier/');
    expect(editResponse?.status()).toBe(200);
    await expect(page.getByRole('heading', {name: 'Modifier le plat', exact: true})).toBeVisible();
    await geometry(page, 'Ma carte');
    await reachable(page.locator('[name="name"]'));
    await reachable(page.locator('[name="price"]'));
    await page.evaluate(() => scrollTo(0, 0));
    await capture(page, info, 'plat');
    const photo = page.locator('[data-photo-preview] img');
    await photo.scrollIntoViewIfNeeded();
    await expect(photo).toBeVisible();
    await expect.poll(() => photo.evaluate(el => (el as HTMLImageElement).complete && (el as HTMLImageElement).naturalWidth > 0)).toBe(true);
    await capture(page, info, 'plat-photo');
    await reachable(page.getByRole('button', {name: 'Enregistrer le plat', exact: true}));
    await capture(page, info, 'plat-bas');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  expect(errors).toEqual([]);
  expect(businessPosts, 'Ce contrôle visuel ne doit jamais enregistrer une modification métier.').toEqual([]);
});
