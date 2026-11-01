# Adaptation ordinateur et tablette STC

## Comportement au 1er novembre 2026

| Largeur de fenêtre | Accueil | Catalogue |
|---|---|---|
| Jusqu’à 760 px | Trois plats, navigation mobile | Une colonne, photo à 50 % |
| 761–1024 px | Six plats, présentation tablette conservée | Une colonne, hauteur proportionnelle à la largeur |
| 1025–1439 px | Six plats | Deux colonnes de cartes horizontales |
| À partir de 1440 px | Six plats | Trois colonnes de cartes horizontales |

La limite de produits réagit au redimensionnement avec `useMediaQuery`. Les filtres et la vue **Carte** permettent toujours de consulter tous les plats.

Les règles ordinateur sont isolées dans `src/desktop.css`, importé en dernier dans `src/main.tsx`. Toutes sont limitées aux fenêtres d’au moins 1025 px. Les styles existants restent responsables du mobile et de la tablette ; le nouveau fichier ne nécessite aucune modification des règles métier ni migration.

## Présentation sur ordinateur

- En-tête, contenu et footer alignés sur une largeur maximale de 1480 px ; navigation centrale et boutons d’au moins 44 px.
- Diaporama de 300 à 330 px de haut, photographie proportionnelle en fond, titre et bouton équilibrés.
- Sept catégories lisibles ; grille de plats régulière, marges crème et variantes violettes conservées. La hauteur minimale des cartes est de 224 px et augmente avec le contenu, notamment avec un texte agrandi.
- Fiche produit de 960 px maximum : photo à gauche, choix à droite, défilement des options et navigation clavier conservés.
- Panier de 680 px maximum, puis 1000 px au passage aux coordonnées : récapitulatif à gauche, formulaire à droite. Le wrapper `.cart-summary` ne change aucun calcul ni action de commande.
- Compte, profil, commandes et favoris adaptés aux grandes largeurs ; champs et textes plus lisibles. Les états de session et les permissions restent gérés par le code existant.

## Vérification

Les captures avant/après sont enregistrées dans `artifacts/desktop-before/` et `artifacts/desktop-after/`. Le fichier `tests/desktop-layout.spec.ts` contrôle les largeurs 1025, 1280, 1440 et 1920 px, les cartes, les textes agrandis, les fenêtres produit/panier et les autres vues client.

La recette indépendante utilise `scripts/e2e.py` et des bases jetables : interactions et régressions mobile/tablette/ordinateur, puis parcours distincts avec règlement sur place. Les contrôles statiques passent par `npm run check`. Les résultats et limites de cette livraison sont consignés dans `artifacts/desktop-validation-2026-11-01.json`.

Les captures locales et les parcours de recette ne créent aucune commande sur le site public. Les données d’authentification et de commande des tests fonctionnels restent dans les environnements jetables.
