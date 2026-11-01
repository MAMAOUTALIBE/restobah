# CRM STC — validation indépendante finale

Rôle 10/10, responsable de validation, 1er novembre 2026. Skills appliqués : `project-tester` et `quality-orchestrator`. Ce rôle a relu l’implémentation et les preuves ; il n’a modifié aucun code produit. Un test de remplacement de photo a été ajouté avec l’accord du coordinateur. Toutes ses écritures de recette ont utilisé la base de test Django et des médias temporaires.

## Gate : PASS

Le noyau CRM demandé est accepté dans l’environnement local contrôlé. Les quatre rubriques sont **Accueil, Commandes, Ma carte et Mon restaurant**. Les fonctions persistantes, les droits, les erreurs métier, les photos, les horaires, les commandes et leur synchronisation avec le site ont reçu des contrôles exécutés. Les défauts reproduits ont été corrigés puis retestés. Aucun défaut bloquant connu ne reste ouvert dans ce périmètre.

Ce gate porte sur le code livré et son fonctionnement local. Il ne signifie pas qu’un déploiement externe, un paiement commercial, SMTP ou une exploitation sur le domaine réel ont été validés.

## Revue effectuée

Lecture des dix dossiers spécialisés, formulaires/vues/routes CRM, 14 templates, ressources CSS/JS, modèles et services de commande/paiement, modifications de synchronisation React, initialisation/réparation des séquences PostgreSQL, suites QA et proxys Vite/Nginx/Caddy.

Les contrôles d’accès exigent une session active et staff, puis les permissions de lecture/écriture pertinentes. Les mutations sont POST avec CSRF ; les réponses privées sont sans stockage ; la cible de connexion est limitée au domaine. Les champs de formulaires sont explicitement listés et validés côté serveur, avec prix Decimal localisés. Les révisions signées détectent les fiches anciennes. Réglages et horaires sont enregistrés ensemble. Les transitions et historiques réutilisent les règles du modèle ; le CRM ne modifie pas arbitrairement prix historiques ou paiement. Les photos bornées sont décodées, réencodées JPEG et renommées UUID.

La synchronisation React conserve la recherche, la catégorie, les quantités et les choix valides d’une fiche ouverte ; le panier est réconcilié avec la carte actuelle. Une panne de lecture en arrière-plan conserve les données précédentes. Les fragments CRM protègent désormais aussi une interaction commencée pendant la requête.

## Défauts reproduits, corrections et retests

| Défaut | Preuve et correction | Validation après correction |
|---|---|---|
| Réponse de fragment lente retirant le bouton qui venait de recevoir le focus | Reproduction indépendante Chromium : `activeElement` passait de l’action à `BODY`. Le frontend contrôle de nouveau focus et formulaire occupé avant de remplacer le DOM. | Trois cas indépendants réussis : focus acquis pendant fetch, POST déjà verrouillé, actualisation ordinaire. Régression durable : neuf tests Playwright réussis. |
| Service nocturne du lundi bloqué par une fermeture du dimanche | `Restaurant.is_open` gardait toute la branche nocturne par la fermeture de la veille. Le contrôle vise maintenant seulement la continuation du service de la veille. | QA a reproduit l’échec avant correction ; le validateur a rejoué les deux tests horaires corrigés : **2 PASS**, 2,704 s. Les suites finales les incluent. |
| Fermeture exceptionnelle ignorée dans le résumé public d’une semaine uniforme | `hours_summary` retournait les horaires communs avant d’examiner la fermeture du jour. La fermeture exceptionnelle est désormais prioritaire. | Le test public hors démonstration vérifie `isOpen=false`, « Aujourd’hui » et « Fermé exceptionnellement » ; **PASS** dans le même lot indépendant. |
| Collision d’identifiant sur PostgreSQL après `seed_demo` | Première recette PG : 103 réussites et une erreur de création d’un plat, identifiant 1 déjà présent. Le backend avance les séquences Product/Restaurant sous verrou sans retour arrière ; commande distincte sans réensemencement. | Cinq tests dédiés réussis sur PostgreSQL, puis **110/110 tests serveur réussis**. Source du correctif relue indépendamment. |
| Manque de preuve du remplacement réussi d’une photo | Ajout du test `test_replacing_a_photo_persists_new_file_and_updates_public_catalog` : POST CRM, nouveau UUID/JPEG décodable, relecture de fiche/API, nom/prix conservés, ancien fichier non supprimé aveuglément. | Exécution indépendante ciblée : **1 PASS**, 0,946 s. Également inclus dans les suites finales. |
| Indicateur de focus orange peu contrasté | Mesure sur couleurs CSS : environ 2:1 sur les fonds crème. Le coordinateur a changé uniquement l’indicateur de focus vers le violet. | Source finale relue ; contraste calculé violet/crème **12,56:1**, violet/surface **13,22:1**. |

La lecture des frontières publiques a aussi confirmé le durcissement issu de l’audit sécurité : consultation des coordonnées d’une commande par staff conditionnée à `view_order`, propriétaire conservé et suivi invité sans coordonnées. Le droit de lecture staff ne donne pas accès à l’initiation du paiement d’autrui. Les tests serveur positifs et négatifs correspondants sont verts.

## Contrôles exécutés directement par le validateur

| Commande ou contrôle | Résultat réellement observé |
|---|---|
| `git diff --check` | PASS, y compris après les corrections finales. |
| `npx eslint --no-ignore backend/shop/static/shop/crm.js --max-warnings 0` | PASS. Le backend est ignoré par le lint générique ; le contrôle explicite a été effectué. |
| `backend/.venv/bin/python backend/manage.py makemigrations --check --dry-run` | PASS : `No changes detected`, après les corrections du modèle. |
| Tests Django ciblés `CRMTests.test_overnight_closures_only_block_the_service_they_actually_close` et `test_exceptional_closure_overrides_a_uniform_week_in_public_hours_summary` | **2 PASS**, base temporaire détruite. |
| Test Django ciblé `CRMTests.test_replacing_a_photo_persists_new_file_and_updates_public_catalog` | **1 PASS**, base et médias temporaires nettoyés. |
| Chromium, vraie ressource `crm.js`, réseau de fragment retardé | Défaut initial reproduit, puis trois scénarios corrigés réussis ; aucune base sollicitée. |
| Nginx 1.28 Alpine, `nginx -t` | PASS : syntaxe et configuration valides. Image locale, conteneur `--rm --network none`, configurations montées en lecture seule, aucun port publié. |
| Caddy 2, `caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`, domaine `stc.example` | PASS : `Valid configuration`. Mêmes précautions d’isolation. Avertissement de formatage uniquement. |
| HTTP réel après redémarrage local | `/crm` et `/crm/carte/` redirigent vers la connexion autorisée ; `/crm/connexion/` répond 200 avec le vrai HTML CRM et `Cache-Control: no-store` ; `/api/health/` répond 200. Le 404 observé avant redémarrage a disparu. |
| Comparaison SHA-256 avec `/tmp/restobah-pre-crm-manifest.json` | 94 fichiers de référence, **aucun supprimé**. À la clôture : treize fichiers de code/configuration changés pour les intégrations et correctifs annoncés, plus le README documentant le CRM, soit quatorze références modifiées. Les styles/cartes/boutons/menu préexistants restent identiques. |

Les couleurs de texte contrôlées dans le CSS donnent : secondaire/crème 4,89:1 ; secondaire/surface 5,15:1 ; bouton principal 12,83:1 ; statut ouvert 4,62:1 ; erreur 6,31:1 ; texte sombre/orange 7,51:1. Ces couples dépassent 4,5:1. Un audit WCAG exhaustif ou une campagne avec de vrais utilisateurs ne sont pas revendiqués.

## Preuves finales de l’équipe, recoupées

| Lot | Résultat et origine de preuve |
|---|---|
| TypeScript, ESLint et build | `npm run check` réussi, sortie communiquée par le coordinateur ; lint CRM explicite également réussi directement par le validateur. |
| Django / SQLite | Suite finale : **110 collectés, 109 réussis, un ignoré**, 12,896 s. Le test ignoré est spécifique au cache PostgreSQL et a été exécuté dans le lot suivant. |
| Django / PostgreSQL 17.10 | **110 réussis, aucun ignoré**, 20,764 s, code 0. Journal `/tmp/stc-crm-postgres-c818b19e8cff.log` relu par le validateur, rapport `07-database.md` recoupé. Conteneurs, base et fichiers temporaires nettoyés, instances préexistantes conservées. |
| CRM HTTP authentifié | **12/12 Playwright réussis** : neuf parcours fonctionnels et trois parcours visuels, 5,4 min. Instance/base/médias jetables. Statut final `passed`, `failedTests: []` vérifié dans `/tmp/restobah-crm-final-e2e-results/.last-run.json`. |
| Régression publique / API / administration | **97/97 Playwright réussis**, 3,8 min, instance jetable distincte. Statut final recoupé dans `/tmp/restobah-crm-legacy-e2e-results/.last-run.json`. |
| Concurrence visuelle des fragments CRM | **9/9 Playwright réussis** sur mobile/tablette/desktop ; source `tests/crm-refresh.spec.ts` relue. Statut final recoupé dans `/tmp/restobah-crm-refresh-final-results/.last-run.json`. Trois cas ont également été rejoués directement par le validateur. |
| Synchronisation publique avec API simulée | Six scénarios réussis, puis inclus dans le lot de régression ; ils complètent les modifications réelles CRM/site testées séparément. Ne pas les additionner une seconde fois au total de régression. |
| Fichiers statiques | Collecte et manifeste CRM temporaires réussis après la couleur de focus finale, contrôle communiqué par le coordinateur. |
| Accès local réel | Coordinateur : connexion avec les accès locaux privés, quatre rubriques, sélection active, mobile 390 px sans débordement, huit plats, focus violet et aucune erreur JS. Le validateur a confirmé séparément les réponses HTTP et redirections après redémarrage. |

Les trois lots Playwright finaux regroupent **118 tests réussis** (12 + 97 + 9). Les premiers lots intermédiaires ne sont pas ajoutés à ce total.

Commandes exactes des deux lots HTTP finaux, fournies par le coordinateur :

```sh
python3 scripts/e2e.py tests/crm.spec.ts tests/crm-visual.spec.ts --project=desktop --project=tablet --project=mobile --workers=1 --output=/tmp/restobah-crm-final-e2e-results
STC_E2E_API_PORT=8002 STC_E2E_WEB_PORT=5175 python3 scripts/e2e.py --grep-invert 'CRM' --output=/tmp/restobah-crm-legacy-e2e-results
```

`npm run test:backend` a produit le résultat SQLite final de 110 tests ; la sortie est conservée dans l’historique d’exécution du coordinateur, sans journal dédié sur disque. La sortie PostgreSQL finale est, elle, disponible dans le journal cité plus haut. Une comparaison d’empreintes ORM sur huit modèles métier avant/après le contrôle authentifié local a aussi été exécutée par le coordinateur : **données métier inchangées**. Les nouvelles sessions de connexion ne sont pas assimilées à des changements de plats ou de commandes.

Les scénarios fonctionnels couvrent création et modification d’un plat avec photo/prix, prix invalide avec saisie conservée, disponibilité persistée, page client déjà ouverte actualisée ; commande invitée réelle puis préparation/prête/terminée et suivi client, total et historique conservés ; horaire invalide refusé puis horaire enregistré/rechargé et exposé publiquement. Les contrôles serveur complètent les permissions, CSRF, fichiers invalides/lourds/grands, photos réencodées, conflits de versions, horaires multiples/nocturnes, fermetures, pause, annulations et garde de paiement.

Dernière revue de clôture : README, `00-execution.md` et `DELIVERY.md` relus avec leurs commandes, chiffres et limites. Le runner isolé utilise désormais `sys.argv[1:] or ['--workers=1']` : un lancement complet sans argument reste séquentiel, tandis que les arguments des lots explicites déjà exécutés sont transmis sans changement. Cette retouche du runner a été relue ; `python3 -m py_compile scripts/e2e.py` et `git diff --check` ont été relancés directement par le validateur avec succès. Les suites complètes n’ont pas été réexécutées après cette seule valeur par défaut ; aucun code produit supplémentaire n’a changé. **Gate PASS confirmé.**

## Revue visuelle

Les parcours authentifiés ont produit 35 captures, couvrant sept scènes à cinq largeurs : **320, 390, 430, 768 et 1280 px**. Le validateur a ouvert et examiné les quatre rubriques à 320 et 1280 px, la carte à 390/430 px, ainsi que les formulaires/photo/bas de page à 320, 768 et 1280 px.

Constats : palette et structure proches de la maquette, quatre destinations visibles, sélection active cohérente, photos/prix/disponibilité/Modifier lisibles, vrais états vides ou vraies commandes de recette, formulaires courts et bouton d’enregistrement accessible au-dessus de la réserve de navigation mobile. Aucun chevauchement visuel bloquant constaté. Les assertions automatiques de largeur, hit-testing des contrôles, chargement des images et absence d’erreur JavaScript complètent cette lecture.

Exemples : `screenshots/crm-carte-1280.png`, `screenshots/crm-carte-320.png`, `screenshots/crm-commandes-320.png`, `screenshots/crm-plat-bas-320.png`.

## Limites et exploitation

- Les tests PostgreSQL utilisent un vrai moteur jetable ; ils ne constituent pas une épreuve de charge ou une garantie contre toute course possible en exploitation.
- Pour une instance PostgreSQL déjà initialisée avec des identifiants explicites, la mise à jour doit inclure `python manage.py repair_crm_sequences` après sauvegarde. Cette procédure a été testée sur bases jetables ; elle n’a pas été appliquée à une instance existante.
- Les configurations Nginx/Caddy sont validées, sans déploiement ni certificat externe vérifié. Aucun paiement réel, service Stripe externe ou envoi SMTP réel n’a été activé par ces contrôles.
- Les anciennes photos ne sont pas supprimées automatiquement ; sauvegarde et politique de purge des médias restent des tâches d’exploitation documentées.
- Aucun test n’a été annoncé réussi sur la seule présence de code ou d’une maquette. Les premiers échecs horaires, le premier échec PostgreSQL et les corrections/retests sont conservés dans les rapports spécialisés.
