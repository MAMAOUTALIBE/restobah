# Audit des écrans et interactions — 1er novembre 2026

## Périmètre et méthode

Audit indépendant UX/UI sur la référence `0c5c588`, avant les corrections de ce nouveau lot. La palette et les gabarits existants sont conservés. Skills lus : `project-tester` et `browser:control-in-app-browser`. Aucun outil `node_repl/js` de pilotage du navigateur n’étant exposé après découverte, les contrôles utilisent Chromium via Playwright local.

Une instance jetable propre a été utilisée sur les ports **8003/5176** : SQLite, accès gérant, e-mails et médias temporaires. Les services habituels, la base locale et les données en ligne n’ont pas été utilisés pour les écritures. Les deux exécutions terminées ont nettoyé leurs processus et répertoires temporaires. Les seules connexions CRM portent sur l’administrateur synthétique de cette recette ; aucun identifiant réel n’apparaît dans ce rapport ou ses captures.

Le harnais d’audit est hors dépôt : `/tmp/stc-pages-audit-20261101/audit.spec.cjs`. Aucun composant ou test produit n’a été modifié par ce rôle. Les captures et résultats sont aussi hors dépôt ; les anciennes captures suivies par Git n’ont pas été remplacées.

## Résultats exécutés

| Contrôle | Résultat |
|---|---|
| Parcours publics et quatre rubriques/formulaires CRM, aux largeurs 320, 390, 768 et 1280 px | **8 tests réussis**, 29,8 s |
| Contrôles de largeur, navigation et pages dans cette matrice | **82 observations réussies**, aucun débordement horizontal |
| Captures produites | **68**, sans formulaire de mot de passe rempli |
| Revue visuelle directe | Accueil 320 ; fiche/options 320 ; panier 390 ; inscription 320 ; FAQ 768 ; carte CRM 1280 ; restaurant CRM 320 |
| Erreurs JavaScript dans les huit parcours | Aucune |
| Écritures métier de ces parcours | Aucune : les soumissions positives ne font pas partie de cette matrice visuelle ; les connexions créent seulement des sessions |
| Reproduction supplémentaire du clavier pendant envoi du panier | **1 échec confirmé**, décrit ci-dessous |

Une première tentative du harnais a été interrompue après découverte d’un libellé de sélecteur erroné dans le script temporaire (`Masquer les filtres` au lieu de `Afficher les filtres`). Cette erreur de harnais a été corrigée avant l’exécution finale des huit tests ; elle n’est pas comptée comme défaut produit.

## Matrice page par page, section par section

Les lignes suivantes concernent les quatre largeurs, sauf mention contraire. « PASS » signifie que les contrôles indiqués ont été exécutés ; il ne vaut pas validation d’un service externe ou d’un comportement non décrit.

| Page ou section | Contrôle réellement effectué | État |
|---|---|---|
| Accueil | Chargement des cartes et des sections, corps sans débordement, capture | PASS |
| En-tête et menu mobile | Sur 320/390 : ouverture et navigation vers Carte, Favoris, Commandes, Compte et Accueil ; fermeture après sélection | PASS |
| Navigation ordinateur/tablette | Accès compte, liens de footer et contenu adapté à la largeur | PASS |
| Carrousel | Sélection de la promotion 2 puis retour à la promotion 1 ; titre attendu visible | PASS |
| Recherche | Résultat vide explicite, recherche accentuée et en majuscules, effacement | PASS |
| Filtres et tri | Végétarien, tri par prix avec vérification de l’ordre affiché, réinitialisation et fermeture | PASS |
| Catégories | Sélection Boissons puis Tout, nombre de cartes correspondant | PASS |
| Cartes | Prix/actions affichés dans la matrice ; ouverture de fiche ; favoris via touche Entrée | PASS |
| Fiche plat et options | Refus sans choix obligatoire, sélection de sauce, quantité, absence de débordement ; fermeture par Échap et retour du focus au bouton d’ouverture | PASS |
| Favoris | Ajout, affichage d’une seule carte, retrait et état vide ; retour à la carte | PASS |
| Panier | Ajout d’un plat, augmentation/réduction de quantité, mode Livraison, accès aux coordonnées, validation native des champs requis vides | PASS pour ces contrôles |
| Clavier du panier pendant validation | Tab depuis Fermer après désactivation des champs de commande | **FAIL — défaut UI-01** |
| Commandes client | Navigation et état invité vide lisible | PASS pour l’état vide ; suivi d’une commande réelle à couvrir par les autres lots fonctionnels |
| Compte : connexion | Champs et action accessibles, rendu et largeur | PASS pour le formulaire initial |
| Compte : inscription | Changement de mode, champs de confirmation visibles, rendu vide | PASS pour le formulaire initial |
| Compte : mot de passe oublié | Accès au formulaire et action d’envoi visible, retour sans compte | PASS pour le formulaire initial ; aucun e-mail réel envoyé |
| Footer | Liens Favoris/Commandes et ouverture/fermeture des trois fenêtres d’information | PASS |
| FAQ | Contenu visible et fermeture par bouton | PASS |
| Allergènes | Fenêtre et contenu visibles, fermeture | PASS pour l’interface ; compositions réelles non attestées |
| Confidentialité | Fenêtre de démonstration lisible et fermable | PASS pour l’interface de démonstration ; documents commerciaux non attestés |
| Connexion CRM | Formulaire vide capturé, vraie connexion avec les accès jetables | PASS |
| CRM Accueil | HTTP 200, quatre destinations, destination active unique, contrôle des liens par hit-testing | PASS |
| CRM Commandes | HTTP 200 et état courant, navigation active, largeur | PASS pour l’écran ; transitions couvertes par les autres lots métier |
| CRM Ma carte | HTTP 200 ; boutons Ajouter, disponibilité et Modifier accessibles au hit-testing sans soumission | PASS |
| CRM Mon restaurant | HTTP 200 ; champs et boutons Enregistrer, Ajouter un créneau, Ajouter la fermeture accessibles ; largeur | PASS pour la présentation ; aucune configuration enregistrée par ce lot |
| CRM Ajouter/Modifier un plat | HTTP 200 ; nom, prix et bouton Enregistrer accessibles ; rendu sans débordement | PASS pour les formulaires ; mutations à couvrir par les lots métier |

## Défaut UI-01 — le focus peut quitter le panier pendant son envoi

**Priorité P2, reproductible.** L’utilisateur au clavier peut quitter la fenêtre pendant qu’elle reste ouverte avec `aria-modal="true"`. Le contexte annoncé et la position réelle du focus divergent ; une connexion lente rend ce cas observable.

### Reproduction effectuée

1. Sur 390 px, ajouter un Cookie Choco au panier et ouvrir les coordonnées à emporter.
2. Renseigner des coordonnées synthétiques valides.
3. Intercepter le POST `/api/orders/` et le maintenir en attente. La requête n’atteint jamais le serveur métier.
4. Valider : le bouton affiche « Validation en cours… » et le fieldset est désactivé.
5. Donner le focus au bouton Fermer, puis presser Tab.

**Attendu :** le focus reste dans le dialogue, ici sur son unique contrôle encore actif ou sur le conteneur.

**Observé :** `document.activeElement` devient `BODY`, sans ancêtre `[role="dialog"]`, alors que le fieldset est encore désactivé. Le test échoue sur `inDialog === true` ; durée 6,0 s. Le harnais libère ensuite la requête interceptée en l’abandonnant ; aucune commande n’a été créée.

Preuve compacte : `/tmp/stc-pages-audit-20261101/busy-modal-focus-summary.json` : `activeTagAfterTab=BODY`, `inDialog=false`, `fieldsetDisabled=true`, `businessWrites=0`.

### Cause et correction minimale proposée

`src/components/Modal.tsx` construit ses contrôles avec `:not([disabled])`. Cette sélection inclut les champs qui héritent de la désactivation de leur fieldset sans porter eux-mêmes l’attribut. Le dernier contrôle calculé peut donc être une zone de texte non focalisable. Le gestionnaire Tab ne traite pas non plus un focus déjà sorti du dialogue.

Corriger le calcul des contrôles réellement focalisables, notamment en excluant `:disabled`, puis gérer le bouclage premier/dernier et le retour au conteneur ou au premier contrôle quand le focus est extérieur. Préserver Échap, le clic extérieur et le retour au bouton d’ouverture. Retester un panier normal, en attente réseau, un paiement en attente et les fenêtres FAQ/plat au clavier, sur mobile et ordinateur.

## Commandes et preuves

Matrice finale réussie :

```sh
STC_E2E_API_PORT=8003 STC_E2E_WEB_PORT=5176 python3 scripts/e2e.py --config=/tmp/stc-pages-audit-20261101/playwright.config.cjs --workers=1 --output=/tmp/stc-pages-audit-20261101/test-results-final
```

Reproduction rouge du focus :

```sh
STC_E2E_API_PORT=8003 STC_E2E_WEB_PORT=5176 python3 scripts/e2e.py --config=/tmp/stc-pages-audit-20261101/playwright.config.cjs --grep 'clavier de la modale' --workers=1 --output=/tmp/stc-pages-audit-20261101/focus-results
```

Les 82 observations sont dans `matrix-results.json`, les captures dans `captures/`, les statuts Playwright dans chacun des dossiers de résultats précités. Ce sont des preuves temporaires locales ; elles ne remplacent pas les tests durables à ajouter avec la correction.

## Limites avant livraison commerciale

- Ce lot visuel ne valide pas de vrais paiements, une réception SMTP, une réinitialisation reçue par e-mail, la validité des documents légaux ou la composition réelle des plats. Ces points demandent des preuves séparées.
- La copie auditée présente encore une interface de démonstration. En source, `Footer.tsx` propose des explications génériques, mais pas de documents complets Mentions légales/CGV fournis par le client. Le contenu métier ne doit pas être inventé pour annoncer une livraison commerciale complète.
- Les mutations compte/adresses, le suivi réel des commandes, les refus serveur, les permissions et les transitions relèvent des suites fonctionnelles et de sécurité complémentaires du coordinateur ; les contrôles de présentation ci-dessus ne sont pas présentés comme leur équivalent.

**Gate de cet audit : FAIL ciblé tant que UI-01 n’est pas corrigé et retesté.** Aucun autre défaut bloquant de disposition n’a été observé dans la matrice décrite.
