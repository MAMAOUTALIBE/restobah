import {test,expect,type Page} from '@playwright/test';
import {randomUUID} from 'node:crypto';
import {readFileSync,readdirSync} from 'node:fs';
import {join} from 'node:path';

const password='Stc-AuthRecovery!82x4';
const accountButton=(page:Page)=>page.getByRole('button',{name:/^(Mon compte|Compte)$/});
const cartDialog=(page:Page)=>page.getByRole('dialog',{name:'Mon panier',exact:true});
async function createCustomer(page:Page,email:string){
  await accountButton(page).click();
  await page.getByRole('button',{name:'Créer un compte',exact:true}).click();
  await page.getByLabel('Nom complet',{exact:true}).fill('Camille Réponse');
  await page.getByLabel('Adresse e-mail',{exact:true}).fill(email);
  await page.getByLabel('Mot de passe',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Créer mon compte',exact:true}).click();
  await expect(page.getByRole('button',{name:'Se déconnecter',exact:true})).toBeVisible();
}
async function openBasket(page:Page){
  await page.getByRole('button',{name:/^(Notre carte|Carte)$/}).click();
  await page.getByRole('button',{name:'Voir tout',exact:true}).click();
  await page.getByRole('button',{name:'Ajouter Le Cookie Choco',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:/Ajouter ·/}).click();
  await page.getByRole('button',{name:/Mon panier/}).click();
  return cartDialog(page);
}
async function openAccountFromBasket(page:Page,email:string,mode:'login'|'register'){
  const cart=await openBasket(page);
  await cart.getByRole('button',{name:'Passer commande',exact:true}).click();
  await cart.getByLabel('Nom complet',{exact:true}).fill('Camille Réponse');
  await cart.getByLabel('Adresse e-mail',{exact:true}).fill(email);
  await cart.getByLabel('Téléphone',{exact:true}).fill('0612345678');
  await cart.getByLabel('Une précision ?',{exact:true}).fill('Brouillon de réponse conservé.');
  await cart.getByRole('button',{name:mode==='login'?'Déjà client ? Me connecter':'Créer un compte',exact:true}).click();
}
async function finishVerifiedOrder(page:Page,email:string){
  const cart=cartDialog(page);await expect(cart).toBeVisible();
  await expect(cart.getByLabel('Adresse e-mail',{exact:true})).toHaveValue(email);
  await expect(cart.getByLabel('Téléphone',{exact:true})).toHaveValue('0612345678');
  await expect(cart.getByLabel('Une précision ?',{exact:true})).toHaveValue('Brouillon de réponse conservé.');
  await cart.getByRole('button',{name:process.env.STC_PAYMENT_MODE==='on_site'?'Commander et régler au restaurant':'Valider la commande de démonstration',exact:true}).click();
  await expect(page.getByRole('heading',{name:/Commande STC-/})).toBeVisible();
  const orders=await page.request.get('/api/orders/');expect(orders.ok()).toBe(true);
  const own=await orders.json();expect(own).toHaveLength(1);expect(own[0].customer.email).toBe(email);
}

for(const mode of ['register','login'] as const){
  test(`authentification ${mode} : corps JSON tronqué après Set-Cookie, identité vérifiée avant reprise panier`,async({page})=>{
    const email=`auth-response-${mode}-${randomUUID()}@example.com`;
    await page.goto('/');
    if(mode==='login'){
      await createCustomer(page,email);
      await page.getByRole('button',{name:'Se déconnecter',exact:true}).click();
    }
    await openAccountFromBasket(page,email,mode);
    let serverStatus=0;let cookieReturned=false;
    await page.route(`**/api/auth/${mode}/`,async route=>{
      const response=await route.fetch();serverStatus=response.status();
      cookieReturned=response.headersArray().some(header=>header.name.toLowerCase()==='set-cookie');
      await route.fulfill({response,body:'{"user":',contentType:'application/json'});
    });
    await page.getByLabel('Mot de passe',{exact:true}).fill(password);
    await page.getByRole('button',{name:mode==='login'?'Se connecter':'Créer mon compte',exact:true}).click();
    await expect.poll(()=>serverStatus).toBe(mode==='register'?201:200);
    expect(cookieReturned).toBe(true);
    await expect.poll(async()=>(await (await page.request.get('/api/auth/me/')).json()).user?.email).toBe(email);
    await expect(page.locator('.toast')).toContainText('Vous êtes connecté.');
    await expect(page.locator('.toast')).not.toContainText('Votre compte est créé.');
    await finishVerifiedOrder(page,email);
  });
}

for(const mode of ['register','login'] as const){
  test(`authentification ${mode} : réponse tronquée et lecture /me indisponible, achat bloqué puis identité vérifiée`,async({page})=>{
    const email=`auth-unverified-${mode}-${randomUUID()}@example.com`;
    await page.goto('/');
    if(mode==='login'){
      await createCustomer(page,email);
      await page.getByRole('button',{name:'Se déconnecter',exact:true}).click();
    }
    await openAccountFromBasket(page,email,mode);
    let blockMe=false;let orderWrites=0;
    page.on('request',request=>{if(new URL(request.url()).pathname==='/api/orders/'&&request.method()==='POST')orderWrites++;});
    await page.route('**/api/auth/me/',async route=>{if(blockMe){if(mode==='register')await route.fulfill({json:null});else await route.abort();}else await route.continue();});
    await page.route(`**/api/auth/${mode}/`,async route=>{
      const response=await route.fetch();expect(response.status()).toBe(mode==='register'?201:200);blockMe=true;
      await route.fulfill({response,body:'{"user":',contentType:'application/json'});
    });
    await page.getByLabel('Mot de passe',{exact:true}).fill(password);
    await page.getByRole('button',{name:mode==='login'?'Se connecter':'Créer mon compte',exact:true}).click();
    await expect(page.locator('.account-page>.notice.error')).toContainText(/vérifier/i);
    expect((await (await page.request.get('/api/auth/me/')).json()).user.email).toBe(email);
    await expect(page.getByRole('button',{name:'Continuer ma commande sans compte',exact:true})).toBeDisabled();
    await expect(cartDialog(page)).toHaveCount(0);
    await page.getByRole('button',{name:/Mon panier/}).click();
    const cart=cartDialog(page);
    await expect(cart.getByRole('alert')).toContainText('Votre session doit être vérifiée avant de commander.');
    await expect(cart.locator('.checkout button[type="submit"]')).toBeDisabled();
    expect(orderWrites).toBe(0);
    await cart.getByRole('button',{name:'Vérifier mon compte',exact:true}).click();
    blockMe=false;
    await page.locator('.account-page>.notice.error').getByRole('button',{name:'Réessayer',exact:true}).click();
    await expect(page.getByRole('button',{name:'Se déconnecter',exact:true})).toBeVisible();
    await page.getByRole('button',{name:/Mon panier/}).click();
    await finishVerifiedOrder(page,email);
    expect(orderWrites).toBe(1);
  });
}

test('réconciliation auth : un autre compte réel ne valide pas le formulaire ni ne reprend le panier',async({page})=>{
  const expectedEmail=`auth-expected-${randomUUID()}@example.com`;
  const otherEmail=`auth-other-${randomUUID()}@example.com`;
  await page.goto('/');await createCustomer(page,expectedEmail);
  await page.getByRole('button',{name:'Se déconnecter',exact:true}).click();
  await openAccountFromBasket(page,expectedEmail,'login');
  const csrf=(await page.context().cookies()).find(cookie=>cookie.name==='csrftoken')?.value;expect(csrf).toBeTruthy();
  const other=await page.request.post('/api/auth/register/',{headers:{'X-CSRFToken':csrf!},data:{name:'Camille Autre',email:otherEmail,password}});
  expect(other.status()).toBe(201);
  let attempts=0;let orderWrites=0;
  page.on('request',request=>{if(new URL(request.url()).pathname==='/api/orders/'&&request.method()==='POST')orderWrites++;});
  await page.route('**/api/auth/login/',async route=>{attempts++;if(attempts===1)await route.abort();else await route.continue();});
  await page.getByLabel('Mot de passe',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Se connecter',exact:true}).click();
  await expect(page.locator('.account-page>.notice.error')).toContainText('ne correspond pas');
  expect((await (await page.request.get('/api/auth/me/')).json()).user.email).toBe(otherEmail);
  await expect(cartDialog(page)).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Continuer ma commande sans compte',exact:true})).toBeDisabled();
  expect(orderWrites).toBe(0);
  await page.getByRole('button',{name:'Se connecter',exact:true}).click();
  await finishVerifiedOrder(page,expectedEmail);
  expect((await (await page.request.get('/api/auth/me/')).json()).user.email).toBe(expectedEmail);
  expect(orderWrites).toBe(1);
});

for(const meUnavailable of [false,true]){
  test(`déconnexion : JSON perdu après fermeture serveur, lecture /me ${meUnavailable?'indisponible puis reprise':'vérifiée'}`,async({page})=>{
    const email=`logout-response-${randomUUID()}@example.com`;
    await page.goto('/');await createCustomer(page,email);
    await (await openBasket(page)).getByRole('button',{name:'Fermer',exact:true}).click();await accountButton(page).click();
    let blockMe=false;let logoutWrites=0;
    await page.route('**/api/auth/me/',async route=>{if(blockMe)await route.abort();else await route.continue();});
    await page.route('**/api/auth/logout/',async route=>{
      logoutWrites++;
      if(logoutWrites>1){await route.continue();return;}
      const response=await route.fetch();expect(response.status()).toBe(200);blockMe=meUnavailable;
      await route.fulfill({response,body:'{"detail":',contentType:'application/json'});
    });
    await page.getByRole('button',{name:'Se déconnecter',exact:true}).click();
    await expect(page.getByRole('button',{name:'Se connecter',exact:true})).toBeVisible();
    expect((await (await page.request.get('/api/auth/me/')).json()).user).toBeNull();
    await expect(page.locator('.profile-card')).toHaveCount(0);
    if(meUnavailable){
      await expect(page.locator('.account-page>.notice.error')).toContainText(/vérifier/i);
      await expect(page.getByRole('button',{name:'Continuer sans compte',exact:true})).toBeDisabled();
      await page.getByRole('button',{name:/Mon panier/}).click();
      await expect(cartDialog(page).getByRole('button',{name:'Passer commande',exact:true})).toBeDisabled();
      await cartDialog(page).getByRole('button',{name:'Vérifier mon compte',exact:true}).click();
      expect(logoutWrites).toBe(1);blockMe=false;
      await page.locator('.account-page>.notice.error').getByRole('button',{name:'Réessayer',exact:true}).click();
      await expect(page.getByRole('button',{name:'Continuer ma commande sans compte',exact:true})).toBeEnabled();
      expect(logoutWrites).toBe(2);
    }else{
      await expect(page.getByRole('button',{name:'Continuer sans compte',exact:true})).toBeEnabled();
      expect(logoutWrites).toBe(1);
    }
  });
}

for(const meUnavailable of [false,true]){
  test(`suppression : réponse perdue après écriture, aucune annonce non prouvée, /me ${meUnavailable?'indisponible puis reprise':'vérifiée'}`,async({page})=>{
    const email=`delete-response-${randomUUID()}@example.com`;
    await page.goto('/');await createCustomer(page,email);
    await (await openBasket(page)).getByRole('button',{name:'Fermer',exact:true}).click();await accountButton(page).click();
    let blockMe=false;let deletions=0;
    await page.route('**/api/auth/me/',async route=>{if(blockMe)await route.abort();else await route.continue();});
    await page.route('**/api/auth/delete-account/',async route=>{
      deletions++;const response=await route.fetch();expect(response.status()).toBe(200);blockMe=meUnavailable;
      await route.fulfill({response,body:'{"detail":',contentType:'application/json'});
    });
    await page.locator('.delete-card').getByRole('button',{name:'Supprimer',exact:true}).click();
    await page.getByLabel('Mot de passe actuel',{exact:true}).fill(password);
    await page.getByRole('button',{name:'Supprimer définitivement mon compte',exact:true}).click();
    await expect(page.getByRole('status').filter({hasText:'La suppression de votre compte n’a pas pu être confirmée.'})).toBeVisible();
    await expect(page.getByRole('button',{name:'Se connecter',exact:true})).toBeVisible();
    expect((await (await page.request.get('/api/auth/me/')).json()).user).toBeNull();
    await expect(page.locator('.profile-card')).toHaveCount(0);
    await expect(page.locator('.toast')).not.toContainText('Votre compte a été supprimé');
    expect(deletions).toBe(1);
    if(meUnavailable){
      await expect(page.locator('.account-page>.notice.error')).toContainText(/vérifier/i);
      await expect(page.getByRole('button',{name:'Continuer sans compte',exact:true})).toBeDisabled();
      await page.getByRole('button',{name:/Mon panier/}).click();
      await expect(cartDialog(page).getByRole('button',{name:'Passer commande',exact:true})).toBeDisabled();
      await cartDialog(page).getByRole('button',{name:'Vérifier mon compte',exact:true}).click();blockMe=false;
      await page.locator('.account-page>.notice.error').getByRole('button',{name:'Réessayer',exact:true}).click();
      await expect(page.getByRole('button',{name:'Continuer ma commande sans compte',exact:true})).toBeEnabled();
    }else await expect(page.getByRole('button',{name:'Continuer sans compte',exact:true})).toBeEnabled();
    expect(deletions).toBe(1);
    await expect(page.getByRole('status').filter({hasText:'La suppression de votre compte n’a pas pu être confirmée.'})).toBeVisible();
    await expect(page.locator('.toast')).not.toContainText('Votre compte a été supprimé');
  });
}

test('suppression non arrivée et lecture indisponible : aucune répétition, compte encore accessible après vérification',async({page})=>{
  const email=`delete-never-arrived-${randomUUID()}@example.com`;
  await page.goto('/');await createCustomer(page,email);
  let blockMe=false;let deletions=0;
  await page.route('**/api/auth/me/',async route=>{if(blockMe)await route.abort();else await route.continue();});
  await page.route('**/api/auth/delete-account/',async route=>{deletions++;blockMe=true;await route.abort();});
  await page.locator('.delete-card').getByRole('button',{name:'Supprimer',exact:true}).click();
  await page.getByLabel('Mot de passe actuel',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Supprimer définitivement mon compte',exact:true}).click();
  await expect(page.locator('.account-page>.notice.error')).toContainText(/vérifier/i);
  expect((await (await page.request.get('/api/auth/me/')).json()).user.email).toBe(email);
  await expect(page.getByRole('status').filter({hasText:'La suppression de votre compte n’a pas pu être confirmée.'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Continuer sans compte',exact:true})).toBeDisabled();
  blockMe=false;
  await page.locator('.account-page>.notice.error').getByRole('button',{name:'Réessayer',exact:true}).click();
  await expect(page.getByRole('button',{name:'Continuer sans compte',exact:true})).toBeEnabled();
  expect(deletions).toBe(1);
  await page.getByLabel('Adresse e-mail',{exact:true}).fill(email);
  await page.getByLabel('Mot de passe',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Se connecter',exact:true}).click();
  await expect(page.getByRole('button',{name:'Se déconnecter',exact:true})).toBeVisible();
  expect(deletions).toBe(1);
});

async function privateResetLink(page:Page,email:string,directory:string){
  const csrf=(await page.context().cookies()).find(cookie=>cookie.name==='csrftoken')?.value;expect(csrf).toBeTruthy();
  const response=await page.request.post('/api/auth/password-reset/',{headers:{'X-CSRFToken':csrf!},data:{email}});expect(response.ok()).toBe(true);
  let link='';
  await expect.poll(()=>{
    const content=readdirSync(directory).map(file=>readFileSync(join(directory,file),'utf8')).find(body=>body.includes(email)&&body.includes('reset_uid='));
    link=content?.match(/https?:\/\/[^\s<>]*\?reset_uid=[^\s<>]+/)?.[0]||'';return link;
  }).not.toBe('');return link;
}

for(const action of ['register','login','logout','delete','confirm'] as const){
  test(`réponse JSON null après ${action} : identité réconciliée sans déréférence ni affirmation non prouvée`,async({page})=>{
    const directory=process.env.STC_EMAIL_FILE_PATH;
    test.skip(action==='confirm'&&!directory,'Le reset exige la boîte e-mail privée de la recette isolée.');
    const email=`auth-null-${action}-${randomUUID()}@example.com`;
    await page.goto('/');
    if(action!=='register')await createCustomer(page,email);
    if(action==='login')await page.getByRole('button',{name:'Se déconnecter',exact:true}).click();
    if(action==='login'||action==='register')await openAccountFromBasket(page,email,action);
    if(action==='confirm'){
      await page.goto(await privateResetLink(page,email,directory!));
      await expect(page.getByRole('button',{name:'Enregistrer le nouveau mot de passe',exact:true})).toBeEnabled();
    }
    const endpoint=action==='delete'?'delete-account':action==='confirm'?'password-reset-confirm':action;
    let writes=0;let serverStatus=0;
    await page.route(`**/api/auth/${endpoint}/`,async route=>{writes++;const response=await route.fetch();serverStatus=response.status();await route.fulfill({response,body:'null',contentType:'application/json'});});
    if(action==='login'||action==='register'){
      await page.getByLabel('Mot de passe',{exact:true}).fill(password);
      await page.getByRole('button',{name:action==='login'?'Se connecter':'Créer mon compte',exact:true}).click();
      await expect.poll(()=>serverStatus).toBe(action==='register'?201:200);
      await expect(page.locator('.toast')).toContainText('Vous êtes connecté.');
      await expect(page.locator('.toast')).not.toContainText('Votre compte est créé.');
      await finishVerifiedOrder(page,email);
    }else{
      if(action==='logout')await page.getByRole('button',{name:'Se déconnecter',exact:true}).click();
      else if(action==='delete'){
        await page.locator('.delete-card').getByRole('button',{name:'Supprimer',exact:true}).click();
        await page.getByLabel('Mot de passe actuel',{exact:true}).fill(password);
        await page.getByRole('button',{name:'Supprimer définitivement mon compte',exact:true}).click();
      }else{
        await page.getByLabel('Nouveau mot de passe',{exact:true}).fill('Stc-NullReset!41m8');
        await page.getByLabel('Confirmer le mot de passe',{exact:true}).fill('Stc-NullReset!41m8');
        await page.getByRole('button',{name:'Enregistrer le nouveau mot de passe',exact:true}).click();
      }
      await expect.poll(()=>serverStatus).toBe(200);
      await expect(page.getByRole('button',{name:'Se connecter',exact:true})).toBeVisible();
      expect((await (await page.request.get('/api/auth/me/')).json()).user).toBeNull();
      await expect(page.locator('.profile-card')).toHaveCount(0);
      if(action==='delete'){
        await expect(page.getByRole('status').filter({hasText:'La suppression de votre compte n’a pas pu être confirmée.'})).toBeVisible();
        await expect(page.locator('.toast')).not.toContainText('Votre compte a été supprimé');
      }else if(action==='confirm'){
        await expect(page.getByRole('alert')).toContainText('La réponse du serveur n’a pas pu être vérifiée.');
        await expect(page.getByRole('status').filter({hasText:'Votre mot de passe a été modifié.'})).toHaveCount(0);
        expect(page.url()).not.toContain('reset_token=');
      }
    }
    expect(writes).toBe(1);
  });
}

for(const action of ['register','login','logout','delete'] as const){
  test(`réponse suspendue ${action} : mutation serveur réelle et panier verrouillé avant lecture du corps`,async({page})=>{
    const email=`auth-held-${action}-${randomUUID()}@example.com`;
    await page.goto('/');
    if(action!=='register')await createCustomer(page,email);
    if(action==='login')await page.getByRole('button',{name:'Se déconnecter',exact:true}).click();
    if(action==='login'||action==='register')await openAccountFromBasket(page,email,action);
    else{
      await (await openBasket(page)).getByRole('button',{name:'Fermer',exact:true}).click();await accountButton(page).click();
      if(action==='delete'){
        await page.locator('.delete-card').getByRole('button',{name:'Supprimer',exact:true}).click();
        await page.getByLabel('Mot de passe actuel',{exact:true}).fill(password);
      }
    }
    let release!:()=>void;const wait=new Promise<void>(resolve=>{release=resolve;});
    let serverStatus=0;let orderWrites=0;let identityWrites=0;
    const endpoint=action==='delete'?'delete-account':action;
    page.on('request',request=>{if(new URL(request.url()).pathname==='/api/orders/'&&request.method()==='POST')orderWrites++;});
    await page.route(`**/api/auth/${endpoint}/`,async route=>{
      identityWrites++;const response=await route.fetch();serverStatus=response.status();await wait;await route.fulfill({response});
    });
    try{
      if(action==='login'||action==='register'){
        await page.getByLabel('Mot de passe',{exact:true}).fill(password);
        await page.getByRole('button',{name:action==='login'?'Se connecter':'Créer mon compte',exact:true}).click();
      }else await page.getByRole('button',{name:action==='logout'?'Se déconnecter':'Supprimer définitivement mon compte',exact:true}).click();
      await expect.poll(()=>serverStatus).toBe(action==='register'?201:200);
      const actual=(await (await page.request.get('/api/auth/me/')).json()).user;
      if(action==='login'||action==='register')expect(actual.email).toBe(email);else expect(actual).toBeNull();
      await page.getByRole('button',{name:/Mon panier/}).click();
      const cart=cartDialog(page);
      if(action==='login'||action==='register')await expect(cart.locator('.checkout button[type="submit"]')).toBeDisabled();
      else await expect(cart.getByRole('button',{name:'Passer commande',exact:true})).toBeDisabled();
      expect(orderWrites).toBe(0);
    }finally{release();}
    if(action==='login'||action==='register')await finishVerifiedOrder(page,email);
    else{
      await expect(cartDialog(page).getByRole('button',{name:'Passer commande',exact:true})).toBeEnabled();
      await cartDialog(page).getByRole('button',{name:'Fermer',exact:true}).click();
      await expect(page.getByRole('button',{name:'Se connecter',exact:true})).toBeVisible();
      if(action==='delete')await expect(page.locator('.toast')).toContainText('Votre compte a été supprimé');
    }
    expect(identityWrites).toBe(1);
  });
}
