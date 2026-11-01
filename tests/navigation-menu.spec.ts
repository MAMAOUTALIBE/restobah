import {expect, test} from '@playwright/test';

test.use({reducedMotion: 'reduce'});

test('le menu indique la page active et ouvre ses cinq destinations', async ({page}) => {
  await page.goto('/');
  await page.getByRole('banner').waitFor();
  const toggle = page.locator('.header-inner .mobile-menu');
  if ((page.viewportSize()?.width ?? 1280) > 760) {
    await expect(toggle).toBeHidden();
    await expect(page.getByRole('navigation', {name: 'Menu mobile', exact: true})).toHaveCount(0);
    return;
  }

  const destinations = [
    {name: 'Accueil', heading: 'Le goût STC.', container: '.promo-banner'},
    {name: 'Carte', heading: 'À la carte', container: '.catalog-section'},
    {name: 'Favoris', heading: 'Mes favoris', container: '.catalog-section'},
    {name: 'Commandes', heading: 'Mes commandes', container: '.orders-page'},
    {name: 'Compte', heading: 'Mon espace gourmand', container: '.account-page'},
  ];
  let active = 'Accueil';
  for (const destination of destinations) {
    await toggle.click();
    const menu = page.getByRole('navigation', {name: 'Menu mobile', exact: true});
    await expect(menu.getByRole('button')).toHaveCount(5);
    await expect(menu.locator('[aria-current="page"]')).toHaveCount(1);
    await expect(menu.getByRole('button', {name: active, exact: true})).toHaveAttribute('aria-current', 'page');
    await menu.getByRole('button', {name: destination.name, exact: true}).click();
    await expect(menu).toHaveCount(0);
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator(destination.container).getByRole('heading', {name: destination.heading, exact: true})).toBeVisible();
    active = destination.name;
  }
});

test('le menu se ferme dehors, rend le focus avec Échap et reste utilisable en petite hauteur', async ({page}) => {
  await page.setViewportSize({width: 390, height: 260});
  await page.goto('/');
  await page.getByRole('banner').waitFor();
  const toggle = page.locator('.header-inner .mobile-menu');
  const menu = page.getByRole('navigation', {name: 'Menu mobile', exact: true});

  await toggle.focus();
  await page.keyboard.press('Enter');
  await expect(menu.getByRole('button', {name: 'Accueil', exact: true})).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);
  await expect(toggle).toBeFocused();

  await toggle.click();
  await expect(menu).toBeVisible();
  await page.mouse.click(4, 120);
  await expect(menu).toHaveCount(0);

  await toggle.click();
  await expect(menu).toBeVisible();
  const search = page.getByRole('textbox', {name: 'Rechercher un plat'});
  await search.focus();
  await expect(menu).toHaveCount(0);
  await expect(search).toBeFocused();

  await page.getByRole('navigation', {name: 'Navigation principale', exact: true})
    .getByRole('button', {name: 'Compte', exact: true}).click();
  await toggle.click();
  const account = menu.getByRole('button', {name: 'Compte', exact: true});
  await expect(account).toHaveAttribute('aria-current', 'page');
  await expect(account).toBeFocused();
  await expect.poll(() => account.evaluate(el => {
    const target = el.getBoundingClientRect();
    const panel = el.closest('nav')!.getBoundingClientRect();
    return target.top >= panel.top && target.bottom <= panel.bottom;
  })).toBe(true);
  expect(await menu.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);

  await page.setViewportSize({width: 768, height: 1024});
  await expect(toggle).toBeHidden();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('#mobile-menu')).toHaveCount(0);
  await page.setViewportSize({width: 390, height: 844});
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
