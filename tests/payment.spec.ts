import {test,expect,type Page} from '@playwright/test';

// These browser tests deliberately mock only the Stripe-facing API responses.
// They validate recovery UI; signed webhooks and server totals have separate Django tests.
const prefix='STC-FIXTURE-';
function order(id:string,status='pending_payment'){
 return {id,date:new Date().toISOString(),total:3.9,subtotal:3.9,deliveryFee:0,mode:'À emporter',items:['1 × Le Cookie Choco'],status,paymentStatus:status==='cancelled'?'cancelled':'pending',accessToken:'browser-fixture-token-not-a-real-order',demoMode:true,lines:[{name:'Le Cookie Choco',quantity:1,unitPrice:3.9,total:3.9,choices:[]}],history:[{status:'pending_payment',date:new Date().toISOString()},...(status==='cancelled'?[{status:'cancelled',date:new Date().toISOString()}]:[])]};
}
async function stripeSettings(page:Page){
 await page.route('**/api/restaurant/',async route=>{const response=await route.fetch();const data=await response.json();await route.fulfill({response,json:{...data,paymentMode:'stripe',orderingEnabled:true,isOpen:true}});});
}
async function checkout(page:Page){
 await page.goto('/');await page.getByRole('button',{name:'Voir tout'}).click();await page.getByRole('button',{name:'Ajouter Le Cookie Choco',exact:true}).click();await page.getByRole('button',{name:'Ajouter · 3,90 €'}).click();await page.getByRole('button',{name:/Mon panier/}).click();await page.getByRole('button',{name:'Passer commande'}).click();await page.getByLabel('Nom complet').fill('Camille Paiement Test');await page.getByLabel('Adresse e-mail').fill('fixture@example.com');await page.getByLabel('Téléphone').fill('0612345678');
}

test('Stripe UI avec fixtures : session expirée, panier conservé et nouvelle clé de commande',async({page})=>{
 await stripeSettings(page);const keys:string[]=[];let count=0;
 await page.route('**/api/orders/',async route=>{if(route.request().method()!=='POST'){await route.continue();return;}keys.push(route.request().headers()['idempotency-key']||'');count++;await route.fulfill({status:201,json:order(`${prefix}EXPIRED-${count}`)});});
 await page.route(`**/api/orders/${prefix}*/payment/`,route=>route.fulfill({status:409,json:{detail:'Cette session de paiement a expiré.'}}));
 await page.route(`**/api/orders/${prefix}*/?token=*`,route=>route.fulfill({json:order(`${prefix}EXPIRED-${count}`,'cancelled')}));
 await checkout(page);await page.getByRole('button',{name:'Continuer vers le paiement test',exact:true}).click();await expect(page.getByRole('alert')).toContainText('annulée ou expirée');await expect(page.getByLabel('Nom complet')).toBeEnabled();await expect(page.getByRole('dialog').getByRole('heading',{name:'Le Cookie Choco'})).toBeVisible();
 expect(await page.evaluate(()=>sessionStorage.getItem('stc-checkout-key'))).toBeNull();expect(await page.evaluate(()=>sessionStorage.getItem('stc-payment-cart'))).toBeNull();
 await page.getByRole('button',{name:'Continuer vers le paiement test',exact:true}).click();await expect(page.getByRole('alert')).toContainText('annulée ou expirée');expect(count).toBe(2);expect(keys[0]).toBeTruthy();expect(keys[1]).not.toBe(keys[0]);
});

test('Stripe UI avec fixtures : commande encore en attente, reprise sans nouvelle commande',async({page})=>{
 await stripeSettings(page);let orders=0;let payments=0;const pending=order(`${prefix}PENDING`);
 await page.route('**/api/orders/',async route=>{if(route.request().method()!=='POST'){await route.continue();return;}orders++;await route.fulfill({status:201,json:pending});});
 await page.route(`**/api/orders/${prefix}PENDING/payment/`,route=>{payments++;return route.fulfill({status:409,json:{detail:'Le résultat du paiement est encore en cours de vérification.'}});});
 await page.route(`**/api/orders/${prefix}PENDING/?token=*`,route=>route.fulfill({json:pending}));
 await checkout(page);await page.getByRole('button',{name:'Continuer vers le paiement test',exact:true}).click();await expect(page.getByRole('button',{name:'Réessayer le paiement test',exact:true})).toBeVisible();await expect(page.getByRole('alert')).toContainText('vérification');await expect(page.getByLabel('Nom complet')).toBeDisabled();
 const saved=await page.evaluate(()=>sessionStorage.getItem('stc-checkout-key'));expect(saved).toBeTruthy();await page.getByRole('button',{name:'Réessayer le paiement test',exact:true}).click();await expect.poll(()=>payments).toBe(2);expect(orders).toBe(1);expect(await page.evaluate(()=>sessionStorage.getItem('stc-checkout-key'))).toBe(saved);
});

test('Stripe UI avec fixtures : retour annulé, migration sûre et purge du marqueur correspondant uniquement',async({page})=>{
 await stripeSettings(page);const cancelled=order(`${prefix}CANCELLED`,'cancelled');
 await page.addInitScript(cancelled=>{
  localStorage.setItem('smash-orders',JSON.stringify([{customer:{email:'legacy-private@example.com',name:'Ancien Client'}}]));
  localStorage.setItem('smash-cart',JSON.stringify([{key:'legacy',product:{id:1,name:'Le Bucket STC',price:0.01,image:'stc-menu-1',category:'Poulet',description:'Ancienne recette'},quantity:2,option:'Sauce maison',extras:['Cheddar supplémentaire'],unitPrice:0.01}]));
  localStorage.setItem('stc-guest-orders',JSON.stringify([{id:cancelled.id,accessToken:cancelled.accessToken}]));
  sessionStorage.setItem('stc-checkout-key',JSON.stringify({key:'old-key',fingerprint:'old-fingerprint'}));sessionStorage.setItem('stc-payment-cart',JSON.stringify({id:cancelled.id,signature:'old-signature'}));
 },cancelled);
 await page.route(`**/api/orders/${prefix}CANCELLED/?token=*`,route=>route.fulfill({json:cancelled}));
 await page.goto('/?payment=cancelled');await expect(page.getByText(/Le paiement a été interrompu/)).toBeVisible();await expect(page.locator('.order-status')).toHaveText('Annulée');
 expect(await page.evaluate(()=>localStorage.getItem('smash-orders'))).toBeNull();expect(await page.evaluate(()=>sessionStorage.getItem('stc-payment-cart'))).toBeNull();expect(await page.evaluate(()=>sessionStorage.getItem('stc-checkout-key'))).toBeNull();
 await page.evaluate(()=>{sessionStorage.setItem('stc-payment-cart',JSON.stringify({id:'STC-UNRELATED',signature:'other'}));sessionStorage.setItem('stc-checkout-key',JSON.stringify({key:'unrelated-key',fingerprint:'other'}));});await page.getByRole('button',{name:'Actualiser',exact:true}).click();await expect(page.getByRole('button',{name:'Actualiser',exact:true})).toBeEnabled();expect(await page.evaluate(()=>sessionStorage.getItem('stc-checkout-key'))).toContain('unrelated-key');
 await page.getByRole('button',{name:/Mon panier/}).click();await expect(page.getByRole('dialog').getByText('26,80 €',{exact:true})).toHaveCount(3);await expect(page.getByRole('button',{name:'Passer commande'})).toBeEnabled();expect(await page.evaluate(()=>localStorage.getItem('smash-cart'))).toBeNull();
});
