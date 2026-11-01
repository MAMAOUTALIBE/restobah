# CRM STC — suivi de fiabilité après la mise en ligne

Date : 1er novembre 2026. Ce suivi distingue le déploiement antérieur, les corrections du code de travail et leurs preuves de validation. Il complète les rapports de livraison locale sans en réécrire l’historique.

## Référence déjà déployée

Le coordinateur a confirmé la mise en ligne du CRM sur la démonstration existante : [espace gérant STC](https://stc.srv2086522.hstgr.cloud/crm/).

- `c111967` : CRM et interface mobile.
- `e02cdd0` : correction de la redirection `/crm` pour conserver HTTPS.

Ces deux versions ont été déployées avec succès le 1er novembre. Leurs identifiants et leur ordre sont également vérifiables dans l’historique Git. La démonstration et le paiement simulé restent actifs ; ce suivi n’annonce aucune ouverture commerciale ni activation SMTP ou Stripe réel.

Pour une publication ultérieure, consulter le marqueur **`.runtime/deployed-revision` sur le serveur** et le compte rendu de contrôle correspondant. Le commit présent dans la copie de travail, le dernier commit du dépôt ou une validation locale ne suffisent pas à identifier la version effectivement publiée. Les états ci-dessous sont ceux de cette étape de rédaction, pas une interdiction de déployer une version suivante.

## État des corrections suivantes

| Sujet | Code et contrôle local |
|---|---|
| Reprise après refus de sécurité d’un formulaire CRM | **PASS indépendant**, contrôles détaillés ci-dessous. |
| Aperçu photo après des sélections rapprochées | **PASS indépendant**, courses et enregistrement réel contrôlés. |

La publication est contrôlée séparément après le commit : son état et ses preuves restent dans les fichiers privés `.runtime/deployments/<révision>/state.json` et `online-validation.json` du serveur. Le marqueur indiqué plus haut identifie la version effectivement publiée.

## 1. Reprendre un formulaire refusé

### Défaut constaté

Le gestionnaire de refus CSRF retournait le même objet JSON pour toutes les routes. Un formulaire du CRM refusé pouvait donc quitter l’interface du gérant pour afficher une réponse technique brute, sans parcours de reprise explicite.

### Correction contrôlée

Les routes CRM reçoivent une page HTML française, toujours avec le statut **403**, annonçant **« Votre demande n’a pas été enregistrée »**. Elle propose seulement des liens GET vers un formulaire ou une rubrique connus. Elle ne rejoue pas le POST et n’affiche ni saisie, ni jeton, ni raison technique du refus. Les informations métier déjà enregistrées restent inchangées.

La réponse CRM est privée et non stockée en cache. Les autres routes, notamment API et administration, conservent leur réponse JSON prévue. Le contrôle CSRF demeure actif : cette correction améliore le message et le retour au formulaire, sans contourner le refus.

Fichiers concernés : `backend/shop/views.py`, `backend/shop/templates/shop/crm/csrf_failure.html`, `backend/shop/test_crm_csrf.py`, `tests/crm-errors.spec.ts`.

### Preuves reçues et revue indépendante

Le coordinateur a transmis le gate indépendant **PASS** avec les résultats réellement exécutés suivants :

- **9 tests Django ciblés réussis**, 0,219 s lors de la reprise indépendante : connexion, création et édition refusées sans écriture, reprises vers des destinations autorisées, origines/référents refusés, absence de fuite des valeurs, réponses API inchangées et préfixes voisins exclus. Source : `shop.test_crm_csrf`.
- **4 parcours navigateur réussis**, 5,1 s, en 1280 et 390 px : refus de connexion puis connexion valide ; édition refusée sans mutation puis réouverture de la fiche enregistrée. Les parcours utilisent l’instance et les médias temporaires, pas les données de la démonstration en ligne. Les quatre POST refusés ont bien répondu 403 ; aucune autre erreur HTTP ni erreur JavaScript n’a été observée.
- Suite serveur : **119 tests collectés, 118 réussis et un ignoré spécifique PostgreSQL**. Le test ignoré n’est pas présenté comme exécuté sur PostgreSQL lors de cette reprise.
- `npm run check` : **PASS** communiqué par le coordinateur.

Les 9 cas ciblés appartiennent à la suite serveur ; ils ne doivent pas être additionnés une seconde fois au total. Les sources et cas ont été relus pour rédiger ce suivi ; le rédacteur de ce document n’a pas exécuté lui-même ces lots.

Commande navigateur effectivement exécutée par la recette :

```sh
python3 scripts/e2e.py tests/crm-errors.spec.ts --project=desktop --project=mobile --workers=1 --output=/tmp/restobah-crm-csrf-e2e-final-results
```

## 2. Faire correspondre l’aperçu photo à la sélection actuelle

### Défaut reproduit avant correction

Le code de sélection photo créait un `FileReader` pour chaque choix sans invalider les callbacks précédents. Si une première lecture finissait après la suivante, son aperçu remplaçait celui du fichier actuellement sélectionné. Ce décalage pouvait aussi remplacer le message de refus d’un nouveau fichier invalide ou afficher une photo après effacement de la sélection.

La reproduction a utilisé la véritable ressource `crm.js` dans un DOM Chromium isolé, avec l’ordre de fin des lectures contrôlé. Aucun appel HTTP, enregistrement de plat ou accès à une base n’a été nécessaire.

| Cas exécuté avant correction | Observation | Résultat initial |
|---|---|---|
| Deux photos valides, première lecture ralentie | Fichier courant `fast-second.png`, aperçu `slow-first.png`. | Échec reproduit |
| Photo valide lente, puis nouveau fichier invalide | L’ancienne lecture remplace le refus par un message de nouvelle photo sélectionnée. | Échec reproduit |
| Photo valide lente, puis sélection effacée | Aucune photo sélectionnée, mais l’ancien callback affiche encore la nouvelle photo. | Échec reproduit |

Script de diagnostic hors dépôt : `/tmp/restobah-crm-photo-race-repro.mjs`, avec les arguments `race`, `invalid` et `clear`. Ce fichier temporaire n’est pas un artefact durable de livraison.

### Correction et validation indépendante : PASS

Chaque changement de sélection invalide les retours précédents et annule une lecture encore active. Les callbacks vérifient leur lecteur et leur révision avant de modifier l’aperçu. Une sélection vide, invalide ou illisible restaure la photo enregistrée ou le visuel vide initial. Un retour tardif ne peut plus effacer l’erreur de la sélection actuelle ni afficher un ancien fichier. Le reste du JavaScript, les styles et la sauvegarde serveur restent inchangés.

Fichiers concernés : `backend/shop/static/shop/crm.js` et `tests/crm-photo.spec.ts`.

Contrôles réellement exécutés par la validation indépendante :

- Les **trois reproductions initiales passent** après correction.
- **Sept contrôles indépendants passent**, dont des callbacks livrés même après l’annulation, le refus après une lecture terminée et la restauration du visuel enregistré ou vide.
- **33 tests photo et 9 tests de rafraîchissement passent** sur mobile, tablette et ordinateur, soit 42 tests en 7,7 s. La suite photo inclut un vrai `FileReader` et des lectures contrôlées sans écriture métier.
- Les **quatre parcours CSRF repassent**, 5,1 s : quatre refus 403 attendus, aucune erreur HTTP inattendue ni erreur JavaScript.
- **Un parcours d’enregistrement réel passe**, 48,2 s, sur instance jetable : photo, prix, disponibilité, persistance et synchronisation avec un site client déjà ouvert.
- ESLint explicite du JavaScript CRM et des nouveaux tests, ainsi que `git diff --check`, passent.

Le lot navigateur final représente **47 tests réussis** : 33 photo, 9 rafraîchissement, 4 CSRF et 1 enregistrement réel. Les reproductions et relances intermédiaires ne sont pas additionnées une seconde fois. La suite serveur déjà exécutée couvre 119 cas collectés : 118 réussis et un cas propre à PostgreSQL ignoré sur SQLite. Aucun code serveur n’a changé après cette exécution.

Commandes finales :

```sh
npx playwright test tests/crm-photo.spec.ts tests/crm-refresh.spec.ts --project=desktop --project=tablet --project=mobile --output=/tmp/restobah-crm-photo-refresh-validation-results
python3 scripts/e2e.py tests/crm-errors.spec.ts --project=desktop --project=mobile --workers=1 --output=/tmp/restobah-crm-photo-csrf-regression-results
python3 scripts/e2e.py tests/crm.spec.ts --grep 'carte, photo, prix et disponibilité persistent' --project=desktop --workers=1 --output=/tmp/restobah-crm-photo-save-validation-results
```

Les bases, médias et accès de ces recettes sont temporaires et ont été nettoyés. Aucune écriture métier de production n’a été effectuée par ces tests.

## Documentation pour le gérant

Le [guide du gérant](GUIDE_GERANT.md) décrit les quatre rubriques et les boutons réellement présents, dont le message de reprise du formulaire. Il ne contient aucun identifiant, mot de passe ou paramètre de déploiement privé.

## Limites du présent suivi

- Le déploiement confirmé de `c111967` et `e02cdd0` ne prouve pas la mise en ligne des deux corrections ultérieures.
- Aucun nouveau test PostgreSQL, paiement réel, envoi SMTP, test de charge ou changement d’infrastructure n’est revendiqué ici.
- Aucun défaut restant n’a été identifié dans le périmètre de ces deux corrections après les revues indépendantes. Les preuves locales précèdent le contrôle distinct de publication.
