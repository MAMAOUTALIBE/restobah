import {test,expect} from '@playwright/test';
test('parcours de commande complet, persistance et responsive',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.getByRole('heading',{name:'Nos menus populaires'})).toBeVisible();
 await expect(page.locator('.product-card')).toHaveCount((page.viewportSize()?.width??1280)<=760?3:(page.viewportSize()?.width??1280)<=1100?6:4);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('textbox',{name:'Rechercher un plat'}).fill('introuvable');await expect(page.getByText('Aucun plat pour cette recherche.')).toBeVisible();
 await page.getByRole('textbox',{name:'Rechercher un plat'}).fill('Burger poulet');await expect(page.locator('.product-card')).toHaveCount(1);
 await page.getByRole('button',{name:'Effacer la recherche'}).click();
 await page.getByRole('button',{name:'Burgers',exact:true}).click();await expect(page.locator('.product-card')).toHaveCount(2);await page.getByRole('button',{name:'Tout',exact:true}).click();
 await page.getByRole('button',{name:'Ajouter Le Bucket STC aux favoris'}).click();
 await page.getByRole('button',{name:'Ajouter Le Bucket STC',exact:true}).click();const modal=page.getByRole('dialog');
 await modal.getByRole('button',{name:/Ajouter ·/}).click();await expect(page.getByRole('alert')).toHaveText('Sélectionnez une option pour continuer.');
 await modal.getByRole('radio',{name:'Sauce maison'}).check();await modal.getByRole('checkbox',{name:/Cheddar supplémentaire/}).check();await modal.getByRole('button',{name:'Augmenter la quantité'}).click();
 await modal.getByRole('button',{name:'Ajouter · 26,80 €'}).click();
 await page.reload();await page.getByRole('button',{name:/Mon panier/}).click();await expect(page.getByRole('dialog').getByText('26,80 €',{exact:true})).toHaveCount(3);
 await page.getByRole('button',{name:'Augmenter Le Bucket STC'}).click();await expect(page.getByText('40,20 €',{exact:true})).toHaveCount(3);
 await page.getByRole('button',{name:'Réduire Le Bucket STC'}).click();
 await page.getByRole('button',{name:'Livraison',exact:true}).click();await page.getByRole('button',{name:'Passer commande'}).click();
 await page.getByLabel('Nom complet').fill('Camille Martin');await page.getByLabel('Adresse e-mail').fill('camille@example.com');await page.getByLabel('Téléphone').fill('0612345678');await page.getByLabel('Adresse de livraison').fill('24 rue du Test');await page.getByLabel('Code postal').fill('75011');await page.getByLabel('Ville',{exact:true}).fill('Paris');
 await page.getByRole('button',{name:'Valider la commande de démonstration'}).click();await expect(page.getByRole('heading',{name:/Commande STC-/})).toBeVisible();await expect(page.getByText('30,70 €',{exact:true})).toBeVisible();await expect(page.getByText('En cuisine',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:/Mon panier/}).click();await expect(page.getByRole('dialog').getByRole('heading',{name:'Une petite faim ?'})).toBeVisible();await page.getByRole('button',{name:'Fermer',exact:true}).click();
 expect(errors).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test('favoris, filtres, suppression et commande à emporter',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Ajouter Le Bucket STC aux favoris'}).click();await page.reload();await expect(page.getByRole('button',{name:'Retirer Le Bucket STC des favoris'})).toBeVisible();
 await page.getByRole('button',{name:'Afficher les filtres'}).click();await page.getByLabel('Végétarien').check();await expect(page.locator('.product-card')).toHaveCount(4);await page.getByRole('button',{name:'Réinitialiser'}).click();
 await page.getByRole('button',{name:'Promotion 2'}).click();await expect(page.getByRole('heading',{name:'Ça croustille. Ça se partage.'})).toBeVisible();
 await page.getByRole('button',{name:'Voir tout'}).click();await page.getByRole('button',{name:'Ajouter Le Cookie Choco',exact:true}).click();await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
 await page.getByRole('button',{name:'Ajouter Le Cookie Choco',exact:true}).click();await page.getByRole('button',{name:'Ajouter · 3,90 €'}).click();await page.getByRole('button',{name:/Mon panier/}).click();
 await page.getByRole('button',{name:'Supprimer Le Cookie Choco'}).click();await expect(page.getByRole('dialog').getByRole('heading',{name:'Une petite faim ?'})).toBeVisible();await page.getByRole('button',{name:'Fermer',exact:true}).click();
 await page.getByRole('button',{name:'Ajouter Le Cookie Choco',exact:true}).click();await page.getByRole('button',{name:'Ajouter · 3,90 €'}).click();await page.getByRole('button',{name:/Mon panier/}).click();await page.getByRole('button',{name:'Passer commande'}).click();
 await page.getByRole('button',{name:'Valider la commande de démonstration'}).click();await expect(page.getByRole('dialog')).toBeVisible();expect(await page.getByLabel('Nom complet').evaluate((el:HTMLInputElement)=>el.validity.valueMissing)).toBe(true);
 await page.getByLabel('Nom complet').fill('Marie Test');await page.getByLabel('Adresse e-mail').fill('marie@example.com');await page.getByLabel('Téléphone').fill('0612345678');await page.getByRole('button',{name:'Valider la commande de démonstration'}).click();await expect(page.getByRole('heading',{name:/Commande STC-/})).toBeVisible();await expect(page.locator('.order-heading').getByText('3,90 €',{exact:true})).toBeVisible();await expect(page.locator('.order-card').getByText(/À emporter/)).toBeVisible();
});
test('une erreur de commande conserve le panier et permet une nouvelle tentative sans doublon',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'Voir tout'}).click();await page.getByRole('button',{name:'Ajouter Le Cookie Choco',exact:true}).click();await page.getByRole('button',{name:'Ajouter · 3,90 €'}).click();await page.getByRole('button',{name:/Mon panier/}).click();await page.getByRole('button',{name:'Passer commande'}).click();
 await page.getByLabel('Nom complet').fill('Camille Nouvelle Tentative');await page.getByLabel('Adresse e-mail').fill('retry@example.com');await page.getByLabel('Téléphone').fill('0612345678');
 let attempts=0;const keys:string[]=[];
 await page.route('**/api/orders/',async route=>{
  if(route.request().method()!=='POST'){await route.continue();return;}
  attempts++;keys.push(route.request().headers()['idempotency-key']||'');
  if(attempts===1){await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Le service est temporairement indisponible. Réessayez.'})});return;}
  await route.continue();
 });
 const submit=page.getByRole('button',{name:'Valider la commande de démonstration'});await submit.click();await expect(page.getByRole('alert')).toContainText('temporairement indisponible');await expect(page.getByRole('dialog').getByRole('heading',{name:'Le Cookie Choco'})).toBeVisible();await expect(page.getByLabel('Nom complet')).toHaveValue('Camille Nouvelle Tentative');
 await submit.click();await expect(page.getByRole('heading',{name:/Commande STC-/})).toBeVisible();expect(attempts).toBe(2);expect(keys[0]).toBeTruthy();expect(keys[1]).toBe(keys[0]);
 const stored=await page.evaluate(()=>Object.fromEntries(Object.entries(localStorage)));expect(JSON.stringify(stored)).not.toContain('retry@example.com');expect(JSON.stringify(stored)).not.toContain('Camille Nouvelle Tentative');
});

test('navigation compacte, footer fonctionnel et absence de débordement',async({page},testInfo)=>{
 await page.goto('/');await expect(page.locator('.product-card')).toHaveCount((page.viewportSize()?.width??1280)<=760?3:(page.viewportSize()?.width??1280)<=1100?6:4);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 if(testInfo.project.name==='mobile'){expect(await page.locator('.bottom-nav').evaluate(el=>el.getBoundingClientRect().height)).toBeLessThanOrEqual(44);expect(await page.locator('.bottom-nav .nav-cart').evaluate(el=>el.getBoundingClientRect().height)).toBeLessThanOrEqual(44);}
 const footer=page.getByRole('contentinfo',{name:'Informations STC'});await footer.scrollIntoViewIfNeeded();await expect(footer).toBeVisible();expect(await footer.evaluate(el=>el.getBoundingClientRect().height)).toBeLessThan(230);await page.screenshot({path:testInfo.outputPath('stc-footer.png'),fullPage:false});
 await footer.getByRole('button',{name:'Questions fréquentes'}).click();await expect(page.getByRole('dialog',{name:'Une question ? On vous répond.'})).toBeVisible();await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
 await footer.getByRole('button',{name:'Infos allergènes'}).click();await expect(page.getByRole('dialog',{name:'Allergènes & préférences'})).toBeVisible();await page.getByRole('button',{name:'C’est compris'}).click();await footer.getByRole('button',{name:'Mes favoris',exact:true}).click();await expect(page.getByRole('heading',{name:'Mes favoris',exact:true})).toBeVisible();
});
