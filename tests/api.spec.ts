import {test,expect,type APIRequestContext,type APIResponse} from '@playwright/test';
import {randomUUID} from 'node:crypto';

type Choice={id:string;name:string;price:number};
type Product={id:number;price:number;optionGroups:{min:number;max:number;choices:Choice[]}[]};
const base=process.env.E2E_BASE_URL||'http://localhost:5173';
const customer={name:'Camille Vérification',email:'camille.e2e@example.com',phone:'0612345678'};
const password='Stc-E2E!72x4';
async function csrf(api:APIRequestContext){await api.get('/api/auth/csrf/');const cookie=(await api.storageState()).cookies.find(c=>c.name==='csrftoken');expect(cookie,'Le serveur doit émettre un cookie CSRF').toBeTruthy();return cookie!.value;}
async function write(api:APIRequestContext,path:string,data:unknown,method='POST',headers:Record<string,string>={}){const token=await csrf(api);return api.fetch(path,{method,data,headers:{'X-CSRFToken':token,...headers}});}
async function register(api:APIRequestContext){const email=`stc-e2e-${randomUUID()}@example.com`;const response=await write(api,'/api/auth/register/',{name:'Camille Vérification',email,password});expect(response.status(),(await response.text()).slice(0,500)).toBe(201);return email;}
async function catalog(api:APIRequestContext){const response=await api.get('/api/products/');expect(response.ok()).toBeTruthy();return response.json() as Promise<Product[]>;}
function validChoices(product:Product){return product.optionGroups.flatMap(g=>g.choices.slice(0,g.min).map(c=>c.id));}
function body(product:Product,changes:Record<string,unknown>={}){return {mode:'À emporter',items:[{productId:product.id,quantity:1,choices:validChoices(product)}],customer,paymentMethod:'simulation',...changes};}
async function expectDenied(response:APIResponse){expect([401,403,404]).toContain(response.status());}

test('API : catalogue réel, santé et protection CSRF des mutations',async({request})=>{
 expect((await request.get('/api/health/')).ok()).toBeTruthy();const products=await catalog(request);expect(products.length).toBeGreaterThanOrEqual(8);expect(products.some(p=>p.id===90)).toBeTruthy();
 const settings=await request.get('/api/restaurant/');expect(settings.ok()).toBeTruthy();expect(await settings.json()).toMatchObject({name:'STC',demoMode:true,paymentMode:'simulation'});
 const token=await csrf(request);const missingCsrf=await request.post('/api/orders/',{data:body(products.find(p=>p.id===6)!)});expect(missingCsrf.status()).toBe(403);
 const foreign=await request.post('/api/auth/password-reset/',{data:{email:'x@example.com'},headers:{'X-CSRFToken':token,Origin:'https://evil.example'}});expect(foreign.status()).toBe(403);
 await expectDenied(await request.get('/api/orders/'));await expectDenied(await request.get('/api/addresses/'));await expectDenied(await request.get('/api/favorites/'));
});

test('API : prix et options recalculés, commande persistante et idempotence',async({request,playwright})=>{
 const products=await catalog(request);const product=products.find(p=>p.id===1)!;const selected=validChoices(product);const cheddar=product.optionGroups.flatMap(g=>g.choices).find(c=>c.name==='Cheddar supplémentaire');expect(cheddar).toBeTruthy();selected.push(cheddar!.id);
 const quantity=2;const expectedUnit=Number((product.price+product.optionGroups.flatMap(g=>g.choices).filter(c=>selected.includes(c.id)).reduce((sum,c)=>sum+c.price,0)).toFixed(2));
 const payload=body(product,{mode:'Livraison',items:[{productId:product.id,quantity,choices:selected}],customer:{...customer,address:'24 rue du Test',postal:'75011',city:'Paris'}});
 const key=randomUUID();const response=await write(request,'/api/orders/',payload,'POST',{'Idempotency-Key':key});expect(response.status(),(await response.text()).slice(0,500)).toBe(201);const order=await response.json();
 expect(order.id).toMatch(/^STC-/);expect(order.accessToken).toBeTruthy();expect(order.status).toBe('confirmed');expect(order.paymentStatus).toBe('simulated');expect(order.subtotal).toBe(Number((expectedUnit*quantity).toFixed(2)));expect(order.deliveryFee).toBe(3.9);expect(order.total).toBe(Number((expectedUnit*quantity+3.9).toFixed(2)));expect(order.lines[0].unitPrice).toBe(expectedUnit);expect(order.history[0].status).toBe('confirmed');
 const replay=await write(request,'/api/orders/',payload,'POST',{'Idempotency-Key':key});expect(replay.status()).toBe(200);expect((await replay.json()).id).toBe(order.id);
 const conflict=await write(request,'/api/orders/',{...payload,mode:'À emporter'},'POST',{'Idempotency-Key':key});expect(conflict.status()).toBe(409);
 const outsider=await playwright.request.newContext({baseURL:base,extraHTTPHeaders:{Origin:base}});
 try{await expectDenied(await outsider.get(`/api/orders/${order.id}/`));await expectDenied(await outsider.get(`/api/orders/${order.id}/?token=incorrect`));await expectDenied(await outsider.get(`/api/orders/${order.id}/?token=${encodeURIComponent('💥')}`));const authorized=await outsider.get(`/api/orders/${order.id}/?token=${encodeURIComponent(order.accessToken)}`);expect(authorized.ok()).toBeTruthy();expect((await authorized.json()).total).toBe(order.total);}finally{await outsider.dispose();}
});

test('API : rejet des options, quantités et livraisons invalides, prix manipulé sans effet',async({request})=>{
 const products=await catalog(request);const product=products.find(p=>p.id===1)!;const cookie=products.find(p=>p.id===6)!;
 for(const payload of [body(product,{items:[{productId:product.id,quantity:1,choices:[]}]}),body(product,{items:[{productId:product.id,quantity:1,choices:['choix-inexistant']}]}),body(cookie,{items:[{productId:cookie.id,quantity:0,choices:[]}]}),body(cookie,{mode:'Livraison',customer:{...customer,address:'1 rue du Test',postal:'99999',city:'Inconnue'}})]){
  const response=await write(request,'/api/orders/',payload,'POST',{'Idempotency-Key':randomUUID()});expect(response.status(),(await response.text()).slice(0,500)).toBe(400);
 }
 const tampered=await write(request,'/api/orders/',body(cookie,{items:[{productId:cookie.id,quantity:1,choices:[],unitPrice:0.01}],total:0.01}),'POST',{'Idempotency-Key':randomUUID()});
 expect([201,400]).toContain(tampered.status());if(tampered.status()===201){expect((await tampered.json()).total).toBe(cookie.price);}
});

test('API : comptes, adresses, favoris et séparation stricte des clients',async({request,playwright})=>{
 const email=await register(request);const me=await request.get('/api/auth/me/');expect((await me.json()).user.email).toBe(email);
 const favorite=await write(request,'/api/favorites/',{productIds:[1,3]},'PUT');expect(favorite.ok()).toBeTruthy();expect((await request.get('/api/favorites/')).ok()).toBeTruthy();expect(await (await request.get('/api/favorites/')).json()).toEqual([1,3]);
 const addressPayload={label:'Maison',name:customer.name,phone:customer.phone,address:'24 rue du Test',postal:'75011',city:'Paris'};const created=await write(request,'/api/addresses/',addressPayload);expect(created.status(),(await created.text()).slice(0,500)).toBe(201);const address=await created.json();
 const patch=await write(request,`/api/addresses/${address.id}/`,{label:'Bureau'},'PATCH');expect(patch.ok()).toBeTruthy();expect((await patch.json()).label).toBe('Bureau');
 const products=await catalog(request);const orderResponse=await write(request,'/api/orders/',body(products.find(p=>p.id===6)!),'POST',{'Idempotency-Key':randomUUID()});expect(orderResponse.status()).toBe(201);const order=await orderResponse.json();expect((await (await request.get('/api/orders/')).json()).some((o:{id:string})=>o.id===order.id)).toBeTruthy();
 const outsider=await playwright.request.newContext({baseURL:base,extraHTTPHeaders:{Origin:base}});try{await register(outsider);expect(await (await outsider.get('/api/addresses/')).json()).toEqual([]);await expectDenied(await write(outsider,`/api/addresses/${address.id}/`,{label:'Interdit'},'PATCH'));await expectDenied(await outsider.get(`/api/orders/${order.id}/`));expect(await (await outsider.get('/api/orders/')).json()).toEqual([]);}finally{await outsider.dispose();}
 const removed=await write(request,`/api/addresses/${address.id}/`,undefined,'DELETE');expect(removed.status()).toBe(204);expect(await (await request.get('/api/addresses/')).json()).toEqual([]);
 expect((await write(request,'/api/auth/logout/',{})).ok()).toBeTruthy();expect((await (await request.get('/api/auth/me/')).json()).user).toBeNull();
 const denied=await write(request,'/api/auth/login/',{email,password:'mot-de-passe-incorrect'});expect([400,401,403]).toContain(denied.status());const login=await write(request,'/api/auth/login/',{email,password});expect(login.ok()).toBeTruthy();expect((await login.json()).user.email).toBe(email);
});

test('API : réinitialisation sans divulgation de compte ni de jeton et webhook non signé refusé',async({request})=>{
 const email=await register(request);const known=await write(request,'/api/auth/password-reset/',{email});const unknown=await write(request,'/api/auth/password-reset/',{email:`absent-${randomUUID()}@example.com`});expect(known.ok()).toBeTruthy();expect(unknown.ok()).toBeTruthy();expect(await known.json()).toEqual(await unknown.json());
 const invalid=await write(request,'/api/auth/password-reset-confirm/',{uid:'invalid',token:'invalid',password});expect(invalid.status()).toBe(400);
 const webhook=await request.post('/api/payments/webhook/',{data:{id:'evt_fake',type:'checkout.session.completed'}});expect([400,503]).toContain(webhook.status());
});

test('API : deux premières soumissions invitées concurrentes créent une seule commande',async({request})=>{
 const token=await csrf(request);const key=randomUUID();const payload={mode:'À emporter',items:[{productId:6,quantity:1,choices:[]}],customer,paymentMethod:'simulation'};
 const responses=await Promise.all([1,2].map(()=>request.post('/api/orders/',{data:payload,headers:{'X-CSRFToken':token,'Idempotency-Key':key}})));
 for(const response of responses)expect([200,201],(await response.text()).slice(0,500)).toContain(response.status());
 const orders=await Promise.all(responses.map(response=>response.json()));expect(orders[0].id).toBe(orders[1].id);expect(orders[0].total).toBe(3.9);expect(orders[1].total).toBe(3.9);
});
