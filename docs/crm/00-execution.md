# CRM STC — exécution et preuves

Demande du 1er novembre 2026. Préserver le site et les modifications existantes. Environnement : quatre agents actifs simultanément, coordination en plusieurs vagues.

## Décision et critères

- Ajouter un espace gérant Django `/crm/`, avec templates, formulaires validés et JavaScript progressif, en réutilisant modèles, sessions et règles métier.
- Quatre rubriques : Accueil, Commandes, Ma carte et Mon restaurant.
- Palette crème/violet/orange, boutons explicites, champs courts et navigation mobile lisible.
- Vérifier : création/modification des plats, photo, prix, disponibilité, commandes et historique, horaires/plages/fermetures, synchronisation avec un site déjà ouvert.
- Contrôler les saisies invalides, sessions/permissions/CSRF, photos, persistance et rendu mobile ; corriger puis relancer les contrôles concernés.
- Conserver les plats épuisés consultables et indisponibles à la commande, conformément au comportement existant. Ne pas promettre leur masquage.
- Exécuter les écritures de recette sur une instance isolée ; ne pas altérer la base et les accès locaux.

## Équipe spécialisée

| Rôle | Agent | Livrable |
|---|---|---|
| Chef de projet | crm_project_manager | 01-project-plan.md |
| Architecte | crm_architect | 02-architecture.md |
| UX | crm_ux | 03-ux.md |
| UI | crm_ui_designer | 04-ui.md |
| Frontend | crm_frontend | 05-frontend.md, templates, styles, JavaScript et tests de rafraîchissement |
| Backend | crm_backend | 06-backend.md, formulaires, vues, droits et réparation des séquences |
| Base de données | crm_database | 07-database.md |
| Sécurité | crm_security | 08-security.md et corrections contrôlées par QA |
| QA | crm_qa | 09-qa.md, tests serveur et parcours isolés |
| Validation indépendante | crm_validation | 10-validation.md, revue et gate final PASS |

## État initial

Administration générique existante à `/admin/`. Aucun CRM dédié. Modèles persistants et transitions de commande existants. Catalogue React chargé au montage seulement ; paramètres restaurant actualisés toutes les 60 secondes. Rapport détaillé dans les livrables des agents.

Une archive du code et une empreinte des sources ont été créées avant les changements CRM dans `/tmp/restobah-pre-crm-20261101.zip` et `/tmp/restobah-pre-crm-manifest.json`. Elles ne contiennent aucune base ni accès privé.

## Validation

**Gate indépendant final : PASS.** Les dix rôles ont produit un livrable vérifiable. Les premiers échecs puis les corrections et relances sont conservés dans les rapports.

- PostgreSQL 17.10 : 110 tests réussis, aucun ignoré ; instances jetables nettoyées, instances existantes préservées.
- SQLite : 109 tests réussis et un test spécifique PostgreSQL ignoré, sur 110 collectés.
- Playwright : 118 tests réussis dans trois lots isolés (12 CRM fonctionnels/visuels, 97 de régression, 9 de concurrence du rafraîchissement).
- TypeScript, ESLint, build, collecte/manifeste des fichiers statiques, contrôle Django, absence de nouvelle migration, et syntaxe des proxys Nginx/Caddy : réussis.
- Recette visuelle authentifiée : 35 captures à 320, 390, 430, 768 et 1280 px ; revue indépendante effectuée.
- Accès local réel après redémarrage géré : connexion, quatre rubriques, mobile, focus et absence d’erreur JavaScript vérifiés. Empreintes des huit ensembles métier inchangées avant/après cette recette en lecture seule.
- Travail antérieur : 94 fichiers de référence, aucun supprimé ; changements attendus limités à l’intégration, la synchronisation et les correctifs métier/sécurité. Les styles précédemment travaillés sont conservés.

Le détail des commandes, des corrections et des limites est dans [DELIVERY.md](DELIVERY.md) et [10-validation.md](10-validation.md). La mise en production, le paiement réel et la configuration SMTP ne sont pas assimilés à une validation locale.

## Sources primaires consultées

- [Django — authentification et permissions](https://docs.djangoproject.com/en/5.2/topics/auth/default/)
- [Django — sécurité](https://docs.djangoproject.com/en/5.2/topics/security/)
- [OWASP — sécuriser les fichiers envoyés](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [Square — disponibilité des articles](https://squareup.com/help/us/en/article/8495-beta-item-availability)

Pistes retenues : disponibilité en une action, droits distincts par opération, validation côté serveur et contrôle réel des photos.
