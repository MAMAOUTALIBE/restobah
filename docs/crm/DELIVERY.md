# Livraison du CRM STC — 1er novembre 2026

## Résultat et accès

**CRM local opérationnel et gate indépendant PASS.** Adresse : http://localhost:5173/crm/. Les services locaux ont été redémarrés proprement, puis la connexion et les quatre rubriques ont été vérifiées sur cette adresse. Aucun réensemencement ni réinitialisation de la base locale n’a été effectué.

L’espace gérant utilise les modèles, sessions et règles du restaurant existant. La gestion technique `/admin/` reste disponible pour les opérations avancées. Les accès locaux restent dans `.runtime/admin-credentials.txt`, fichier privé non versionné ; ils ne sont pas reproduits dans ce rapport.

## Fonctionnalités contrôlées

| Rubrique | Fonctionnement livré |
|---|---|
| Accueil | Indicateurs calculés en base, commandes récentes, état réel de prise des commandes et raccourcis utiles. Actualisation automatique des blocs de lecture. |
| Commandes | Recherche et filtres, contenu et coordonnées autorisées, paiement, historique et transitions Préparer → Marquer prête → Terminer. Contrôle du statut attendu, protection des annulations et des commandes impayées. |
| Ma carte | Recherche/catégorie, création et modification des plats, prix décimaux français, disponibilité explicite, photo, allergènes et groupes d’options existants dans les détails. Saisies invalides et changements concurrents refusés avec explication. |
| Mon restaurant | Coordonnées, pause des commandes, retrait/livraison, délais, frais et zones ; plusieurs services par jour, services passant minuit et fermetures exceptionnelles. Enregistrement atomique des réglages et du planning. |

L’interface reprend le crème, le violet et l’orange de la maquette. Les quatre rubriques restent visibles sur mobile, avec boutons explicites et champs lisibles. Les confirmations d’enregistrement proviennent de la réponse serveur.

Le site client déjà ouvert reçoit le catalogue, les photos, les prix et la disponibilité en arrière-plan toutes les 15 secondes et au retour sur l’onglet. Recherche, catégorie et choix valides d’une fiche ouverte sont conservés ; le panier est réconcilié. Un plat épuisé demeure consultable, avec ajout désactivé, conformément au comportement antérieur.

## Équipe et livrables

Dix agents spécialisés ont été constitués, en plusieurs vagues, avec quatre agents actifs au maximum, coordinateur inclus.

| Rôle | Agent et preuve |
|---|---|
| Chef de projet | `crm_project_manager` — [plan et critères](01-project-plan.md) |
| Architecte logiciel | `crm_architect` — [structure et contrats](02-architecture.md) |
| Expert UX | `crm_ux` — [parcours et erreurs](03-ux.md) |
| Designer UI | `crm_ui_designer` — [cahier de conception](04-ui.md) |
| Développeur frontend | `crm_frontend` — [interface et rafraîchissement](05-frontend.md) |
| Développeur backend | `crm_backend` — [formulaires et règles](06-backend.md) |
| Expert base de données | `crm_database` — [intégrité et vrais tests PostgreSQL](07-database.md) |
| Expert sécurité | `crm_security` — [frontières et contrôles](08-security.md) |
| Expert tests et QA | `crm_qa` — [tests et premiers échecs documentés](09-qa.md) |
| Responsable validation | `crm_validation` — [revue indépendante et gate final](10-validation.md) |

## Corrections réalisées et retestées

1. **Droits sur les commandes** : un simple compte d’équipe ne peut plus lire toutes les commandes via l’API. La lecture staff exige la permission dédiée ; elle ne donne pas un droit d’initier un paiement pour autrui. Propriétaire et suivi invité conservent leurs accès prévus.
2. **Écritures CRM** : sessions actives, permissions par opération, POST et CSRF ; limitation des connexions gérant, cibles de redirection contrôlées et réponses privées non mises en cache.
3. **Photos** : vrai contenu JPEG/PNG/WebP vérifié, limites de poids/dimensions, réencodage JPEG et nom aléatoire. Création et remplacement ont été contrôlés, ainsi que le refus des fichiers invalides et la conservation de l’ancienne photo en cas d’erreur.
4. **Concurrence** : révisions signées contre l’écrasement de fiches et de réglages devenus anciens ; état souhaité explicite pour une disponibilité ; commande verrouillée et transition historisée.
5. **Rafraîchissement** : une réponse lente ne remplace plus une action ayant acquis le focus pendant la requête ni un POST en cours. Les derniers contenus restent affichés si une mise à jour échoue.
6. **Horaires** : une fermeture la veille ne bloque plus le nouveau service nocturne du jour. Une fermeture exceptionnelle du jour apparaît aussi dans le résumé public, même avec des horaires identiques toute la semaine.
7. **PostgreSQL** : l’initialisation à identifiants explicites pouvait provoquer une collision lors du premier ajout de plat. Les séquences sont maintenant réalignées sans recul ; une commande de réparation dédiée traite une installation existante sans réensemencer la carte.
8. **Intégration** : `/crm/` est routé par Vite, Nginx et Caddy ; les photos de recette utilisent un répertoire jetable ; la recette complète utilise un worker par défaut afin de préserver les scénarios partageant les réglages du restaurant.

Les régressions horaires et la collision PostgreSQL ont d’abord été observées en échec, puis corrigées et rejouées. Les rapports spécialisés conservent ces étapes.

## Tests réellement exécutés

| Contrôle | Résultat final |
|---|---|
| Django / PostgreSQL 17.10 réel et jetable | **110 réussis, aucun ignoré**, 20,764 s. Les cinq tests ciblés de séquences réussissent aussi. |
| Django / SQLite | **109 réussis, un ignoré spécifique PostgreSQL**, 110 collectés, 12,896 s. |
| CRM navigateur authentifié | **12 réussis**, 5,4 min : neuf parcours métier et trois parcours visuels sur ordinateur, tablette et mobile. |
| Régression site public, API et administration | **97 réussis**, 3,8 min, instance jetable distincte. |
| Rafraîchissement concurrent CRM | **9 réussis**, trois cas sur trois formats ; trois cas également rejoués indépendamment par le validateur. |
| Qualité et intégration | TypeScript, ESLint, build, lint explicite du JavaScript CRM, `manage.py check`, migrations à blanc, collecte/manifeste des fichiers statiques et diff-check réussis. |
| Proxys | `nginx -t` et `caddy validate` réussis dans des conteneurs sans réseau et sans port publié, avec configurations montées en lecture seule. |
| Adresse locale réelle | Connexion et quatre rubriques contrôlées après redémarrage, mobile 390 px, huit plats, focus violet visible, aucune erreur JavaScript. |

Les trois lots Playwright finaux représentent **118 tests réussis**, sans additionner à nouveau les exécutions intermédiaires ou les tests de synchronisation déjà inclus dans la régression.

Commandes principales de reproduction :

```sh
npm run check
npm run test:backend
python3 scripts/e2e.py tests/crm.spec.ts tests/crm-visual.spec.ts --project=desktop --project=tablet --project=mobile --workers=1 --output=/tmp/restobah-crm-final-e2e-results
STC_E2E_API_PORT=8002 STC_E2E_WEB_PORT=5175 python3 scripts/e2e.py --grep-invert 'CRM' --output=/tmp/restobah-crm-legacy-e2e-results
npx playwright test tests/crm-refresh.spec.ts --project=desktop --project=tablet --project=mobile --output=/tmp/restobah-crm-refresh-final-results
```

Les tests qui écrivent des plats, horaires et commandes utilisent exclusivement les bases et fichiers temporaires de la recette. Leurs accès sont générés pour cette instance et ne sont pas imprimés. Les tests de rafraîchissement utilisent un réseau contrôlé, sans écriture métier.

Le journal PostgreSQL final est `/tmp/stc-crm-postgres-c818b19e8cff.log`. Les sorties des autres commandes figurent dans l’historique d’exécution et les rapports spécialisés ; les artefacts Playwright contiennent un statut final réussi sans test en échec.

## Revue visuelle et préservation

Trente-cinq captures authentifiées couvrent les quatre rubriques et la fiche plat à **320, 390, 430, 768 et 1280 px**. Elles vérifient les images, les prix, les boutons, les champs, l’état actif et l’accès au bouton d’enregistrement sur mobile. La revue indépendante et les contrôles de géométrie/hit-testing n’ont relevé aucun chevauchement bloquant.

- [Ma carte — ordinateur](../../screenshots/crm-carte-1280.png)
- [Ma carte — mobile](../../screenshots/crm-carte-390.png)
- [Commandes — mobile](../../screenshots/crm-commandes-390.png)
- [Mon restaurant — mobile](../../screenshots/crm-restaurant-320.png)

Les sources ont été sauvegardées avant intervention : 94 fichiers de référence, aucun supprimé. Les modifications de fichiers existants concernent les intégrations, les correctifs annoncés et leur documentation ; les nouveaux fichiers CRM et tests s’y ajoutent. Les styles et composants précédemment travaillés ont été conservés.

Une comparaison d’empreintes ORM avant/après la recette authentifiée locale a confirmé que **huit ensembles métier étaient inchangés** : restaurant, plats, catégories, horaires, fermetures, commandes, lignes et historique. Les sessions de connexion sont distinctes de ces données métier. Les deux conteneurs PostgreSQL de test ont été supprimés ; les 36 conteneurs préexistants ont été conservés.

## Limites et mise en service

**Aucun blocage local connu au terme des contrôles.**

- L’instance est en mode démonstration ; les commandes de recette sont réellement persistées, avec paiement simulé. La production n’a pas été publiée et aucun paiement ou envoi SMTP réel n’a été activé.
- Pour une base PostgreSQL déjà initialisée avec les anciens identifiants, appliquer la commande `repair_crm_sequences` lors de la mise à jour, après sauvegarde. Cette réparation a été testée sur bases jetables et n’a pas été appliquée aux instances existantes. [Procédure](../OPERATIONS.md).
- Les configurations des proxys ont été validées, pas un déploiement public ni un certificat TLS. Les tests ne constituent pas une épreuve de charge.
- Les anciennes photos sont conservées ; leur sauvegarde et leur éventuelle purge relèvent de l’exploitation.

Les repères techniques consultés sont consignés dans [le journal d’exécution](00-execution.md#sources-primaires-consultées), notamment la documentation Django, les recommandations OWASP pour les photos et les règles UX de notification et de validation. La validation finale repose sur les contrôles exécutés ci-dessus.
