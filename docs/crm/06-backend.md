# CRM STC — implémentation backend

Rôle 6/10 : développeur backend. Livraison du 1er novembre 2026, à valider indépendamment par QA et le responsable de validation.

## Implémentation

L’espace `/crm/` utilise les sessions, modèles et règles métier Django existants. Aucune base distincte, nouvelle table, migration ou donnée locale n’a été créée par ce lot.

Fichiers créés :

- `backend/shop/crm_forms.py` : formulaires courts, validation, photos, révisions et horaires.
- `backend/shop/crm_views.py` : lectures, permissions, statistiques, fragments et mutations transactionnelles.
- `backend/shop/crm_urls.py` : routes nommées sous le namespace `crm`.
- `backend/shop/sequences.py` : verrouillage et avance sûre des compteurs PostgreSQL des identifiants explicites de démonstration.
- `backend/shop/management/commands/repair_crm_sequences.py` : réparation seule, sans réinitialiser ni charger la carte.
- `backend/shop/test_seed_sequences.py` : cinq tests de non-régression dédiés aux compteurs et à la préservation des données.

Fichiers modifiés :

- `backend/config/urls.py` : inclusion de `/crm/`.
- `backend/shop/middleware.py` : limitation partagée des connexions CRM, en plus de l’administration existante ; page française et `Retry-After` en cas de limitation CRM.
- `backend/shop/models.py` (`Restaurant.is_open`) : correction du lien entre fermeture exceptionnelle et service nocturne, sans changement de schéma.
- `backend/shop/services.py` (`hours_summary`) : une fermeture du jour prend priorité sur le résumé des horaires hebdomadaires uniformes. Le durcissement distinct des droits de lecture des commandes est conservé.
- `backend/shop/management/commands/seed_demo.py` : verrou des tables avant l’initialisation puis avance des compteurs, sans écraser les recettes ou réglages existants.
- `docs/OPERATIONS.md` : procédure de réparation d’une base existante sans recharger les exemples.

Les templates, styles et JavaScript sont la responsabilité du frontend. Les proxys, l’isolation des médias et la synchronisation React sont intégrés séparément par le coordinateur.

## Routes et contrats

| Nom | URL | Méthodes et opération |
|---|---|---|
| `crm:login` | `/crm/connexion/` | GET/POST : connexion gérant par e-mail |
| `crm:logout` | `/crm/deconnexion/` | POST : déconnexion de sa propre session |
| `crm:dashboard` | `/crm/` | GET : accueil et raccourcis autorisés |
| `crm:dashboard_fragment` | `/crm/accueil-fragment/` | GET : indicateurs et commandes récents |
| `crm:orders` | `/crm/commandes/` | GET : liste, recherche, filtre et pagination |
| `crm:orders_fragment` | `/crm/commandes/fragment/` | GET : actualisation protégée de cette liste |
| `crm:order_status` | `/crm/commandes/<id>/statut/` | POST : transition métier |
| `crm:menu` | `/crm/carte/` | GET : plats réguliers, prix et disponibilités |
| `crm:product_add` | `/crm/carte/ajouter/` | GET/POST : création |
| `crm:product_edit` | `/crm/carte/<id>/modifier/` | GET/POST : modification |
| `crm:product_availability` | `/crm/carte/<id>/disponibilite/` | POST : disponibilité explicite |
| `crm:restaurant` | `/crm/restaurant/` | GET/POST : réglages et horaires atomiques |
| `crm:closure_add` | `/crm/restaurant/fermetures/ajouter/` | POST : fermeture exceptionnelle |
| `crm:closure_delete` | `/crm/restaurant/fermetures/<id>/supprimer/` | POST : retrait d’une fermeture |

Réussite d’écriture : redirection HTTP 302 et message réel. Formulaire invalide : HTML 200 avec saisie et erreurs. Disponibilité/statut syntaxiquement invalide : HTTP 400. Révision de disponibilité périmée ou transition refusée/périmée : HTML 409 avec données actuelles. Les lectures privées et fragments portent `Cache-Control: no-store`. Les fragments portent aussi `X-STC-Fragment: dashboard` ou `orders`, ce qui permet au client de distinguer un fragment valide d’une page de connexion.

## Permissions et authentification

- Le gérant doit être authentifié, actif et `is_staff`, avec au moins une permission métier pour entrer dans le CRM.
- Les lectures utilisent `view_product`, `view_order`, `view_restaurant`. Les ajouts et changements exigent aussi `add_product`, `change_product`, `change_order` ou `change_restaurant` selon l’opération.
- Les réglages, horaires et fermetures constituent un même agrégat métier : `view_restaurant` + `change_restaurant` autorisent leur écriture. Il n’existe aucune modification de comptes ou de permissions dans ces formulaires.
- Un lecteur ne peut pas écrire, même en fabriquant une requête. Un client connecté ou un staff sans droit métier reçoit un refus d’accès.
- L’accueil ne calcule ni indicateur ni coordonnées de commande sans `view_order` ; son fragment de commandes exige cette permission.
- La déconnexion nécessite une session authentifiée et un POST protégé CSRF, mais aucun droit métier, afin de rester possible si les droits du compte sont retirés.
- Connexion : e-mail normalisé en minuscules, mot de passe non réaffiché, refus générique, retour `next` limité au même hôte. Le compteur de tentatives existant couvre également `/crm/connexion/`.
- Les formulaires ne désactivent jamais la protection CSRF. Les templates conservent l’échappement HTML. Aucun secret ou accès local n’est exposé.

## Saisie et intégrité

### Plats

Champs : nom, catégorie existante, prix, description, photo et disponibilité ; détails facultatifs : résumé, badge, végétarien, allergènes textuels et choix existants. Les promotions et champs techniques ne sont pas acceptés depuis le formulaire. Les prix sont des `Decimal`, avec virgule ou point acceptés, bornes et deux décimales vérifiées côté serveur.

La photo est bornée à 5 Mio avant validation, doit réellement être une image JPEG/PNG/WebP fixe, avec au plus 6 000 pixels de côté et 20 millions de pixels. Elle est décodée puis réencodée en JPEG, sans nom original ni métadonnées ou contenu ajouté, sous un nom UUID. Les images transparentes sont aplaties sur fond blanc. Aucune URL distante n’est téléchargée. Sans nouvelle photo, celle déjà enregistrée est conservée.

L’édition et la disponibilité utilisent une révision signée du produit, valide au plus douze heures. Une fiche périmée ne peut pas écraser un prix, une photo, une disponibilité ou des options modifiés entre-temps. L’état de disponibilité envoyé est une valeur explicite `1` ou `0`, jamais une inversion aveugle.

La disponibilité effective reprend `services.product_data()` : un choix obligatoire épuisé empêche toujours la commande. Les plats épuisés restent consultables sur le site, conformément au comportement antérieur.

### Commandes

Recherche bornée, filtres métier et pagination par 30. Lignes et historique sont préchargés. Le CRM ne propose que l’action suivante permise et une annulation secondaire lorsqu’elle est autorisée. Les totaux, lignes et statuts de paiement ne sont jamais éditables.

Chaque transition contrôle `expected_status` sous transaction et verrou de ligne, puis utilise `Order.check_transition()` et `Order.transition()`. L’historique reste la source réelle. Une commande payée ne peut pas être annulée avant le traitement prévu par les règles existantes. Une annulation de paiement Stripe en attente passe par `release_checkout()` avant la transition ; un échec ne produit pas une fausse annulation.

### Restaurant et horaires

Les réglages et le formset `hours` sont validés ensemble avant toute sauvegarde. La révision du restaurant comprend les périodes existantes : une autre mise à jour ne peut pas être écrasée silencieusement. Les identifiants et le nombre initial des périodes sont contrôlés contre la base.

Plusieurs services par jour et les services qui passent minuit sont conservés. Les chevauchements sont détectés sur une semaine circulaire, y compris dimanche/lundi, avec la précision réelle des heures (secondes et microsecondes). Les périodes ordinaires restent présentées en heures/minutes ; une précision existante est préservée dans le champ. Les suppressions nécessitent une case explicite, sans effacement de toutes les périodes avant validation.

Les fermetures exceptionnelles doivent porter une date présente ou future et restent uniques pour ce restaurant. Leur ajout et leur suppression n’effacent pas le planning habituel. Les codes postaux sont des chaînes de cinq chiffres ; une livraison activée exige une zone renseignée.

Une fermeture bloque toute la date concernée ainsi que la continuation, après minuit, du service qui aurait commencé ce jour-là. Elle ne bloque pas le nouveau service du lendemain. Le résumé public affiche « Fermé exceptionnellement » le jour de fermeture, même si les sept jours ont habituellement les mêmes horaires.

### Identifiants PostgreSQL après initialisation

La recette sur PostgreSQL 17 a révélé une collision à la création d’un plat : les identifiants explicites chargés par `seed_demo` n’avançaient pas les séquences. Le correctif verrouille les tables `Product` et `Restaurant` avant l’initialisation, puis avance les compteurs jusqu’au maximum existant uniquement si nécessaire. Un compteur déjà plus haut n’est jamais abaissé. Si l’identifiant existant vaut exactement `last_value` avec `is_called=false`, il est marqué consommé ; une table vide conserve son compteur intact.

Le helper partagé protège les insertions ordinaires concurrentes avec une transaction et un verrou `SHARE ROW EXCLUSIVE`. Les objets à clé textuelle ne sont pas concernés. SQLite met déjà à jour ses compteurs lors d’identifiants explicites. Les opérations manuelles hors application qui appellent directement `nextval` ne font pas partie du protocole de verrouillage de tables ; la procédure est une opération de maintenance avec l’utilisateur de base de l’application.

Pour une base déjà initialisée, exécuter `python manage.py repair_crm_sequences` depuis le backend, avec les mêmes paramètres d’environnement que l’instance. Cette commande ne relance pas le seed et ne recrée pas les plats supprimés. Aucune donnée métier ni migration n’est nécessaire. Voir la procédure Docker dans [OPERATIONS.md](../OPERATIONS.md#réparer-les-compteurs-didentifiants-postgresql).

## Contexte partagé avec le frontend

- Base : `section`, `restaurant`, `operator_name`, `demo_mode`, `ordering_enabled`, `is_open`, `permissions`, `crm_updated_at`.
- Produits : attributs `crm_image_url`, `crm_effective_available`, `crm_revision` ; `q`, `category_filter`, `categories`.
- Formulaire : `form`, `product`, `photo_url`, `is_new`. `revision` est un champ caché.
- Commandes : `orders`, `page_obj`, `status_filter`, `q` ; attributs `crm_next_status`, `crm_next_label`, `crm_can_cancel`. POST : `status`, `expected_status`, `return_filter` facultatif.
- Accueil : `stats` (`confirmed`, `preparing`, `ready`, `today_count`, `today_total`, `unavailable_products`) et `recent_orders`. Les métriques interdites restent absentes du rendu autorisé.
- Restaurant : `form`, `opening_formset` de préfixe `hours`, `closure_form`, `closures`. Inclure le management form, les identifiants cachés et la révision.

## Contrôles et handoff

`backend/.venv/bin/python backend/manage.py check` a été exécuté avec succès après implémentation et après les derniers ajustements. L’agent QA a exécuté un premier lot de 25 tests CRM avec succès, puis complète les frontières et les parcours isolés ; sa validation finale fait autorité dans le rapport QA.

Après les deux corrections d’horaires issues de la validation indépendante, leurs tests de régression ont d’abord échoué sur le code précédent, puis passé sur le correctif. La commande `backend/.venv/bin/python backend/manage.py test shop --noinput` a ensuite exécuté 104 tests en 11,880 s : 103 réussites et une exclusion propre à PostgreSQL. Cette exécution utilise la base de test Django et ne remplace pas la reprise des parcours HTTP sur une instance fraîche par QA.

Après le correctif des séquences, `backend/.venv/bin/python backend/manage.py test shop.test_seed_sequences --noinput` a exécuté les cinq nouveaux tests SQLite avec succès : création automatique après seed, préservation des personnalisations au second seed, réparation seule d’identifiants explicites, non-retour en arrière après suppression d’un identifiant élevé, et table vide sans réservation d’identifiant. `manage.py check` et `git diff --check` réussissent. La recette PostgreSQL indépendante doit confirmer ces cas et la suite complète sur la version finale ; une réussite SQLite ne démontre pas l’exécution du SQL PostgreSQL.

Validation encore requise au handoff : suite Django CRM et régression complète, Playwright sur instance et médias isolés, revue sécurité et validation indépendante, rendu mobile/desktop, synchronisation d’un onglet client déjà ouvert, erreurs et coupures réseau. Aucune mise en production, migration, création de données utilisateur ni activation de paiement réel n’a été effectuée par ce lot.

Les anciennes photos ne sont pas automatiquement supprimées lors d’un remplacement : elles ne sont pas effacées sans vérification de leurs autres usages. La politique de sauvegarde/purge des médias relève de l’exploitation.
