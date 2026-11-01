import {expect,test,type Page} from '@playwright/test';
import type {RestaurantSettings} from '../src/types';

const settings:RestaurantSettings={
 name:'Restaurant de recette',address:'1 place du Test',city:'Lyon',hours:'12h – 14h',days:'Lundi',
 deliveryFee:0,minDeliveryTotal:0,deliveryPostalCodes:[],orderingEnabled:true,isOpen:true,demoMode:false,
 paymentMode:'on_site',pickupEnabled:false,deliveryEnabled:false,
 contactPhone:'+33 1 23 45 67 89',contactEmail:'bonjour@restaurant.fr',
 legalNoticeUrl:'https://restaurant.fr/mentions-legales',privacyUrl:'https://restaurant.fr/confidentialite',termsUrl:'https://restaurant.fr/conditions',
};
async function fixture(page:Page,overrides:Partial<RestaurantSettings>={}){
 let writes=0;
 await page.route('**/api/**',async route=>{
  if(route.request().method()!=='GET')writes++;
  const path=new URL(route.request().url()).pathname;
  const json=path==='/api/restaurant/'?{...settings,...overrides}:path==='/api/auth/me/'?{user:null}:[];
  await route.fulfill({json});
 });
 await page.goto('/');
 await expect(page.getByRole('contentinfo',{name:'Informations STC'}).getByRole('link',{name:'Appeler le restaurant'})).toHaveCount(overrides.contactPhone===''?0:1);
 return ()=>writes;
}

test('footer : liens client accessibles et compacts à 320, 390 et 1280 px',async({page})=>{
 const writes=await fixture(page);
 const footer=page.getByRole('contentinfo',{name:'Informations STC'});
 await expect(footer.getByRole('link',{name:'Appeler le restaurant'})).toHaveAttribute('href','tel:+33123456789');
 await expect(footer.getByRole('link',{name:'Écrire au restaurant'})).toHaveAttribute('href','mailto:bonjour@restaurant.fr');
 for(const [name,url] of [['Mentions légales',settings.legalNoticeUrl!],['Politique de confidentialité',settings.privacyUrl!],['Conditions de commande',settings.termsUrl!]]){
  await expect(footer.getByRole('link',{name,exact:true})).toHaveAttribute('href',url);
 }
 await expect(footer.locator('.footer-service-tags > span')).toHaveCount(0);
 await expect(footer).not.toContainText('®');
 for(const width of [320,390,1280]){
  await page.setViewportSize({width,height:900});
  await footer.scrollIntoViewIfNeeded();
  for(const name of ['Appeler le restaurant','Écrire au restaurant','Mentions légales','Politique de confidentialité','Conditions de commande']){
   const link=footer.getByRole('link',{name,exact:true});
   await expect(link).toBeVisible();
   const rect=await link.boundingBox();
   expect(rect).not.toBeNull();expect(rect!.x).toBeGreaterThanOrEqual(0);expect(rect!.x+rect!.width).toBeLessThanOrEqual(width);
   expect(rect!.height).toBeGreaterThanOrEqual(32);
  }
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 }
 await footer.getByRole('button',{name:'Questions fréquentes'}).click();
 await expect(page.getByRole('dialog')).toContainText('Quand régler ma commande ?');
 await expect(page.getByRole('dialog')).toContainText('Aucun paiement en ligne n’est demandé.');
 expect(writes()).toBe(0);
});

test('footer : informations absentes ou liens dangereux masqués, services respectés',async({page})=>{
 await fixture(page,{contactPhone:'',contactEmail:'bad\naddress',legalNoticeUrl:'javascript:alert(1)',privacyUrl:'http://restaurant.fr/',termsUrl:'https://user:secret@restaurant.fr/',pickupEnabled:true,deliveryEnabled:false});
 const footer=page.getByRole('contentinfo',{name:'Informations STC'});
 await expect(footer.getByRole('link')).toHaveCount(0);
 await expect(footer.locator('.footer-service-tags > span')).toHaveCount(1);
 await expect(footer.locator('.footer-service-tags')).toContainText('À emporter');
 await expect(footer.locator('.footer-service-tags')).not.toContainText('Livraison');
 await footer.getByRole('button',{name:'Confidentialité',exact:true}).click();
 await expect(page.getByRole('dialog',{name:'Vos données'})).toBeVisible();
});
