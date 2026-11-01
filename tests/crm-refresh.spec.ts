import {readFile} from 'node:fs/promises';
import {expect, test} from '@playwright/test';

test.use({reducedMotion: 'reduce'});

const initialPage = `<!doctype html><html lang="fr"><meta charset="utf-8"><body>
<div class="crm-app">
  <div><p data-refresh-status role="status"></p><button data-refresh-button>Actualiser</button></div>
  <div data-refresh-fragment="/crm-refresh-fragment/" data-fragment-name="orders">
    <div data-crm-updated-at="2026-11-01T10:00:00Z">
      <form data-submit-lock action="/action" method="post"><button id="prepare" type="submit">Préparer</button></form>
      <p id="order-content">Commande initiale</p>
    </div>
  </div>
</div></body></html>`;
const updatedFragment = '<div data-crm-updated-at="2026-11-01T10:01:00Z"><p id="order-content">Commandes actualisées</p></div>';

const scenarios = [
  {name: 'garde le focus acquis pendant une actualisation lente', kind: 'focus'},
  {name: 'conserve une action en cours pendant une actualisation lente', kind: 'post'},
  {name: 'actualise les commandes lorsque personne ne les manipule', kind: 'idle'},
] as const;

for (const scenario of scenarios) {
  test(`le CRM ${scenario.name}`, async ({page}) => {
    const source = await readFile(new URL('../backend/shop/static/shop/crm.js', import.meta.url), 'utf8');
    let releaseResponse = () => {};
    let requestSeen = false;
    const responseGate = new Promise<void>(resolve => {releaseResponse = resolve;});
    await page.route('**/crm-refresh-fixture/', route => route.fulfill({contentType: 'text/html; charset=utf-8', body: initialPage}));
    await page.route('**/crm-refresh-fragment/', async route => {
      requestSeen = true;
      await responseGate;
      await route.fulfill({contentType: 'text/html; charset=utf-8', headers: {'X-STC-Fragment': 'orders'}, body: updatedFragment});
    });

    try {
      await page.goto('/crm-refresh-fixture/');
      await page.addScriptTag({content: source});
      await page.evaluate(() => window.dispatchEvent(new Event('focus')));
      await expect.poll(() => requestSeen).toBe(true);

      if (scenario.kind === 'focus') {
        await page.getByRole('button', {name: 'Préparer', exact: true}).focus();
      } else if (scenario.kind === 'post') {
        await page.evaluate(() => {
          // Keep the page in place after the real submit handler locks the action.
          document.addEventListener('submit', event => event.preventDefault());
          const button = document.querySelector<HTMLButtonElement>('#prepare')!;
          button.focus();
          button.form!.requestSubmit(button);
          button.blur();
        });
        await expect(page.locator('#prepare')).toHaveAttribute('aria-busy', 'true');
        expect(await page.evaluate(() => document.activeElement?.id)).not.toBe('prepare');
      }

      releaseResponse();
      await expect(page.getByRole('button', {name: 'Actualiser', exact: true})).toBeEnabled();
      if (scenario.kind === 'idle') {
        await expect(page.locator('#order-content')).toHaveText('Commandes actualisées');
      } else {
        await expect(page.locator('#order-content')).toHaveText('Commande initiale');
        if (scenario.kind === 'focus') {
          await expect(page.getByRole('button', {name: 'Préparer', exact: true})).toBeFocused();
        } else {
          await expect(page.locator('#prepare')).toHaveAttribute('aria-busy', 'true');
        }
      }
    } finally {
      releaseResponse();
    }
  });
}
