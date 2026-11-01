import {expect, test, type Page} from '@playwright/test';
import type {Product, RestaurantSettings} from '../src/types';

const regular: Product[] = [
  {id: 1, name: 'Le Bucket STC', category: 'Poulet', description: 'Poulet et frites.', image: 'stc-menu-1', price: 11.9},
  {id: 2, name: 'Le Menu Original', category: 'Menus', description: 'Burger, frites et boisson.', image: 'stc-menu-2', price: 15.9},
  {id: 8, name: 'Le Spicy Chicken', category: 'Burgers', description: 'Poulet et sauce épicée.', image: 'spicy', price: 12.5, discountPercent: 75},
  {id: 5, name: 'Le Veggie Garden', category: 'Burgers', description: 'Burger végétal.', image: 'veggie', price: 10.9, vegetarian: true},
  {id: 4, name: 'Les Frites Cheddar', category: 'Accompagnements', description: 'Frites et cheddar.', image: 'fries', price: 5.5, vegetarian: true},
  {id: 6, name: 'Le Cookie Choco', category: 'Desserts', description: 'Cookie au chocolat.', image: 'dessert', price: 3.9, vegetarian: true},
  {id: 4004, name: 'La Salade Fraîcheur', category: 'Salades', description: 'Salade croquante.', image: 'veggie', price: 8.5, vegetarian: true},
];
const promotions: Product[] = [
  {...regular[1], id: 90, name: 'Menu Original — Offre du moment', price: 11.13, promotional: true, discountPercent: 30},
  {...regular[1], id: 91, name: 'Menu Original — Offre spéciale', price: 9.54, promotional: true, discountPercent: 40},
  {...regular[2], id: 92, name: 'Offre Burger indisponible', price: 1, promotional: true, discountPercent: 99, available: false},
];
const restaurant: RestaurantSettings = {
  name: 'STC', address: '24 rue du Test', city: 'Paris', hours: '11h30 – 23h', days: 'Tous les jours',
  deliveryFee: 3.9, minDeliveryTotal: 15, deliveryPostalCodes: ['75011'],
  orderingEnabled: true, isOpen: true, demoMode: true, paymentMode: 'simulation',
};

async function openCatalogue(page: Page, products: Product[], failProducts = false) {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/products/' && failProducts) {
      await route.fulfill({status: 503, json: {detail: 'Service temporairement indisponible.'}});
      return;
    }
    const data = path === '/api/products/' ? products
      : path === '/api/restaurant/' ? restaurant
      : path === '/api/categories/' ? [...new Set(products.filter(product => !product.promotional).map(product => product.category))].map((name, position) => ({name, position}))
      : path === '/api/auth/me/' ? {user: null} : [];
    await route.fulfill({json: data});
  });
  await page.goto('/');
}

async function selectCategory(page: Page, category: string) {
  await page.getByRole('group', {name: 'Catégories', exact: true})
    .getByRole('button', {name: category, exact: true}).click();
}

async function expectSelection(page: Page, name: string, price: string, image: string) {
  const banner = page.locator('.offer');
  await expect(banner.getByRole('heading', {name, exact: true})).toBeVisible();
  await expect(banner).toContainText(price);
  await expect(banner.locator('.offer-discount')).toHaveCount(0);
  await expect(banner.locator('.offer-food')).toHaveAttribute('src', `/images/${image}.jpg`);
}

test('la bannière suit la catégorie, la vraie meilleure remise et le produit de son bouton', async ({page}) => {
  await openCatalogue(page, [...regular, ...promotions]);
  const banner = page.locator('.offer');
  await expect(banner.locator('h2')).toHaveText('Jusqu’à −40 %');
  await expect(banner.locator('.offer-discount')).toContainText('40');
  await banner.getByRole('button', {name: 'Commander Menu Original — Offre spéciale', exact: true}).click();
  await expect(page.getByRole('dialog', {name: 'Menu Original — Offre spéciale', exact: true})).toBeVisible();
  await page.keyboard.press('Escape');

  await selectCategory(page, 'Menus');
  await expect(banner.locator('h2')).toHaveText('Jusqu’à −40 %');
  await expect(banner.locator('.offer-food')).toHaveAttribute('src', '/images/stc-menu-2.jpg');
  await selectCategory(page, 'Burgers');
  await expectSelection(page, 'Le Spicy Chicken', '12,50', 'spicy');
  await banner.getByRole('button', {name: 'Commander Le Spicy Chicken', exact: true}).click();
  await expect(page.getByRole('dialog', {name: 'Le Spicy Chicken', exact: true})).toBeVisible();
  await page.keyboard.press('Escape');
  await selectCategory(page, 'Poulet');
  await expectSelection(page, 'Le Bucket STC', '11,90', 'stc-menu-1');
  await selectCategory(page, 'Salades');
  await expectSelection(page, 'La Salade Fraîcheur', '8,50', 'veggie');

  await selectCategory(page, 'Burgers');
  await page.getByRole('button', {name: 'Afficher les filtres'}).click();
  await page.getByRole('combobox', {name: 'Trier les produits'}).selectOption('price');
  await expectSelection(page, 'Le Veggie Garden', '10,90', 'veggie');
  await selectCategory(page, 'Tout');
  await expect(banner.locator('h2')).toHaveText('Jusqu’à −40 %');
  await page.getByRole('button', {name: 'Voir tout', exact: true}).click();
  await expect(banner).toBeVisible();
  await page.getByRole('textbox', {name: 'Rechercher un plat'}).fill('Spicy');
  await expect(banner).toHaveCount(0);
  await page.getByRole('button', {name: 'Effacer la recherche'}).click();
  await expect(banner).toBeVisible();
});

test('la sélection respecte végétarien et disponibilité sans attribuer de fausse remise', async ({page}) => {
  const meatOffer = {...regular[2], id: 93, name: 'Offre Spicy', price: 1.25, promotional: true, discountPercent: 90};
  const unavailableVeggie = {...regular[3], id: 94, name: 'Offre Veggie indisponible', price: 1, promotional: true, discountPercent: 99, available: false};
  await openCatalogue(page, [...regular, ...promotions, meatOffer, unavailableVeggie]);
  await expect(page.locator('.offer h2')).toHaveText('Jusqu’à −90 %');
  await page.getByRole('button', {name: 'Afficher les filtres'}).click();
  await page.getByLabel('Végétarien', {exact: true}).check();
  await expectSelection(page, 'Le Veggie Garden', '10,90', 'veggie');
  await selectCategory(page, 'Burgers');
  await expectSelection(page, 'Le Veggie Garden', '10,90', 'veggie');
  await selectCategory(page, 'Poulet');
  await expect(page.locator('.offer')).toHaveCount(0);
  await selectCategory(page, 'Desserts');
  await expectSelection(page, 'Le Cookie Choco', '3,90', 'dessert');
});

test('la bannière disparaît sans produit éligible ou en cas de chargement impossible', async ({page}) => {
  await openCatalogue(page, [...regular.map(product => ({...product, available: false})), ...promotions.map(product => ({...product, available: false}))]);
  await expect(page.locator('.product-card').first()).toBeVisible();
  await expect(page.locator('.offer')).toHaveCount(0);
  await page.unroute('**/api/**');
  await openCatalogue(page, [], true);
  await expect(page.getByRole('alert')).toContainText('La carte n’a pas pu être chargée.');
  await expect(page.locator('.offer')).toHaveCount(0);
});
