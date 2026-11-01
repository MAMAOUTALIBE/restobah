import {expect,test,type Page} from '@playwright/test';
import type {Product,RestaurantSettings} from '../src/types';

const product:Product={id:6,name:'Le Cookie Test',category:'Desserts',price:3.9,description:'Un cookie de recette.',image:'cookie'};
const settings:RestaurantSettings={name:'STC',address:'Adresse de recette',city:'Paris',hours:'11h – 23h',days:'Tous les jours',deliveryFee:3.9,minDeliveryTotal:0,deliveryPostalCodes:['75011'],orderingEnabled:true,isOpen:true,demoMode:true,paymentMode:'simulation',pickupEnabled:true,deliveryEnabled:true};

async function catalogue(page:Page){
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    const data=path==='/api/products/'?[product]:path==='/api/restaurant/'?settings
      :path==='/api/categories/'?[{name:'Desserts',position:0}]:path==='/api/auth/me/'?{user:null}:{};
    await route.fulfill({json:data});
  });
  await page.goto('/');
  await expect(page.locator('.product-card')).toHaveCount(1);
}

test('la modale boucle au clavier, récupère un focus extérieur et le rend après Échap',async({page})=>{
  await catalogue(page);
  await page.evaluate(()=>{document.body.style.overflow='auto';});
  const opener=page.getByRole('button',{name:'Ajouter Le Cookie Test',exact:true});
  await opener.click();
  const dialog=page.getByRole('dialog');
  const close=dialog.getByRole('button',{name:'Fermer',exact:true});
  const add=dialog.getByRole('button',{name:'Ajouter · 3,90 €',exact:true});
  await expect(dialog).toBeFocused();
  await page.keyboard.press('Tab');await expect(close).toBeFocused();
  await page.keyboard.press('Shift+Tab');await expect(add).toBeFocused();
  await page.keyboard.press('Tab');await expect(close).toBeFocused();
  await page.getByRole('button',{name:'Afficher les filtres',exact:true}).focus();
  await expect(close).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  expect(await page.evaluate(()=>document.body.style.overflow)).toBe('auto');
});

test('une modale sans contrôle actif garde le focus sur son conteneur',async({page})=>{
  await catalogue(page);
  await page.getByRole('button',{name:'Ajouter Le Cookie Test',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.locator('button,input,select,textarea').evaluateAll(nodes=>{
    for(const node of nodes)(node as HTMLButtonElement|HTMLInputElement).disabled=true;
  });
  await dialog.focus();
  await page.keyboard.press('Tab');await expect(dialog).toBeFocused();
  await page.keyboard.press('Shift+Tab');await expect(dialog).toBeFocused();
  await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);
});

test('le panier ouvert depuis une notification garde seul le focus et Échap ferme une modale à la fois',async({page})=>{
  const errors:string[]=[];
  page.on('pageerror',error=>errors.push(error.message));
  await catalogue(page);
  await page.evaluate(()=>{document.body.style.overflow='auto';});
  const opener=page.getByRole('button',{name:'Ajouter Le Cookie Test',exact:true});
  await opener.click();
  await page.getByRole('dialog').getByRole('button',{name:'Ajouter · 3,90 €',exact:true}).click();
  await opener.click();
  await page.getByRole('button',{name:'Voir le panier',exact:true}).click();
  const basket=page.getByRole('dialog',{name:'Mon panier',exact:true});
  const productDialog=page.getByRole('dialog',{name:'Le Cookie Test',exact:true,includeHidden:true});
  await expect(page.locator('[role="dialog"]')).toHaveCount(2);
  await expect(productDialog).toHaveJSProperty('inert',true);
  await expect(productDialog).toHaveAttribute('aria-hidden','true');
  await expect(basket).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(basket.getByRole('button',{name:'Fermer',exact:true})).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(basket).toHaveCount(0);
  await expect(productDialog).toBeVisible();
  await expect(productDialog).toHaveJSProperty('inert',false);
  expect(await page.evaluate(()=>document.body.style.overflow)).toBe('hidden');
  expect(await productDialog.evaluate(dialog=>dialog.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Escape');
  await expect(productDialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  expect(await page.evaluate(()=>document.body.style.overflow)).toBe('auto');
  expect(errors).toEqual([]);
});

test('le panier occupé exclut les champs désactivés par le fieldset et garde le focus',async({page})=>{
  const errors:string[]=[];
  page.on('pageerror',error=>errors.push(error.message));
  await catalogue(page);
  await page.getByRole('button',{name:'Ajouter Le Cookie Test',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Ajouter · 3,90 €',exact:true}).click();
  await page.getByRole('button',{name:/Mon panier/}).click();
  await page.getByRole('button',{name:'Passer commande',exact:true}).click();
  await page.getByLabel('Nom complet',{exact:true}).fill('Client Test');
  await page.getByLabel('Adresse e-mail',{exact:true}).fill('client-test@example.com');
  await page.getByLabel('Téléphone',{exact:true}).fill('0612345678');
  let release:()=>void=()=>{};
  let submissions=0;
  const pending=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/api/orders/',async route=>{
    expect(route.request().method()).toBe('POST');
    submissions++;
    await pending;
    await route.fulfill({status:503,json:{detail:'Échec de recette prévu, aucune commande créée.'}});
  });
  try{
    await page.getByRole('button',{name:'Valider la commande de démonstration',exact:true}).click();
    await expect.poll(()=>submissions).toBe(1);
    const dialog=page.getByRole('dialog');
    await expect(dialog.locator('fieldset')).toHaveJSProperty('disabled',true);
    const close=dialog.getByRole('button',{name:'Fermer',exact:true});
    await close.focus();
    await page.keyboard.press('Tab');await expect(close).toBeFocused();
    await page.keyboard.press('Shift+Tab');await expect(close).toBeFocused();
    await page.keyboard.press('Tab');await expect(close).toBeFocused();
    release();
    await expect(dialog.getByRole('alert')).toHaveText('Échec de recette prévu, aucune commande créée.');
    await expect(dialog.getByLabel('Nom complet',{exact:true})).toHaveValue('Client Test');
    await expect(dialog.locator('fieldset')).toHaveJSProperty('disabled',false);
    await close.focus();await page.keyboard.press('Shift+Tab');
    await expect(dialog.getByRole('button',{name:'Valider la commande de démonstration',exact:true})).toBeFocused();
    expect(errors).toEqual([]);
    expect(submissions).toBe(1);
  }finally{release();}
});
