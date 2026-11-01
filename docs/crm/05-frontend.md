# CRM STC — implémentation frontend

Rôle 5/10, développeur frontend. Intervention limitée aux templates `backend/shop/templates/shop/crm/` et aux ressources `backend/shop/static/shop/crm.css` et `crm.js`.

## Interface livrée

- Quatre rubriques : **Accueil**, **Commandes**, **Ma carte**, **Mon restaurant**. Barre latérale sur ordinateur, quatre destinations visibles dans une barre basse sur mobile, avec réserve pour la zone de sécurité.
- Palette crème/violet/orange, polices locales DM Sans et Outfit, contrôles explicites, cibles tactiles de 44 px et texte courant de 16 px.
- En-tête avec état réel des commandes, mention de démonstration, lien vers le site et déconnexion par POST. Aucun chiffre ou graphique illustratif.
- **Ma carte** : photos, prix français, catégorie, recherche, filtre, disponibilité écrite et bouton Modifier. Les états indisponibles restent lisibles. Le formulaire court conserve les champs et affiche les erreurs du serveur, y compris les conflits de version cachés.
- Fiche plat : aperçu de la photo enregistrée, aperçu local de la nouvelle photo, sélection JPEG/PNG/WebP, disponibilité, puis options/allergènes/préférences dans « Plus de détails ». Aucune saisie JSON.
- **Commandes** : filtres, recherche par référence/client, pagination de l’historique, lignes et options, coordonnées, suivi et seule action suivante autorisée. Les transitions et les annulations sont de vrais formulaires POST protégés ; le filtre est conservé après action.
- **Accueil** : trois indicateurs calculés par le serveur, dernières commandes et raccourcis utiles.
- **Mon restaurant** : coordonnées, prise de commandes, retrait/livraison, tarifs et zone postale, créneaux multiples, indication des fermetures après minuit, ajout de créneau et fermetures exceptionnelles. En lecture seule, les champs et mutations sont désactivés/masqués.
- Connexion et erreurs d’accès en français. Une page 403 permet de revenir au site ou de se connecter avec un autre accès gérant, sans boucle vers une page interdite. La limitation des tentatives est présentée dans l’écran de connexion.

## JavaScript progressif

Les écritures restent fonctionnelles sans JavaScript : formulaires natifs et jetons CSRF. Les boutons annoncent l’enregistrement en cours, empêchent les doubles clics et retrouvent leur état lors d’un retour via le cache du navigateur.

L’actualisation automatique concerne uniquement les fragments d’Accueil et Commandes, toutes les 15 secondes et au retour sur l’onglet. Le script :

- vérifie la réponse HTTP et l’en-tête `X-STC-Fragment` ;
- détecte une redirection de connexion ou un accès refusé et ne remplace pas les commandes par la page de connexion ;
- conserve les données affichées en cas de panne, avec un bouton Actualiser ;
- conserve les détails ouverts et ne remplace pas une zone dont une action possède le focus ;
- affiche l’heure transmise par le serveur, uniquement après un rendu valide ;
- n’actualise aucun formulaire de plat ou de réglages en cours de saisie.

Les images d’aperçu utilisent un Data URL local, compatible avec la CSP existante ; aucune photo n’est publiée avant l’enregistrement serveur.

## Contrat et coordination

Coordination effectuée avec les agents backend, sécurité et QA. Routes et contextes de `02-architecture.md` respectés ; permissions en lecture/écriture, état désiré de disponibilité, révision signée, ancien statut de commande et filtres explicites sont transmis au serveur.

Sélecteurs qui décrivent le produit : `nav[aria-label="Gestion du restaurant"]`, `article[data-product-id]`, `article[data-order-id]`, formulaires et labels français. Ils sont partagés avec QA et servent aussi au comportement progressif, sans branche spéciale de test.

## Contrôles réellement exécutés dans ce rôle

1. Compilation des **14 templates Django** avec le moteur du projet : réussie après les dernières retouches.
2. Rendu GET par `RequestFactory`, avec un opérateur synthétique autorisé, des données lues et sans écriture : Accueil, Commandes, Ma carte, création d’un plat, Mon restaurant, connexion et modification d’un plat ont répondu **200**. Ce contrôle n’est pas un test de connexion ni d’autorisation.
3. Contrôle navigateur de **Ma carte** à **1440, 390 et 320 px**, à partir du HTML serveur rendu et des ressources réelles : huit cartes affichées, aucun débordement horizontal et aucune erreur JavaScript. Captures relues à 1440 et 390 px : `/tmp/stc-crm-front-menu-{1440,390,320}.png`. Ce rendu synthétique ne remplace pas les parcours authentifiés sur l’instance isolée.
4. `npx eslint --no-ignore backend/shop/static/shop/crm.js` : réussi. L’option est nécessaire parce que la configuration générale ignore les fichiers backend.
5. `git diff --check` : réussi pendant l’implémentation ; à répéter à la validation finale.

Les fichiers HTML temporaires générés par le contrôle de rendu sont supprimés après contrôle. Aucune session, base utilisateur, photo publiée, migration ou donnée métier n’a été modifiée par ce rôle.

## Correction issue de la validation indépendante

Le responsable de validation a reproduit une course : le focus était contrôlé avant le chargement d’un fragment, mais un utilisateur pouvait choisir une action pendant cette requête. Le remplacement tardif retirait alors le bouton actif du document.

Le script vérifie désormais de nouveau le focus immédiatement avant de remplacer le fragment. Il refuse également le remplacement lorsqu’un formulaire possède une action d’enregistrement en cours (`aria-busy`). Le retour anticipé conserve les données et la dernière heure réellement affichées.

Le validateur a rejoué indépendamment trois scénarios réseau contrôlés sur le vrai `crm.js` : **focus acquis pendant la requête**, **action POST verrouillée pendant la requête**, **actualisation normale sans interaction**. Les trois ont réussi (5,9 secondes). Le lint explicite du script et `git diff --check` ont été relancés après le correctif. Le harnais local de reproduction est `/tmp/restobah-crm-refresh-focus-check.mjs` ; ce fichier temporaire n’est pas une dépendance du produit.

Une régression persistante reprend ces comportements dans **`tests/crm-refresh.spec.ts`**. Les réponses de fragment sont retenues puis libérées de manière contrôlée ; le vrai script du produit est injecté dans une page de test de même origine que le `baseURL` configuré. Aucun appel à la base ni authentification réelle n’est nécessaire pour ces cas de concurrence de l’interface.

Commande exécutée : `npx playwright test tests/crm-refresh.spec.ts --project=mobile --project=tablet --project=desktop --output=/tmp/restobah-crm-refresh-final-results` : **9 tests réussis en 3,8 secondes**. `npx eslint tests/crm-refresh.spec.ts` et le contrôle des espaces ont réussi. Le premier portage du harnais utilisait une origine externe incompatible avec l’en-tête Origin du projet ; la fixture a été alignée sur le `baseURL`, puis la suite a été relancée avec succès.

## Validation indépendante encore requise

QA et responsable de validation doivent exécuter les parcours authentifiés sur l’instance jetable : connexion, droits/CSRF, création/modification/photo/prix/disponibilité, commandes et transitions, horaires/fermetures, erreurs et persistance, synchronisation avec le site ouvert, actualisation des fragments et rendu mobile des quatre rubriques. Ce rapport ne prononce pas de gate final.
