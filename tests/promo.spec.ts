import {expect, test} from '@playwright/test';

test('les promotions au clavier ouvrent le bon plat et le menu peut être ajouté au panier', async ({page}) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  const carousel = page.getByRole('region', {name: 'Nos promotions'});
  const slides = [
    {heading: 'Le goût STC.', product: 'Le Bucket STC'},
    {heading: 'À partager.', product: 'Les Crispy Tenders'},
    {heading: 'Menu complet.', product: 'Le Menu Original'},
  ];

  for (const [index, slide] of slides.entries()) {
    const pager = carousel.getByRole('button', {name: `Promotion ${index + 1}`, exact: true});
    await pager.focus();
    await page.keyboard.press('Enter');
    await expect(pager).toHaveAttribute('aria-current', 'true');
    await expect(carousel.getByRole('heading', {name: slide.heading, exact: true})).toBeVisible();
    await carousel.getByRole('button', {name: 'Commander', exact: true}).click();
    const dialog = page.getByRole('dialog', {name: slide.product, exact: true});
    await expect(dialog).toBeVisible();

    if (index === 2) {
      await dialog.getByRole('radio', {name: 'Cola 33 cl'}).check();
      await dialog.getByRole('button', {name: 'Ajouter · 15,90 €', exact: true}).click();
      await expect(dialog).toHaveCount(0);
      await page.getByRole('button', {name: /Mon panier/}).click();
      await expect(page.getByRole('dialog').getByRole('heading', {name: slide.product, exact: true})).toBeVisible();
      await expect(page.getByRole('dialog').getByText('Cola 33 cl', {exact: false})).toBeVisible();
    } else {
      await page.keyboard.press('Escape');
      await expect(dialog).toHaveCount(0);
    }
  }
  expect(errors).toEqual([]);
});
