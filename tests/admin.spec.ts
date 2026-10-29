import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';

// Dev-only credentials are created by manage.py dev_admin, never printed or committed.
function credentials(){
 const content=readFileSync(join(process.env.STC_RUNTIME_DIR||'.runtime','admin-credentials.txt'),'utf8');
 const email=content.match(/^E-mail\s*:\s*(.+)$/m)?.[1]?.trim();const password=content.match(/^Mot de passe\s*:\s*(.+)$/m)?.[1]?.trim();
 if(!email||!password)throw new Error('Exécutez manage.py dev_admin pour préparer les accès de test locaux.');
 return {email,password};
}

test('administration : passage en cuisine et suivi invité réellement mis à jour',async({browser})=>{
 test.setTimeout(60_000);
 const base=process.env.E2E_BASE_URL||'http://localhost:5173';const guest=await browser.newContext({baseURL:base,extraHTTPHeaders:{Origin:base}});const administrator=await browser.newContext({baseURL:base});
 try{
  await guest.request.get('/api/auth/csrf/');const token=(await guest.cookies()).find(c=>c.name==='csrftoken')!.value;
  const response=await guest.request.post('/api/orders/',{headers:{'X-CSRFToken':token,'Idempotency-Key':randomUUID()},data:{mode:'À emporter',items:[{productId:6,quantity:1,choices:[]}],customer:{name:'Camille Suivi',email:'suivi@example.com',phone:'0612345678'},paymentMethod:'simulation'}});expect(response.status()).toBe(201);const order=await response.json();
  await guest.addInitScript(({id,accessToken})=>localStorage.setItem('stc-guest-orders',JSON.stringify([{id,accessToken}])),{id:order.id,accessToken:order.accessToken});
  const clientPage=await guest.newPage();await clientPage.goto(`/?order_id=${order.id}`);await expect(clientPage.getByRole('heading',{name:`Commande ${order.id}`,exact:true})).toBeVisible();await expect(clientPage.locator('.order-status')).toHaveText('Confirmée');
  const adminPage=await administrator.newPage();await adminPage.goto(`/admin/shop/order/${encodeURIComponent(order.id)}/change/`);const access=credentials();await adminPage.locator('input[name="username"]').fill(access.email);await adminPage.locator('input[name="password"]').fill(access.password);await adminPage.locator('input[type="submit"]').click();
  await expect(adminPage.locator('#id_status')).toBeVisible();await adminPage.locator('#id_status').selectOption('preparing');await adminPage.locator('input[name="_save"]').click();
  await clientPage.bringToFront();await expect(clientPage.locator('.order-status')).toHaveText('En cuisine',{timeout:36_000});await expect(clientPage.getByLabel('Suivi : En cuisine')).toBeVisible();await clientPage.getByText('Historique du suivi',{exact:true}).click();await expect(clientPage.locator('.order-events li')).toHaveCount(2);
  const detail=await guest.request.get(`/api/orders/${order.id}/?token=${encodeURIComponent(order.accessToken)}`);expect(detail.ok()).toBeTruthy();expect((await detail.json()).history.map((event:{status:string})=>event.status)).toEqual(['confirmed','preparing']);
 }finally{await guest.close();await administrator.close();}
});
