import {test,expect,type Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';

// Regression tests of the reliability audit. Route rewrites only alter catalogue/settings
// responses to emulate administration changes; orders and refusals come from the real API.
const noOverflow=(page:Page)=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);
async function guestOrder(page:Page){
 await page.request.get('/api/auth/csrf/');const token=(await page.context().cookies()).find(c=>c.name==='csrftoken')!.value;
 const response=await page.request.post('/api/orders/',{headers:{'X-CSRFToken':token,'Idempotency-Key':randomUUID()},data:{mode:'À emporter',items:[{productId:6,quantity:1,choices:[]}],customer:{name:'Camille Lien',email:'lien@example.com',phone:'0612345678'},paymentMethod:'simulation'}});
 expect(response.status()).toBe(201);return response.json() as Promise<{id:string;accessToken:string}>;
}
async function addCookie(page:Page){await page.getByRole('button',{name:'Voir tout'}).click();await page.getByRole('button',{name:'Ajouter Le Cookie Choco',exact:true}).click();await page.getByRole('button',{name:'Ajouter · 3,90 €'}).click();await page.getByRole('button',{name:/Mon panier/}).click();}

test('les refus du serveur sont affichés tels quels, panier conservé',async({page})=>{
 await page.goto('/');await addCookie(page);await page.getByRole('button',{name:'Livraison',exact:true}).click();await page.getByRole('button',{name:'Passer commande'}).click();
 await page.getByLabel('Nom complet').fill('Camille Zone');await page.getByLabel('Adresse e-mail').fill('zone@example.com');await page.getByLabel('Téléphone').fill('0612345678');await page.getByLabel('Adresse de livraison').fill('1 place Bellecour');await page.getByLabel('Code postal').fill('75011');await page.getByLabel('Ville',{exact:true}).fill('Paris');
 // The browser check passes; the server receives an address outside the zone and must explain its refusal.
 await page.route('**/api/orders/',async route=>{if(route.request().method()!=='POST'){await route.continue();return;}const body=route.request().postDataJSON();body.customer.postal='69001';await route.continue({postData:JSON.stringify(body)});});
 await page.getByRole('button',{name:'Valider la commande de démonstration'}).click();
 await expect(page.getByRole('alert')).toHaveText('Cette adresse est en dehors de notre zone de livraison.');await expect(page.getByRole('dialog').getByRole('heading',{name:'Le Cookie Choco'})).toBeVisible();
});

test('mot de passe refusé : la raison est indiquée',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:/^(Mon compte|Compte)$/}).click();await page.getByRole('button',{name:'Créer un compte',exact:true}).click();
 await page.getByLabel('Nom complet',{exact:true}).fill('Camille Test');await page.getByLabel('Adresse e-mail',{exact:true}).fill(`stc-weak-${randomUUID()}@example.com`);await page.getByLabel('Mot de passe',{exact:true}).fill('motdepasse');await page.getByLabel('Confirmer le mot de passe',{exact:true}).fill('motdepasse');await page.getByRole('button',{name:'Créer mon compte',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Mot de passe : Ce mot de passe est trop courant.');
});

test('remise, catégories et prix suivent le catalogue du serveur',async({page})=>{
 await page.route('**/api/products/',async route=>{const response=await route.fetch();const products=await response.json();
  const promotion=products.find((p:{id:number})=>p.id===90);promotion.discountPercent=25;
  products.push({...products.find((p:{id:number})=>p.id===4),id:4004,name:'La Salade Fraîcheur',category:'Salades',description:'Salade croquante.',summary:'',price:8.5});
  await route.fulfill({response,json:products});});
 await page.route('**/api/categories/',async route=>{const response=await route.fetch();const list=await response.json();await route.fulfill({response,json:[...list,{name:'Salades',position:3}]});});
 await page.goto('/');
 await expect(page.locator('.offer h2')).toHaveText('Jusqu’à −25 %');await expect(page.locator('.offer-discount')).toContainText('25');
 const salads=page.getByRole('button',{name:'Salades',exact:true});await expect(salads).toBeVisible();await salads.click();await expect(page.locator('.product-card')).toHaveCount(1);await expect(page.locator('.product-grid').getByRole('heading',{name:'La Salade Fraîcheur'})).toBeVisible();
 expect(await noOverflow(page)).toBe(true);
});

test('recherche insensible aux accents et aux majuscules',async({page})=>{
 await page.goto('/');await page.getByRole('textbox',{name:'Rechercher un plat'}).fill('  EPICEE ');await expect(page.locator('.product-card')).toHaveCount(1);await expect(page.getByRole('heading',{name:'Le Spicy Chicken'})).toBeVisible();
});

test('lien de suivi reçu par e-mail : commande retrouvée et jeton retiré de l’adresse',async({page,browser})=>{
 const order=await guestOrder(page);
 const other=await browser.newContext({baseURL:process.env.E2E_BASE_URL||'http://localhost:5173'});
 try{
  const visitor=await other.newPage();await visitor.goto(`/?order_id=${order.id}&token=${encodeURIComponent(order.accessToken)}`);
  await expect(visitor.getByRole('heading',{name:`Commande ${order.id}`,exact:true})).toBeVisible();expect(visitor.url()).not.toContain('token=');
  expect(await visitor.evaluate(()=>localStorage.getItem('stc-guest-orders'))).toContain(order.id);
 }finally{await other.close();}
});

test('hors démonstration, aucune mention de démonstration dans le footer',async({page})=>{
 await page.route('**/api/restaurant/',async route=>{const response=await route.fetch();await route.fulfill({response,json:{...await response.json(),demoMode:false}});});
 await page.goto('/');const footer=page.getByRole('contentinfo',{name:'Informations STC'});await footer.scrollIntoViewIfNeeded();
 await expect(footer.getByText('24 rue des Gourmands',{exact:false})).toBeVisible();await expect(footer.getByText('Adresse de démonstration')).toHaveCount(0);await expect(footer.getByText('Horaires indicatifs')).toHaveCount(0);
 await footer.getByRole('button',{name:'Confidentialité',exact:true}).click();await expect(page.getByRole('dialog',{name:'Vos données'})).toBeVisible();await expect(page.getByRole('dialog')).not.toContainText('démonstration');
});

test('après connexion, les commandes invitées de l’appareil restent visibles',async({page})=>{
 await page.goto('/');const order=await guestOrder(page);
 await page.evaluate(ref=>localStorage.setItem('stc-guest-orders',JSON.stringify([ref])),{id:order.id,accessToken:order.accessToken});await page.reload();
 await page.getByRole('button',{name:/^(Mon compte|Compte)$/}).click();await page.getByRole('button',{name:'Créer un compte',exact:true}).click();
 const password='Stc-Guest!58x2';await page.getByLabel('Nom complet',{exact:true}).fill('Camille Invitée');await page.getByLabel('Adresse e-mail',{exact:true}).fill(`stc-guest-${randomUUID()}@example.com`);await page.getByLabel('Mot de passe',{exact:true}).fill(password);await page.getByLabel('Confirmer le mot de passe',{exact:true}).fill(password);await page.getByRole('button',{name:'Créer mon compte',exact:true}).click();
 await expect(page.getByRole('button',{name:'Se déconnecter',exact:true})).toBeVisible();await page.locator('.account-card').getByRole('button',{name:'Mes commandes'}).click();
 await expect(page.getByRole('heading',{name:`Commande ${order.id}`,exact:true})).toBeVisible();
});

test('suppression du compte : mot de passe exigé, puis retour à la connexion',async({page})=>{
 const password='Stc-Delete!47x3';await page.goto('/');await page.getByRole('button',{name:/^(Mon compte|Compte)$/}).click();await page.getByRole('button',{name:'Créer un compte',exact:true}).click();
 await page.getByLabel('Nom complet',{exact:true}).fill('Camille Départ');await page.getByLabel('Adresse e-mail',{exact:true}).fill(`stc-delete-${randomUUID()}@example.com`);await page.getByLabel('Mot de passe',{exact:true}).fill(password);await page.getByLabel('Confirmer le mot de passe',{exact:true}).fill(password);await page.getByRole('button',{name:'Créer mon compte',exact:true}).click();
 const card=page.locator('.delete-card');await card.getByRole('button',{name:'Supprimer',exact:true}).click();
 await card.getByLabel('Mot de passe actuel').fill('mauvais-mot-de-passe');await card.getByRole('button',{name:'Supprimer définitivement mon compte'}).click();await expect(card.getByRole('alert')).toHaveText('Mot de passe : Mot de passe incorrect.');
 await card.getByLabel('Mot de passe actuel').fill(password);await card.getByRole('button',{name:'Supprimer définitivement mon compte'}).click();
 await expect(page.getByRole('status').filter({hasText:'Votre compte a été supprimé'})).toBeVisible();await expect(page.getByRole('button',{name:'Se connecter',exact:true})).toBeVisible();
 expect((await (await page.request.get('/api/auth/me/')).json()).user).toBeNull();
});

test('délais affichés et livraison fermée sans zone suivent les réglages du restaurant',async({page})=>{
 let settings:Record<string,unknown>={pickupDelay:'10 min',deliveryDelay:'45 min'};
 await page.route('**/api/restaurant/',async route=>{const response=await route.fetch();await route.fulfill({response,json:{...await response.json(),...settings}});});
 await page.goto('/');await addCookie(page);const dialog=page.getByRole('dialog');
 await expect(dialog.getByText(/Prêt dans 10 min/)).toBeVisible();await dialog.getByRole('button',{name:'Livraison',exact:true}).click();await expect(dialog.getByText(/Livraison · 45 min/)).toBeVisible();
 settings={deliveryEnabled:false,deliveryPostalCodes:[]};await page.getByRole('button',{name:'Fermer',exact:true}).click();await page.reload();await page.getByRole('button',{name:/Mon panier/}).click();
 await expect(page.getByRole('dialog').getByRole('button',{name:'Livraison',exact:true})).toBeDisabled();
});
