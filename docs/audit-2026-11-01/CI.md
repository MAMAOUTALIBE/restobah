# CI Linux et PostgreSQL — 1er novembre 2026

## Workflow préparé

Le workflow `.github/workflows/ci.yml` conserve un service PostgreSQL 17 jetable et les contrôles TypeScript, ESLint, build, audit Python, cohérence des migrations et suite Django complète. Il ajoute :

- `npm audit --audit-level=moderate`, incluant les dépendances de développement ;
- l'application effective des migrations sur la base PostgreSQL jetable ;
- les tests unitaires des sauvegardes, du paquet de livraison et de la politique des connexions ;
- une recette distincte des commandes réelles avec paiement sur place et démonstration désactivée.

Les permissions GitHub sont limitées à la lecture du dépôt. Le job a une durée maximale de 35 minutes. Aucune variable secrète de production n'est référencée.

## Deux campagnes isolées

| Campagne | Base du service CI | Modes | Commande | Résultats et artefact |
|---|---|---|---|---|
| Régressions complètes | `stc` | `STC_E2E_PAYMENT_MODE=simulation`, `STC_E2E_DEMO_MODE=1` | `python3 scripts/e2e.py --workers=1 --output=test-results/default` | `test-results/default/`, `browser-demonstration-results` |
| Commandes réelles, règlement physique | `stc_onsite` | `STC_E2E_PAYMENT_MODE=on_site`, `STC_E2E_DEMO_MODE=0` | `python3 scripts/e2e.py tests/onsite.spec.ts --workers=1 --output=test-results/onsite` | `test-results/onsite/`, `browser-onsite-results` |

La seconde base est créée explicitement par psycopg en autocommit, avec des identifiants SQL cités et les seuls accès synthétiques du service CI. Elle ne reprend ni les comptes, ni les paramètres, ni les commandes de la première campagne. Le serveur Django hérite bien de l'URL propre à chaque campagne. `scripts/e2e.py` crée un répertoire temporaire distinct pour les comptes de recette, les médias et les e-mails privés, puis le supprime. Il impose des clés Stripe vides dans les deux modes.

Les six parcours serveur sur place sont volontairement ignorés dans la campagne de simulation. La campagne dédiée découvre quinze cas : neuf avec réponses API interceptées et six parcours sur un vrai serveur jetable, répartis sur ordinateur, tablette et mobile. Elle ne se limite donc pas à des doubles réseau.

Les deux dossiers sont envoyés séparément, même après échec, lorsqu'ils existent. Les fichiers de statut cachés de Playwright sont inclus ; la conservation est de sept jours. Le premier contrôle en échec bloque les étapes métier suivantes. Un job interrompu avant la seconde campagne ne constitue pas une preuve de recette sur place.

## Contrôles effectués sur cette modification

```sh
go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 -shellcheck= -pyflakes= .github/workflows/ci.yml
python3 -m unittest discover -s tests -p 'test_operations.py' -v
npx playwright test tests/onsite.spec.ts --list --workers=1 --output=/tmp/stc-ci-onsite-discovery
git diff --check -- .github/workflows/ci.yml docs/audit-2026-11-01/CI.md
```

Résultats : **actionlint PASS**, **16 tests d'outillage PASS en 0,646 s**, **15 cas navigateur découverts**, contrôle des espaces **PASS**. La découverte des cas n'exécute pas les parcours.

Un contrôle structurel supplémentaire, exécuté avec le Python du backend et le parseur YAML Ruby, a vérifié les deux URL de base distinctes, les modes explicites, le travail en série, les sorties/artefacts distincts et les clés Stripe vides du harnais. Le bloc Python de création de base a été parsé et exécuté avec `psycopg.connect` remplacé par un double : exactement un appel en autocommit et une requête `CREATE DATABASE "stc_onsite" OWNER "stc"`. **Aucune connexion à une base n'a été ouverte par ce contrôle.** Actionlint constitue la validation du dialecte GitHub Actions ; le parseur Ruby seul n'en est pas la preuve.

## Preuve externe restante

Ce lot n'a lancé ni nouvelle campagne complète locale, ni test Docker, ni commit, ni push, ni relance GitHub. Le workflow doit encore être exécuté sur le commit final poussé par le coordinateur. Une CI verte ne pourra être annoncée qu'après observation de ce run Linux/PostgreSQL et des deux campagnes effectivement terminées. Les résultats locaux des corrections de cartes, du serveur et du paiement sur place sont consignés séparément dans `UI-CORRECTIONS.md` et `06-qa.md` ; ils ne remplacent pas cette preuve.
