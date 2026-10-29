# STC — commande de restaurant

Application React/TypeScript et API Django REST Framework. Le catalogue, les comptes, les adresses, les favoris et les commandes sont persistants. Le montant et les options sont validés au serveur. L’interface reste fidèle à la référence STC, avec navigation mobile de 44 px et footer compact.

## Démarrage local

Prérequis : Node.js 22+, Python 3.13 ou 3.14 et `npm`.

```sh
python3 scripts/setup.py
npm run dev:all
```

- Site : http://localhost:5173
- Administration : http://localhost:5173/admin/
- Santé API : http://localhost:5173/api/health/

Le script crée un `.env` privé, installe les dépendances, applique les migrations et ajoute les données initiales sans écraser les modifications existantes. Le compte administrateur local et son mot de passe aléatoire sont dans `.runtime/admin-credentials.txt` : ce fichier n’est pas versionné et les accès ne sont pas publiés dans les logs.

Pour lancer les services séparément :

```sh
backend/.venv/bin/python backend/manage.py runserver 127.0.0.1:8000 --noreload
npm run dev
```

Ces deux commandes s’exécutent dans deux terminaux à la racine du projet. `npm run dev:all` refuse de démarrer si un des ports est déjà occupé.

## Fonctionnalités

- Catalogue, catégories et options administrables, recherche (sans accents), filtres, tri et allergènes ; un plat dont une option obligatoire est épuisée est indisponible.
- Panier local avec validation et actualisation des choix disponibles.
- Retrait ou livraison, frais, délais affichés et zone postale configurables (zone obligatoire pour livrer).
- Commande invitée ou avec compte, total calculé en base avec des décimaux et clé anti-doublon ; refus du serveur affichés tels quels.
- E-mail de confirmation au client (lien de suivi personnel) et alerte de l’équipe (`STC_ORDER_NOTIFICATION_EMAIL`).
- Comptes clients, connexion/déconnexion, réinitialisation du mot de passe, adresses et favoris synchronisés, suppression du compte en libre-service.
- Historique protégé et suivi des statuts réels ; les commandes invitées de l’appareil restent visibles après connexion.
- Administration Django : produits/photos/options, horaires, fermetures, promotions, commandes et statuts.
- Stripe Checkout en **mode test uniquement** : signatures vérifiées, webhooks idempotents, sessions de 31 à 41 min, annulation administrative qui ferme la session, paiement tardif signalé « à rembourser », `cancel_stale_orders` pour les commandes impayées.

Par défaut, `STC_DEMO_MODE=1` et `STC_PAYMENT_MODE=simulation` : les commandes sont réellement enregistrées dans la base locale, mais aucun restaurant ni paiement réel n’est déclenché. Les données du restaurant et les photos sont illustratives. Les retours de Stripe ne marquent jamais une commande comme payée ; seul un webhook vérifié le permet.

## Vérifications

```sh
npm run check
npm run test:backend
# Installer une fois le navigateur de test :
npx playwright install chromium
# Instance jetable (ports 8001/5174), base locale non modifiée :
npm run test:e2e:isolated
```

`npm run check` exécute TypeScript, ESLint et la compilation de production. Les tests Django vérifient les règles métier et la sécurité, dont des webhooks Stripe signés. Playwright teste l’API et les parcours sur ordinateur et mobile.

`npm run test:e2e:isolated` crée une base SQLite, un dossier d’accès administrateur et un dossier d’e-mails temporaires, puis les supprime : la base locale et `.runtime/admin-credentials.txt` ne sont pas touchés. `npm run test:e2e` cible les serveurs déjà lancés (ou `E2E_BASE_URL`) et ajoute des données de recette à leur base. Une configuration CI PostgreSQL est fournie dans `.github/workflows/ci.yml` ; elle n’a pas été publiée automatiquement.

## Variante Docker avec PostgreSQL

```sh
# Créer .env via le setup ci-dessus au préalable.
docker compose build
docker compose run --rm backend python manage.py migrate --noinput
docker compose run --rm backend python manage.py seed_demo
docker compose up -d
```

Les fichiers statiques de Django sont intégrés à l’image lors de sa construction.

Site de revue : http://127.0.0.1:8080 (adresse distincte pour séparer les cookies de la version de développement). Cette instance possède sa propre base PostgreSQL, distincte de SQLite. Créer un administrateur dans cette instance avec `docker compose exec backend python manage.py createsuperuser`.

## Configuration et exploitation

- `.env.example` : configuration locale ; `.env.production.example` : paramètres à renseigner pour le déploiement.
- [Exploitation et déploiement](docs/OPERATIONS.md).
- [Contrat de l’API](API_CONTRACT.md).
- [Validation et état de livraison](docs/DELIVERY.md).
- `screenshots/` : captures de contrôle de l’interface.

La mise en ligne demande encore un domaine/hébergement, des coordonnées et allergènes réels, un service SMTP et les paramètres Stripe. Cette livraison bloque volontairement les clés Stripe réelles : une ouverture aux paiements réels nécessite une validation distincte et une évolution de la configuration.

## Organisation

`src/components/` : interface ; `src/services/api.ts` : client HTTP ; `src/store/` : session et panier ; `src/types.ts` : contrats ; `backend/shop/` : modèles, API et règles métier ; `backend/config/` : Django ; `deploy/` : conteneurs/proxy ; `scripts/` : installation, lancement et sauvegarde.

Les photos STC sont servies depuis `public/images/`. Les polices sont hébergées localement dans `public/fonts/`, avec leurs licences. Les informations de démonstration sont configurables dans l’administration ; le script `seed_demo` est idempotent et ne remplace pas les changements de l’exploitant.

## Démonstration en ligne

https://stc.srv2086522.hstgr.cloud (mode démonstration, paiement simulé). L’adresse `https://stc.sonutech.tech` sera active après création de son enregistrement DNS : voir [OPERATIONS.md](docs/OPERATIONS.md#démonstration-publique-déployée-25-octobre-2026).

## Livraison vérifiée (25 octobre 2026, après audit)

70 tests Django réussis sur PostgreSQL 17 (69 sur SQLite, le test du cache partagé étant propre à PostgreSQL) ; 41 tests Playwright réussis sur instance isolée et sur la pile Docker (Nginx, gunicorn, PostgreSQL). Opérationnel en local et en recette Docker, en mode démonstration ; la production n’est pas publiée et le paiement réel reste bloqué. Défauts corrigés, preuves, limites et étapes de mise en production : [rapport de livraison](docs/DELIVERY.md). L’archive est produite avec `python3 scripts/package.py`.

Une instance déjà lancée avant cette mise à jour doit être sauvegardée, migrée (migrations 0004 et 0005, avant le redémarrage) et redémarrée : voir [OPERATIONS.md](docs/OPERATIONS.md#mise-à-jour-dune-instance-existante).
