import {expect, test, type Page} from '@playwright/test';
import type {Order, Product, RestaurantSettings, User} from '../src/types';

// Only catalogue/session fixtures are used here. Full order and account
// regressions run separately against scripts/e2e.py's disposable database.
const menu: Product = {
  id: 2, name: 'Le Menu Original', category: 'Menus', price: 15.9,
  description: 'Burger de poulet croustillant, frites et boisson au choix.',
  summary: 'Burger poulet + frites + boisson.', image: 'stc-menu-2', badge: 'LE BON PLAN',
  optionGroups: [{id: 'drink', name: 'Votre boisson', min: 1, max: 1,
    choices: [{id: 'drink-cola', name: 'Cola 33 cl', price: 0}]},
  {id: 'extras', name: 'Vos suppléments', min: 0, max: 1,
    choices: [{id: 'extra-cheddar', name: 'Cheddar', price: 1}]}],
};
const catalogue: Product[] = [
  {id: 1, name: 'Le Bucket STC', category: 'Poulet', price: 11.9,
    description: 'Poulet croustillant, frites et sauce.', image: 'stc-menu-1', badge: 'BEST-SELLER'},
  menu,
  {id: 3, name: 'Les Crispy Tenders', category: 'Poulet', price: 9.9,
    description: 'Tenders de poulet et sauce maison.', image: 'stc-menu-3', badge: 'FAIT MAISON'},
  {id: 4, name: 'Les Frites Cheddar', category: 'Accompagnements', price: 5.5,
    description: 'Frites dorées et cheddar.', image: 'fries'},
  {id: 5, name: 'Le Veggie Garden', category: 'Burgers', price: 10.9,
    description: 'Galette végétale, avocat et salade.', image: 'veggie', vegetarian: true},
  {id: 6, name: 'Le Cookie Choco', category: 'Desserts', price: 3.9,
    description: 'Cookie au chocolat.', image: 'dessert'},
  {id: 7, name: 'Le Cola Frais', category: 'Boissons', price: 2.5,
    description: 'Boisson fraîche.', image: 'drink'},
  {id: 8, name: 'Le Spicy Chicken', category: 'Burgers', price: 12.5,
    description: 'Poulet croustillant et sauce épicée.', image: 'spicy'},
  {id: 9, name: 'Les Frites Nature', category: 'Accompagnements', price: 3,
    description: 'Frites dorées et croustillantes.', image: 'fries'},
];
const settings: RestaurantSettings = {
  name: 'STC', address: 'Adresse de recette', city: 'Paris', hours: '11h30 – 23h00', days: 'Tous les jours',
  deliveryFee: 3.9, minDeliveryTotal: 0, deliveryPostalCodes: ['75011'],
  orderingEnabled: true, isOpen: true, demoMode: true, paymentMode: 'simulation',
  pickupEnabled: true, deliveryEnabled: true,
};
const customer: User = {id: 77, name: 'Camille Desktop', email: 'desktop-fixture@example.invalid', phone: '06 12 34 56 78'};
const order: Order = {
  id: 'STC-DESKTOP-RECETTE', date: '2026-11-01T12:30:00Z', total: 15.9, subtotal: 15.9,
  deliveryFee: 0, mode: 'À emporter', items: ['Le Menu Original'], status: 'ready',
  paymentMethod: 'simulation', paymentStatus: 'simulated', demoMode: true,
  lines: [{name: 'Le Menu Original', quantity: 1, unitPrice: 15.9, total: 15.9, choices: ['Cola 33 cl']}],
  history: [{status: 'confirmed', date: '2026-11-01T12:30:00Z'}, {status: 'ready', date: '2026-11-01T12:40:00Z'}],
};

async function fixtures(page: Page, products = catalogue, signedIn = false) {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const data = path === '/api/products/' ? products
      : path === '/api/categories/' ? ['Menus', 'Burgers', 'Poulet', 'Accompagnements', 'Boissons', 'Desserts'].map((name, position) => ({name, position}))
      : path === '/api/restaurant/' ? settings
      : path === '/api/auth/me/' ? {user: signedIn ? customer : null}
      : path === '/api/auth/capabilities/' ? {passwordResetAvailable: false}
      : path === '/api/addresses/' ? [{id: 1, label: 'Maison', name: customer.name, phone: customer.phone,
        address: '24 rue de la Recette', postal: '75011', city: 'Paris'}]
      : path === '/api/favorites/' ? [1, 2]
      : path === '/api/orders/' ? [order] : {detail: 'Réponse de recette.'};
    await route.fulfill({json: data});
  });
}

async function ready(page: Page) {
  await page.goto('/');
  await expect(page.locator('.product-grid .product-card').first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

async function noHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test('desktop : accueil de six plats, catégories visibles et grille de deux ou trois colonnes', async ({page}, info) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.emulateMedia({reducedMotion: 'reduce'});
  await fixtures(page);
  for (const width of [1025, 1280, 1440, 1920]) {
    await page.setViewportSize({width, height: 1000});
    await ready(page);
    const navigation = page.getByRole('navigation', {name: 'Navigation ordinateur'});
    await expect(navigation).toBeVisible();
    await expect(navigation.getByRole('button')).toHaveCount(3);
    await expect(page.getByRole('navigation', {name: 'Navigation principale'})).toBeHidden();
    await expect(page.locator('.product-grid .product-card')).toHaveCount(6);
    const banner = page.getByRole('region', {name: 'Nos promotions'});
    const hero = await banner.boundingBox();
    expect(hero?.height).toBeGreaterThanOrEqual(260);
    expect(hero?.height).toBeLessThanOrEqual(420);
    const categories = page.getByRole('group', {name: 'Catégories', exact: true});
    await expect(categories.getByRole('button')).toHaveCount(7);
    expect(await categories.evaluate(rail => {
      const frame = rail.getBoundingClientRect();
      return Array.from(rail.querySelectorAll('button')).every(button => {
        const rect = button.getBoundingClientRect();
        return rect.left >= frame.left - 1 && rect.right <= frame.right + 1 && rect.width >= 44 && rect.height >= 44;
      });
    })).toBe(true);
    await noHorizontalOverflow(page);
    await page.screenshot({path: info.outputPath(`accueil-${width}.png`), fullPage: true});

    await page.getByRole('button', {name: 'Voir tout', exact: true}).click();
    await expect(page.locator('.product-card')).toHaveCount(catalogue.length);
    const layout = await page.locator('.product-grid').evaluate(grid => {
      const cards = Array.from(grid.querySelectorAll('.product-card'));
      const firstTop = cards[0].getBoundingClientRect().top;
      return cards.map(card => {
        const rect = card.getBoundingClientRect();
        const media = card.querySelector('.card-media')!.getBoundingClientRect();
        const body = card.querySelector('.card-body')!.getBoundingClientRect();
        const price = card.querySelector('.card-price')!.getBoundingClientRect();
        const action = card.querySelector('.card-add,.card-choose')!.getBoundingClientRect();
        return {
          firstRow: Math.abs(rect.top - firstTop) < 2, width: rect.width, height: rect.height,
          horizontal: media.right <= body.left + 1,
          foodShare: media.width / rect.width,
          actionsContained: price.left >= body.left && price.right <= action.left + 1 && action.right <= rect.right + 1
            && action.bottom <= rect.bottom + 1,
          touchTarget: action.width >= 44 && action.height >= 44,
          noOverflow: card.scrollWidth <= card.clientWidth,
        };
      });
    });
    expect(layout.filter(card => card.firstRow)).toHaveLength(width >= 1440 ? 3 : 2);
    expect(Math.max(...layout.map(card => card.height)) - Math.min(...layout.map(card => card.height))).toBeLessThan(2);
    expect(Math.max(...layout.map(card => card.width)) - Math.min(...layout.map(card => card.width))).toBeLessThan(2);
    expect(layout.every(card => card.horizontal && card.foodShare > .38 && card.foodShare < .49
      && card.actionsContained && card.touchTarget && card.noOverflow), `${width}px: cartes accessibles`).toBe(true);
    await noHorizontalOverflow(page);
    await page.screenshot({path: info.outputPath(`carte-${width}.png`), fullPage: true});
  }
  expect(errors).toEqual([]);
});

test('desktop : fiche produit en deux colonnes, choix au clavier et panier avec récapitulatif séparé', async ({page}, info) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await fixtures(page);
  for (const width of [1280, 1920]) {
    await page.setViewportSize({width, height: 1000});
    await ready(page);
    const opener = page.getByRole('button', {name: 'Choisir Le Menu Original', exact: true});
    await opener.focus();
    await page.keyboard.press('Enter');
    const detail = page.getByRole('dialog', {name: 'Le Menu Original', exact: true});
    await expect(detail).toBeFocused();
    const media = await detail.locator('.detail-image').boundingBox();
    const body = await detail.locator('.detail-body').boundingBox();
    expect(media && body && media.x + media.width <= body.x + 1).toBe(true);
    const frame = await detail.boundingBox();
    expect(frame?.width).toBeGreaterThan(760);
    expect(frame && frame.x >= 16 && frame.x + frame.width <= width - 16).toBe(true);
    await page.keyboard.press('Tab');
    await expect(detail.getByRole('button', {name: 'Fermer', exact: true})).toBeFocused();
    await detail.getByRole('radio', {name: 'Cola 33 cl'}).check();
    await detail.getByRole('button', {name: 'Ajouter · 15,90 €', exact: true}).click();
    await expect(detail).toHaveCount(0);
    await page.getByRole('button', {name: /Mon panier/}).click();
    const cart = page.getByRole('dialog', {name: 'Mon panier', exact: true});
    await expect(cart).toBeVisible();
    expect((await cart.boundingBox())!.width).toBeLessThanOrEqual(700);
    await cart.getByRole('button', {name: 'Augmenter Le Menu Original', exact: true}).click();
    await expect(cart.locator('.quantity>span')).toHaveText('2');
    await cart.getByRole('button', {name: 'Passer commande', exact: true}).click();
    const summary = await cart.locator('.cart-summary').boundingBox();
    const checkout = await cart.locator('form.checkout').boundingBox();
    expect(summary && checkout && summary.x + summary.width <= checkout.x + 1).toBe(true);
    expect((await cart.boundingBox())!.width).toBeGreaterThan(760);
    for (const label of ['Nom complet', 'Adresse e-mail', 'Téléphone']) {
      const input = cart.getByLabel(label, {exact: true});
      await expect(input).toBeVisible();
      expect((await input.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    await noHorizontalOverflow(page);
    await page.screenshot({path: info.outputPath(`panier-${width}.png`), fullPage: true});
    await cart.getByRole('button', {name: 'Supprimer Le Menu Original', exact: true}).click();
    await page.keyboard.press('Escape');
    await expect(cart).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});

test('desktop : noms et options longs avec texte agrandi à150% restent lisibles et commandables', async ({page}, info) => {
  const longName = 'Le Menu Original généreux au poulet croustillant, sélection spéciale du chef';
  const longDrink = 'Limonade artisanale au citron et aux fruits fraîchement pressés';
  const longMenu: Product = {...menu, name: longName,
    optionGroups: [{id: 'drink', name: 'Votre boisson artisanale et rafraîchissante au choix', min: 1, max: 1,
      choices: [{id: 'drink-long', name: longDrink, price: 0}]},
    {id: 'extras', name: 'Vos suppléments de fromage et de légumes croquants', min: 0, max: 1,
      choices: [{id: 'extra-long', name: 'Cheddar affiné et supplément de salade croquante', price: 1}]}]};
  await fixtures(page, catalogue.map(product => product.id === 2 ? longMenu : product));
  for (const width of [1025, 1440, 1920]) {
    await page.setViewportSize({width, height: 1000});
    await ready(page);
    await page.getByRole('button', {name: 'Voir tout', exact: true}).click();
    await page.locator('.product-card').evaluateAll(cards => {
      for (const card of cards) {
        const nodes = Array.from(card.querySelectorAll<HTMLElement>('.card-title,.card-text,.card-options li,.card-price,.card-choose'));
        const sizes = nodes.map(node => parseFloat(getComputedStyle(node).fontSize));
        nodes.forEach((node, index) => {node.style.fontSize = `${sizes[index] * 1.5}px`;});
      }
    });
    const accessible = await page.locator('.product-card').evaluateAll(cards => cards.every(card => {
      const rect = card.getBoundingClientRect();
      const body = card.querySelector('.card-body')!;
      const price = card.querySelector('.card-price')!.getBoundingClientRect();
      const action = card.querySelector('.card-add,.card-choose')!.getBoundingClientRect();
      const separate = price.right <= action.left + 1 || price.bottom <= action.top + 1 || action.bottom <= price.top + 1;
      return card.scrollWidth <= card.clientWidth && body.scrollHeight <= body.clientHeight + 1
        && separate && action.width >= 44 && action.height >= 44
        && action.right <= rect.right + 1 && action.bottom <= rect.bottom + 1;
    }));
    expect(accessible, `${width}px: agrandissement du texte`).toBe(true);
    await page.getByRole('button', {name: `Choisir ${longName}`, exact: true}).click();
    const detail = page.getByRole('dialog', {name: longName, exact: true});
    await detail.locator('.detail-body').evaluate(body => {
      const nodes = Array.from(body.querySelectorAll<HTMLElement>('h2,p,legend,.option'));
      const sizes = nodes.map(node => parseFloat(getComputedStyle(node).fontSize));
      nodes.forEach((node, index) => {node.style.fontSize = `${sizes[index] * 1.5}px`;});
    });
    await detail.getByRole('radio', {name: longDrink}).check();
    await expect(detail.getByRole('button', {name: 'Ajouter · 15,90 €', exact: true})).toBeEnabled();
    expect(await detail.evaluate(dialog => dialog.scrollWidth <= dialog.clientWidth)).toBe(true);
    await noHorizontalOverflow(page);
    await page.screenshot({path: info.outputPath(`texte-150-${width}.png`), fullPage: true});
    await page.keyboard.press('Escape');
  }
});

test('desktop : compte, suivi et favoris utilisent la largeur sans champs ni actions masqués', async ({page}, info) => {
  await fixtures(page, catalogue, true);
  for (const width of [1025, 1280, 1920]) {
    await page.setViewportSize({width, height: 1000});
    await ready(page);
    const header = page.locator('.site-header');
    await header.getByRole('button', {name: 'Mon compte', exact: true}).click();
    const profile = page.locator('.profile-card');
    await expect(profile).toBeVisible();
    await expect(page.locator('.saved-address')).toHaveCount(1);
    await expect(profile.getByLabel('Nom du compte', {exact: true})).toHaveValue(customer.name);
    const profileBox = (await profile.boundingBox())!;
    const addressBox = (await page.locator('.address-card').boundingBox())!;
    const pageBox = (await page.locator('.account-page').boundingBox())!;
    const greetingBox = (await page.locator('.account-card:has(.account-heading)').boundingBox())!;
    const deletionBox = (await page.locator('.delete-card').boundingBox())!;
    expect(Math.abs(profileBox.y - addressBox.y), `${width}px: profil et adresses partagent une rangée`).toBeLessThan(2);
    expect(profileBox.x + profileBox.width).toBeLessThanOrEqual(addressBox.x - 8);
    expect(greetingBox.width).toBeGreaterThanOrEqual(pageBox.width - 2);
    expect(deletionBox.width).toBeGreaterThanOrEqual(pageBox.width - 2);
    for (const input of await profile.locator('input').all()) {
      const rect = await input.boundingBox();
      expect(rect!.height).toBeGreaterThanOrEqual(44);
      expect(await input.evaluate(node => parseFloat(getComputedStyle(node).fontSize))).toBeGreaterThanOrEqual(14);
    }
    await noHorizontalOverflow(page);
    await page.screenshot({path: info.outputPath(`compte-${width}.png`), fullPage: true});
    await header.getByRole('button', {name: 'Commandes', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'Mes commandes', exact: true})).toBeVisible();
    await expect(page.locator('.order-card')).toHaveCount(1);
    await expect(page.locator('.order-card')).toContainText('Cola 33 cl');
    await noHorizontalOverflow(page);
    await page.screenshot({path: info.outputPath(`commandes-${width}.png`), fullPage: true});
    await header.getByRole('button', {name: 'Mes favoris', exact: true}).click();
    await expect(page.getByRole('heading', {name: 'Mes favoris', exact: true})).toBeVisible();
    await expect(page.locator('.product-card')).toHaveCount(2);
    await noHorizontalOverflow(page);
    const footer = page.getByRole('contentinfo', {name: 'Informations STC'});
    await footer.scrollIntoViewIfNeeded();
    await expect(footer.getByRole('button', {name: 'Questions fréquentes', exact: true})).toBeVisible();
    await footer.getByRole('button', {name: 'Questions fréquentes', exact: true}).click();
    await expect(page.getByRole('dialog', {name: 'Une question ? On vous répond.', exact: true})).toBeVisible();
    await page.keyboard.press('Escape');
  }
});
