import {test,expect} from '@playwright/test';
import {randomUUID} from 'node:crypto';

test('compte client : inscription, favoris synchronisés et reconnexion',async({page})=>{
 const email=`stc-browser-${randomUUID()}@example.com`;const password='Stc-Browser!64x9';const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await page.getByRole('button',{name:'Ajouter Le Bucket STC aux favoris'}).click();
 await page.getByRole('button',{name:/^(Mon compte|Compte)$/}).click();await page.getByRole('button',{name:'Créer un compte',exact:true}).click();
 await page.getByLabel('Nom complet',{exact:true}).fill('Camille Test');await page.getByLabel('Adresse e-mail',{exact:true}).fill(email);await page.getByLabel('Mot de passe',{exact:true}).fill(password);await page.getByRole('button',{name:'Créer mon compte',exact:true}).click();
 await expect(page.getByRole('button',{name:'Se déconnecter',exact:true})).toBeVisible();
 await page.reload();await page.getByRole('button',{name:/^(Mon compte|Compte)$/}).click();await expect(page.getByRole('button',{name:'Se déconnecter',exact:true})).toBeVisible();
 const addresses=page.locator('.address-card');await addresses.getByRole('button',{name:'Ajouter',exact:true}).click();
 await page.getByLabel('Nom de cette adresse',{exact:true}).fill('Maison');await page.getByLabel('Destinataire',{exact:true}).fill('Camille Test');await page.getByLabel('Téléphone de livraison',{exact:true}).fill('0612345678');await page.getByLabel('Rue et numéro',{exact:true}).fill('24 rue du Test');await page.getByLabel('Code postal de l’adresse',{exact:true}).fill('75011');await page.getByLabel('Ville de l’adresse',{exact:true}).fill('Paris');await page.getByRole('button',{name:'Enregistrer l’adresse',exact:true}).click();
 await expect(addresses.getByRole('heading',{name:'Maison',exact:true})).toBeVisible();await page.getByRole('button',{name:'Modifier l’adresse Maison',exact:true}).click();await page.getByLabel('Nom de cette adresse',{exact:true}).fill('Bureau');await page.getByRole('button',{name:'Enregistrer l’adresse',exact:true}).click();await expect(addresses.getByRole('heading',{name:'Bureau',exact:true})).toBeVisible();
 await page.getByRole('button',{name:/^(Notre carte|Carte)$/}).click();await page.getByRole('button',{name:'Ajouter Le Cookie Choco',exact:true}).click();await page.getByRole('button',{name:'Ajouter · 3,90 €'}).click();await page.getByRole('button',{name:/Mon panier/}).click();await page.getByRole('button',{name:'Livraison',exact:true}).click();await page.getByRole('button',{name:'Passer commande'}).click();await page.getByLabel('Utiliser une adresse enregistrée').selectOption({label:'Bureau — 75011 Paris'});await expect(page.getByLabel('Adresse de livraison')).toHaveValue('24 rue du Test');await expect(page.getByLabel('Adresse e-mail')).toHaveValue(email);await page.getByRole('button',{name:'Valider la commande de démonstration'}).click();await expect(page.getByRole('heading',{name:/Commande STC-/})).toBeVisible();await expect(page.getByText('7,80 €',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:/^(Mon compte|Compte)$/}).click();

 await page.getByRole('button',{name:'Se déconnecter',exact:true}).click();await page.getByLabel('Adresse e-mail',{exact:true}).fill(email);await page.getByLabel('Mot de passe',{exact:true}).fill(password);await page.getByRole('button',{name:'Se connecter',exact:true}).click();await expect(page.getByRole('button',{name:'Se déconnecter',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Supprimer l’adresse Bureau',exact:true}).click();await expect(page.locator('.saved-address')).toHaveCount(0);
 await page.getByRole('contentinfo',{name:'Informations STC'}).getByRole('button',{name:'Mes favoris',exact:true}).click();await expect(page.getByRole('heading',{name:'Mes favoris',exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Retirer Le Bucket STC des favoris'})).toBeVisible();
 expect(errors).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
