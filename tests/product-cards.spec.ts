import {expect, test, type Page} from '@playwright/test';
import type {Product, RestaurantSettings} from '../src/types';

const products: Product[] = [
  {
    id: 1, name: 'Le Bucket STC', category: 'Poulet', price: 11.9,
    description: '4 morceaux de poulet croustillant, frites et sauce au choix.',
    summary: '4 morceaux + frites + sauce au choix.', image: 'stc-menu-1', badge: 'BEST-SELLER',
  },
  {
    id: 2, name: 'Le Menu Original', category: 'Menus', price: 15.9,
    description: 'Burger poulet croustillant, frites et boisson au choix.',
    summary: 'Burger poulet + frites + boisson.', image: 'stc-menu-2', badge: 'LE BON PLAN',
    optionGroups: [{
      id: 'drink', name: 'Votre boisson', min: 1, max: 1,
      choices: [{id: 'drink-cola', name: 'Cola 33 cl', price: 0}],
    }, {
      id: 'extras', name: 'Vos suppléments', min: 0, max: 1,
      choices: [{id: 'extra-cheddar', name: 'Cheddar', price: 1}],
    }],
  },
  {
    id: 3, name: 'Les Crispy Tenders', category: 'Poulet', price: 9.9,
    description: '5 tenders de poulet marinés, panure croustillante et sauce.',
    summary: '5 tenders de poulet + sauce au choix.', image: 'stc-menu-3', badge: 'FAIT MAISON',
  },
  {
    id: 4, name: 'Les Frites Cheddar', category: 'Accompagnements', price: 5.5,
    description: 'Frites dorées et cheddar fondant.', image: 'fries', available: false,
  },
  {
    id: 5, name: 'Le Veggie Garden', category: 'Burgers', price: 10.9,
    description: 'Galette végétale, avocat, salade croquante et sauce aux herbes.',
    image: 'veggie', vegetarian: true,
  },
  {
    id: 8, name: 'Le Spicy Chicken', category: 'Burgers', price: 12.5,
    description: 'Poulet croustillant, coleslaw frais et sauce légèrement épicée.',
    image: 'spicy', badge: 'ÇA PIQUE !', vegetarian: false,
  },
];
const settings: RestaurantSettings = {
  name: 'STC', address: '24 rue du Test', city: 'Paris', hours: '11h30 – 23h', days: 'Tous les jours',
  deliveryFee: 3.9, minDeliveryTotal: 15, deliveryPostalCodes: ['75011'],
  orderingEnabled: true, isOpen: true, demoMode: true, paymentMode: 'simulation',
};

// Read-only catalogue fixtures keep these UI regressions independent of local restaurant data.
async function openCatalogue(page: Page, catalogue = products) {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const data = path === '/api/products/' ? catalogue
      : path === '/api/restaurant/' ? settings
      : path === '/api/categories/' ? [{name: 'Menus', position: 0}, {name: 'Poulet', position: 1}]
      : path === '/api/auth/me/' ? {user: null} : [];
    await route.fulfill({json: data});
  });
  await page.goto('/');
  await expect(page.locator('.product-grid').getByRole('heading', {name: 'Le Bucket STC', exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Voir tout', exact: true}).click();
  await expect(page.locator('.product-card')).toHaveCount(catalogue.length);
  await page.evaluate(() => document.fonts.ready);
}

test('sur mobile chaque carte occupe sa ligne, avec photo, prix et action accessibles', async ({page}) => {
  await page.emulateMedia({reducedMotion: 'reduce'});
  await openCatalogue(page);
  for (const width of [320, 390, 760, 768, 820, 900, 901, 1024]) {
    await page.setViewportSize({width, height: 900});
    const rows = await page.locator('.product-grid').evaluate(grid => {
      const gridRect = grid.getBoundingClientRect();
      const cards = Array.from(grid.querySelectorAll('.product-card'));
      const firstHeight = cards[0].getBoundingClientRect().height;
      return cards.map(card => {
        const rect = card.getBoundingClientRect();
        const media = card.querySelector('.card-media')!.getBoundingClientRect();
        const body = card.querySelector('.card-body')!.getBoundingClientRect();
        const price = card.querySelector('.card-price')!.getBoundingClientRect();
        const action = card.querySelector('.card-add,.card-choose')!.getBoundingClientRect();
        return {
          fullWidth: Math.abs(rect.width - gridRect.width) < 2,
          sameHeight: Math.abs(rect.height - firstHeight) < 1,
          halfWidthPhotoColumn: Math.abs(body.left - (rect.left + rect.width / 2)) < 2,
          horizontal: media.right <= price.left + 1,
          priceAndActionFit: price.right <= action.left && action.right <= rect.right,
          actionTouchTarget: action.width >= 44 && action.height >= 44,
          noOverflow: card.scrollWidth <= card.clientWidth,
        };
      });
    });
    expect(rows.every(row => Object.values(row).every(Boolean)), `${width}px card layout`).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test('le gabarit mobile reste identique en filtrant menus, burgers, poulet ou accompagnements', async ({page}) => {
  await page.emulateMedia({reducedMotion: 'reduce'});
  await openCatalogue(page);
  test.setTimeout(90_000);
  for (const width of [320, 360, 364, 365, 375, 387, 388, 390, 395, 396, 400, 430, 600, 760, 761, 768, 820, 900, 901, 1024]) {
    await page.setViewportSize({width, height: 1000});
    const heights: number[] = [];
    const titleOffsets: number[] = [];
    for (const category of ['Menus', 'Burgers', 'Poulet', 'Accompagnements']) {
      await page.getByRole('group', {name: 'Catégories', exact: true})
        .getByRole('button', {name: category, exact: true}).click();
      const cards = await page.locator('.product-card').evaluateAll(cards => cards.map(card => {
        const rect = card.getBoundingClientRect();
        const media = card.querySelector('.card-media')!;
        const body = card.querySelector('.card-body')!.getBoundingClientRect();
        const title = card.querySelector('.card-title')!.getBoundingClientRect();
        const price = card.querySelector('.card-price')!.getBoundingClientRect();
        const action = card.querySelector('.card-add,.card-choose')!.getBoundingClientRect();
        return {
          height: rect.height,
          titleOffset: title.top - rect.top,
          halfWidthPhoto: Math.abs(body.left - (rect.left + rect.width / 2)) < 2,
          photoFrame: getComputedStyle(media).margin === '4px 0px 4px 4px',
          actionFits: price.right <= action.left && action.right <= rect.right,
          touchTarget: action.width >= 44 && action.height >= 44,
          noOverflow: card.scrollWidth <= card.clientWidth,
        };
      }));
      expect(cards.length).toBeGreaterThan(0);
      expect(cards.every(({height: _height, titleOffset: _titleOffset, ...checks}) => Object.values(checks).every(Boolean))).toBe(true);
      heights.push(...cards.map(card => card.height));
      titleOffsets.push(...cards.map(card => card.titleOffset));
      if (category === 'Menus') await expect(page.locator('.card-options')).toBeVisible();
      if (category === 'Accompagnements') {
        await expect(page.locator('.card-badge-spacer')).toHaveAttribute('aria-hidden', 'true');
        await expect(page.locator('.card-badge-spacer')).toHaveText('');
      }
    }
    expect(Math.max(...heights) - Math.min(...heights), `${width}px filtered category heights`).toBeLessThan(1);
    expect(Math.max(...titleOffsets) - Math.min(...titleOffsets), `${width}px title alignment`).toBeLessThan(1);
  }
});

test('la carte conserve sa forme et grandit sans s’aplatir du mobile à la tablette', async ({page}) => {
  await page.emulateMedia({reducedMotion: 'reduce'});
  await openCatalogue(page);
  let previous: {width: number; height: number} | undefined;
  let referenceRatio: number | undefined;
  for (const width of [320, 360, 364, 365, 375, 387, 388, 390, 395, 396, 400, 430, 600, 760, 761, 768, 820, 900, 901, 1024]) {
    await page.setViewportSize({width, height: 1000});
    const shape = await page.locator('.formula-card').evaluate(card => {
      const rect = card.getBoundingClientRect();
      return {width: rect.width, height: rect.height};
    });
    if (previous) {
      expect(shape.width, `${width}px: la carte ne rétrécit pas au seuil responsive`).toBeGreaterThanOrEqual(previous.width - 1);
      expect(shape.height, `${width}px: agrandir l’écran n’aplatit pas la carte`).toBeGreaterThanOrEqual(previous.height - 1);
    }
    // Small screens may grow to fit their text and 44px controls. Once that
    // minimum is no longer needed, the visible shape must remain proportional.
    if (width >= 390) {
      const ratio = shape.width / shape.height;
      if (referenceRatio === undefined) referenceRatio = ratio;
      expect(ratio, `${width}px: une carte horizontale conserve les proportions du mobile de référence`).toBeGreaterThan(2.2);
      expect(ratio).toBeLessThan(2.5);
      expect(Math.abs(ratio - referenceRatio), `${width}px: aucune déformation avec la largeur`).toBeLessThan(0.04);
    }
    previous = shape;
  }
});

test('un nom long et une simulation de texte agrandi à 200 % restent consultables', async ({page}) => {
  await page.emulateMedia({reducedMotion: 'reduce'});
  const longMenuName = 'Le Menu Original généreux au poulet croustillant, sélection spéciale du chef';
  const catalogue = products.map(product => product.id === 2 ? {
    ...product,
    name: longMenuName,
    description: 'Burger poulet croustillant avec une grande portion de frites et une boisson au choix pour votre repas.',
    summary: 'Burger poulet croustillant, frites et boisson au choix pour votre repas.',
  } : product);
  for (const width of [320, 390, 768, 1024]) {
    await page.setViewportSize({width, height: 1000});
    await openCatalogue(page, catalogue);
    await page.locator('.product-card').evaluateAll(cards => {
      for (const card of cards) {
        const nodes = Array.from(card.querySelectorAll<HTMLElement>('.card-badge,.card-title,.card-text,.card-options li,.card-price,.card-choose'));
        // Capture every computed size before changing inherited styles.
        const originalSizes = nodes.map(node => parseFloat(getComputedStyle(node).fontSize));
        nodes.forEach((node, index) => { node.style.fontSize = `${originalSizes[index] * 2}px`; });
      }
    });
    const checks = await page.locator('.product-card').evaluateAll(cards => cards.map(card => {
      const rect = card.getBoundingClientRect();
      const body = card.querySelector<HTMLElement>('.card-body')!;
      const contents = Array.from(body.children).map(node => node.getBoundingClientRect());
      const action = card.querySelector('.card-add,.card-choose')!.getBoundingClientRect();
      const title = card.querySelector<HTMLElement>('.card-title')!;
      const titleStyle = getComputedStyle(title);
      const range = document.createRange();
      range.selectNodeContents(title.querySelector('button')!);
      const textLines = Array.from(range.getClientRects());
      return {
        name: title.textContent,
        actionDimensions: {width: action.width, height: action.height},
        textContained: contents.every(node => node.left >= rect.left && node.right <= rect.right + 1 && node.top >= rect.top && node.bottom <= rect.bottom + 1),
        bodyFits: body.scrollHeight <= body.clientHeight + 1,
        // Outfit's ink can extend beyond its line box without being clipped.
        // Check the actual text lines against the card that clips its content.
        titleNotClipped: titleStyle.overflow === 'visible' && titleStyle.webkitLineClamp === 'none'
          && textLines.length > 0 && textLines.every(line => line.left >= rect.left && line.right <= rect.right + 1 && line.top >= rect.top && line.bottom <= rect.bottom + 1),
        actionAccessible: action.width >= 44 && action.height >= 44,
        noOverflow: card.scrollWidth <= card.clientWidth,
      };
    }));
    const failures = checks.filter(({name: _name, actionDimensions: _actionDimensions, ...flags}) => !Object.values(flags).every(Boolean));
    expect(failures, `${width}px: texte 200 % contenu`).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.getByRole('button', {name: `Choisir ${longMenuName}`, exact: true}).click();
  await expect(page.getByRole('dialog', {name: longMenuName, exact: true})).toBeVisible();
});

test('favori au clavier, choix du menu et ajout au panier fonctionnent après la refonte', async ({page}) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await openCatalogue(page);
  const favorite = page.getByRole('button', {name: 'Ajouter Le Bucket STC aux favoris', exact: true});
  await favorite.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button', {name: 'Retirer Le Bucket STC des favoris', exact: true})).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(page.getByRole('button', {name: 'Retirer Le Bucket STC des favoris', exact: true})).toBeVisible();
  const choose = page.getByRole('button', {name: 'Choisir Le Menu Original', exact: true});
  await choose.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button', {name: 'Ajouter · 15,90 €', exact: true}).click();
  await expect(dialog.getByRole('alert')).toHaveText('Sélectionnez une option pour continuer.');
  await dialog.getByRole('radio', {name: 'Cola 33 cl'}).check();
  await dialog.getByRole('button', {name: 'Ajouter · 15,90 €', exact: true}).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole('button', {name: /Mon panier/}).click();
  await expect(page.getByRole('dialog').getByRole('heading', {name: 'Le Menu Original', exact: true})).toBeVisible();
  await expect(page.getByRole('dialog').getByText('Cola 33 cl', {exact: false})).toBeVisible();
  expect(errors).toEqual([]);
});

test('un plat indisponible reste consultable et son ajout est désactivé', async ({page}) => {
  await openCatalogue(page);
  const card = page.locator('.product-card').filter({has: page.getByRole('heading', {name: 'Les Frites Cheddar'})});
  await expect(card.getByRole('button', {name: 'Ajouter Les Frites Cheddar', exact: true})).toBeDisabled();
  await expect(card).toContainText(/indisponible/i);
  await card.getByRole('button', {name: 'Personnaliser Les Frites Cheddar', exact: true}).click();
  await expect(page.getByRole('dialog').getByRole('button', {name: 'Ajouter · 5,50 €', exact: true})).toBeDisabled();
});
