# Adaptation ordinateur et tablette STC

## Comportement

- Jusqu’à 760 px : version mobile conservée, trois produits sur l’accueil et navigation de 44 px.
- De 761 à 1100 px : six produits sur l’accueil, grille de trois colonnes, recherche et en-tête compacts.
- Au-delà de 1100 px : quatre produits sur l’accueil, grille de quatre colonnes, contenu centré avec largeur maximale.
- Toutes les grandes tailles : en-tête fixe au défilement, photographie promotionnelle mieux cadrée, catégories regroupées, boutons et cartes plus lisibles. Le footer reste compact.

La limite de produits réagit aux changements de taille de fenêtre via `useMediaQuery`. Les règles propres aux grands écrans sont isolées dans `src/responsive.css`, chargé après les styles existants.

## Vérification

Captures : `screenshots/stc-responsive-{390,768,1024,1440,1920}.png`.

Contrôles : aucune largeur de document supérieure à la fenêtre, bouton promotionnel visible, trois/six/quatre produits selon la taille, navigation mobile conservée à 44 px. TypeScript, ESLint et compilation vérifiés.

Le projet Playwright `tablet` utilise une fenêtre de 768 × 1024 px avec prise en charge tactile et rejoue les mêmes parcours que l’ordinateur et le mobile.

Le serveur local a été synchronisé avec le code existant : sauvegarde SQLite, application des migrations déjà présentes 0004 et 0005, puis redémarrage de l’application. Aucune nouvelle règle métier ni migration n’a été introduite pour cette adaptation visuelle.

## Résultat de recette

Gate : **PASS**. `npm run check` réussi. `npx playwright test` : **58 tests réussis en environ 1 min 24 s**, aucun ignoré, couvrant API/administration et les trois projets ordinateur, tablette et mobile. Les scénarios Stripe sont des fixtures de récupération de l’interface, pas des paiements externes réels.
