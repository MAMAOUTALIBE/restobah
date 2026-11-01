import {readFile} from 'node:fs/promises';
import {expect, test, type Page} from '@playwright/test';

const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9zsAAAAASUVORK5CYII=';
const savedPhoto = `data:image/png;base64,${png}#saved`;
const refusal = 'Choisissez une photo JPEG, PNG ou WebP de 5 Mo maximum.';
const readError = 'La photo ne peut pas être lue. Choisissez un autre fichier.';
const selected = 'Nouvelle photo sélectionnée. Enregistrez le plat pour la publier.';

declare global {
  interface Window {
    photoReaders: Array<{aborted: boolean; emit: (event: 'load' | 'error') => void}>;
  }
}

async function mount(page: Page, saved = true, controlled = true) {
  await page.setContent(`<!doctype html><html lang="fr"><meta charset="utf-8"><body>
    <main class="crm-app"><label>Photo<input name="photo" type="file"></label>
    <div data-photo-preview class="crm-photo-preview${saved ? '' : ' is-empty'}">${saved
      ? `<img alt="Photo enregistrée" src="${savedPhoto}">`
      : '<span><svg aria-hidden="true"></svg><span>Votre photo apparaîtra ici</span></span>'}</div>
    <p data-photo-feedback role="status"></p></main></body></html>`);
  if (controlled) {
    await page.evaluate(imageData => {
      window.photoReaders = [];
      class ControlledReader extends EventTarget {
        static EMPTY = 0;
        static LOADING = 1;
        static DONE = 2;
        readyState = 0;
        result: string | null = null;
        aborted = false;
        fileName = '';

        readAsDataURL(file: File) {
          this.fileName = file.name;
          this.readyState = 1;
          window.photoReaders.push(this);
        }

        abort() {
          this.aborted = true;
          this.readyState = 2;
          this.dispatchEvent(new Event('abort'));
        }

        emit(event: 'load' | 'error') {
          // Deliver even after abort, as if this callback was already queued.
          this.readyState = 2;
          this.result = event === 'load' ? `${imageData}#${this.fileName}` : null;
          this.dispatchEvent(new Event(event));
        }
      }
      Object.defineProperty(window, 'FileReader', {value: ControlledReader});
    }, `data:image/png;base64,${png}`);
  }
  const source = await readFile(new URL('../backend/shop/static/shop/crm.js', import.meta.url), 'utf8');
  await page.addScriptTag({content: source});
  return page.locator('[data-photo-preview]').innerHTML();
}

async function choose(page: Page, name = 'new.png', mimeType = 'image/png', buffer = Buffer.from(png, 'base64')) {
  await page.getByLabel('Photo', {exact: true}).setInputFiles({name, mimeType, buffer});
}

async function emit(page: Page, index: number, event: 'load' | 'error') {
  await page.evaluate(({index, event}) => window.photoReaders[index].emit(event), {index, event});
}

async function expectRestored(page: Page, initial: string, saved: boolean, message: string) {
  await expect(page.locator('[data-photo-preview]')).toHaveJSProperty('innerHTML', initial);
  if (saved) await expect(page.locator('[data-photo-preview]')).not.toHaveClass(/is-empty/);
  else await expect(page.locator('[data-photo-preview]')).toHaveClass(/is-empty/);
  await expect(page.locator('[data-photo-feedback]')).toHaveText(message);
  if (message) await expect(page.locator('[data-photo-feedback]')).toHaveClass(/is-error/);
  else await expect(page.locator('[data-photo-feedback]')).not.toHaveClass(/is-error/);
}

test('la photo courante résiste aux anciens load et error livrés malgré abort', async ({page}) => {
  const initial = await mount(page);
  await choose(page, 'first.png');
  await choose(page, 'second.webp', 'image/webp');
  expect(await page.evaluate(() => window.photoReaders[0].aborted)).toBe(true);
  await emit(page, 0, 'error');
  await emit(page, 0, 'load');
  await expectRestored(page, initial, true, '');

  await emit(page, 1, 'load');
  await emit(page, 0, 'load');
  await emit(page, 0, 'error');
  await expect(page.locator('[data-photo-preview] img')).toHaveAttribute('src', /#second\.webp$/);
  await expect(page.locator('[data-photo-feedback]')).toHaveText(selected);
  await expect(page.locator('[data-photo-feedback]')).not.toHaveClass(/is-error/);
});

for (const finished of [false, true]) {
  for (const action of ['invalid', 'clear'] as const) {
    test(`la photo enregistrée revient après ${action}, lecture ${finished ? 'terminée' : 'en cours'}`, async ({page}) => {
      const initial = await mount(page);
      await choose(page);
      if (finished) await emit(page, 0, 'load');
      if (action === 'invalid') await choose(page, 'notes.txt', 'text/plain');
      else await page.getByLabel('Photo', {exact: true}).setInputFiles([]);
      await emit(page, 0, 'load');
      await emit(page, 0, 'error');
      await expectRestored(page, initial, true, action === 'invalid' ? refusal : '');
      expect(await page.evaluate(() => window.photoReaders[0].aborted)).toBe(!finished);
    });
  }
}

for (const action of ['invalid', 'clear'] as const) {
  test(`le placeholder revient après ${action} sans photo enregistrée`, async ({page}) => {
    const initial = await mount(page, false);
    await choose(page);
    await emit(page, 0, 'load');
    if (action === 'invalid') await choose(page, 'notes.txt', 'text/plain');
    else await page.getByLabel('Photo', {exact: true}).setInputFiles([]);
    await emit(page, 0, 'error');
    await emit(page, 0, 'load');
    await expectRestored(page, initial, false, action === 'invalid' ? refusal : '');
  });
}

test('une photo dépassant 5 Mo retire le précédent aperçu et conserve le refus', async ({page}) => {
  const initial = await mount(page);
  await choose(page);
  await emit(page, 0, 'load');
  await choose(page, 'too-large.jpg', 'image/jpeg', Buffer.alloc(5 * 1024 * 1024 + 1));
  await emit(page, 0, 'load');
  await expectRestored(page, initial, true, refusal);
  expect(await page.evaluate(() => window.photoReaders.length)).toBe(1);
});

for (const saved of [true, false]) {
  test(`une erreur de lecture courante rétablit ${saved ? 'la photo enregistrée' : 'le placeholder'}`, async ({page}) => {
    const initial = await mount(page, saved);
    await choose(page);
    await emit(page, 0, 'load');
    await choose(page, 'unreadable.jpg', 'image/jpeg');
    await expectRestored(page, initial, saved, '');
    await emit(page, 1, 'error');
    await emit(page, 0, 'load');
    await emit(page, 1, 'load');
    await expectRestored(page, initial, saved, readError);
  });
}

test('le vrai FileReader affiche une photo puis le vidage rétablit la photo enregistrée', async ({page}) => {
  const initial = await mount(page, true, false);
  await choose(page);
  const previewImage = page.locator('[data-photo-preview] img');
  await expect(previewImage).not.toHaveAttribute('src', savedPhoto);
  await expect(previewImage).toHaveJSProperty('naturalWidth', 1);
  await expect(page.locator('[data-photo-feedback]')).toHaveText(selected);
  await expect(page.locator('[data-photo-feedback]')).not.toHaveClass(/is-error/);
  await page.getByLabel('Photo', {exact: true}).setInputFiles([]);
  await expectRestored(page, initial, true, '');
});
