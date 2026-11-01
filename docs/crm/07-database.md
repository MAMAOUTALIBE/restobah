# Audit base de données — CRM STC

Date de contrôle : 1 novembre 2026. Rôle : expert base de données. Périmètre : modèles, migrations, règles métier et lecture de la base locale. Aucun modèle, migration, média ou enregistrement utilisateur n’a été modifié.

## Décision

Le CRM Django à quatre rubriques peut être construit **sans nouvelle table et sans migration de schéma obligatoire**. Les modèles actuels couvrent déjà les plats, photos, catégories, options, horaires multiples, fermetures, commandes, paiements et historique. Réutiliser ces modèles et les fonctions métier ; ne pas créer une seconde source de vérité dans le navigateur.

`makemigrations --check --dry-run` a retourné `No changes detected`. Ce contrôle porte sur l’alignement code/migrations ; il ne remplace pas une recette fonctionnelle du futur CRM.

## État observé

| Domaine | Garantie existante | Conséquence pour le CRM |
| --- | --- | --- |
| Prix | `DecimalField` et validateurs minimum zéro ; prix promotionnel calculé en `Decimal` puis arrondi à deux décimales | Employer un formulaire décimal, accepter une saisie française et refuser les montants négatifs ou trop précis avant sauvegarde. Aucun prix reçu du navigateur ne doit recalculer une commande historique. |
| Plats | Catégorie protégée par clé étrangère ; groupes d’options en relation multiple ; règles promotions/allergènes dans `Product.clean()` | Employer `ModelForm`/validation complète et préserver les champs non présentés par le formulaire simplifié. Ne pas vider les options, promotions ou allergènes lors d’une modification de nom/prix/photo. |
| Disponibilité | `Product.available`, fenêtres de promotion, disponibilité de la source et nombre de choix disponibles contrôlés par `product_data()` et `create_order()` | Distinguer « disponible » saisi par le gérant et « commandable » effectif. Une option obligatoire épuisée peut bloquer un plat pourtant activé. |
| Photos | `ImageField`, fichier séparé sous `MEDIA_ROOT`, URL publique fournie par `product_data()` | La sauvegarde du fichier et celle du SQL ne constituent pas une transaction unique. Ne jamais supprimer l’ancienne photo avant le succès de la modification. Sauvegarder base **et** médias. |
| Horaires | Plusieurs lignes `OpeningHour` par jour ; `Restaurant.is_open()` traite les créneaux passant minuit | Conserver toutes les plages existantes. Une interface d’une seule plage par jour ne doit pas effacer silencieusement la deuxième. |
| Fermetures | Contrainte SQL unique `(restaurant, date)` | Valider les doublons dans le formulaire et gérer aussi une éventuelle collision SQL concurrente. |
| Commandes | Instantanés des noms/options/prix dans `OrderLine`, clé SQL unique d’idempotence, historique séparé | Modifier uniquement le statut autorisé ; ne pas reconstruire les lignes depuis le catalogue actuel. |
| Paiements | Session de paiement protégée ; webhooks idempotents ; garde de paiement avant préparation | Le CRM ne marque jamais manuellement une commande payée et ne contourne pas les transitions existantes. |

Sources locales : `backend/shop/models.py:51`, `:88`, `:101`, `:143`, `:218` ; `backend/shop/services.py:18`, `:35`, `:48`, `:86`, `:117` ; `backend/shop/payments.py:33` ; `backend/shop/admin.py:86` et `:126`.

## Contrôles en lecture seule réellement exécutés

Commande :

```sh
backend/.venv/bin/python backend/manage.py makemigrations --check --dry-run
```

Résultat : `No changes detected`, code de sortie 0.

Une seconde commande Django shell a exécuté uniquement des `SELECT` ORM et des vérifications d’existence de fichiers. Résultats de cet instantané local :

| Contrôle | Résultat |
| --- | --- |
| Restaurants présents | 1 |
| Restaurant canonique `pk=1` présent | Oui |
| Prix de plats négatifs | 0 |
| Prix d’options négatifs | 0 |
| Jours de semaine hors 0–6 | 0 |
| Plages avec ouverture égale à fermeture | 0 |
| Plages identiques dupliquées | 0 |
| Groupes dont le minimum dépasse le maximum | 0 |
| Promotions sans produit source | 0 |
| Références de photos vers des fichiers absents | 0 |

Les coordonnées clients et les secrets n’ont pas été affichés. Ces contrôles n’établissent pas l’absence générale de défaut et ne constituent pas des tests d’écriture du CRM.

## Contrat d’écriture à respecter

1. **Formulaires métier validés.** Un appel ORM `save()`/`update()` ne remplace pas les validations de formulaire. Utiliser une liste explicite de champs, `ModelForm` ou validation équivalente. Conserver les relations et champs techniques absents du formulaire. Les allergènes doivent être convertis en liste de noms, sans exposer un éditeur JSON au patron.
2. **Disponibilité explicite.** Le bouton envoie l’état voulu (`available=true/false`), pas « inverser ». Un double clic ou une répétition réseau ne doit pas annuler la première action. L’écriture ciblée du seul champ évite d’écraser prix et photo. Une fiche d’édition ancienne ne devrait pas écraser une modification concurrente sans avertissement ; une empreinte signée de la version présentée permet une détection sans nouveau champ de modèle si ce cas est pris en charge.
3. **Commandes atomiques.** Recharger la commande avec `select_for_update()` dans `transaction.atomic()`, puis appeler `Order.transition()`. Le statut et son `OrderHistory` doivent être validés ensemble. L’appel direct à `QuerySet.update(status=...)` est exclu. Une action déjà appliquée reste idempotente ; un retour de statut interdit reste refusé.
4. **Annulation d’un paiement en attente.** Passer par `payments.release_checkout()` puis revérifier le statut verrouillé avant transition. Si Stripe est injoignable ou le paiement est passé entre-temps, conserver la commande et afficher l’erreur. Ne pas maintenir un verrou SQL pendant une interaction manuelle avec l’utilisateur.
5. **Restaurant canonique.** Travailler sur `Restaurant(pk=1)` et contrôler les permissions côté serveur. Le singleton est aujourd’hui garanti par le parcours applicatif, pas par une contrainte SQL « une seule ligne ». Ne pas accepter un identifiant de restaurant arbitraire venant du formulaire.
6. **Horaires et fermetures atomiques.** Valider toutes les lignes avant de sauvegarder, verrouiller le restaurant parent et employer un formset limité à ses lignes. Appliquer le lot dans une transaction ; une erreur ne doit pas sauvegarder une moitié du planning. Les suppressions doivent être explicites. Conserver les plages de nuit et les multiples services.
7. **Photos sûres et durables.** Valider contenu réel, poids et dimensions avant enregistrement. Un nom généré évite les collisions et les chemins contrôlés par le navigateur. Sur erreur de formulaire, garder la photo actuelle. Un éventuel nettoyage de fichiers se fait après validation SQL et uniquement sur un fichier non référencé ; ne pas mettre en place de purge destructive automatique dans cette phase.

## Contraintes absentes et priorité

Les contrôles de prix positif, jour valide, ouverture différente de fermeture et bornes d’options sont surtout applicatifs. Un écrit ORM brut peut les contourner. Le CRM peut rester fiable avec tous ses accès d’écriture derrière les formulaires validés et les transactions ci-dessus. Une migration de contraintes SQL supplémentaires serait un durcissement utile séparé, après analyse des données existantes et recette SQLite/PostgreSQL ; elle n’est pas nécessaire à la création des quatre écrans et ne doit pas être introduite sans besoin démontré.

Les horaires n’interdisent pas les doublons ou chevauchements. Ajouter au formulaire/formset une validation des chevauchements, avec bornes adjacentes autorisées. Pour les nuits, comparer des intervalles de semaine normalisés, y compris le passage dimanche/lundi ; ne pas rejeter simplement `fermeture < ouverture`, qui est un cas métier déjà supporté.

La distinction est importante : `select_for_update()` verrouille réellement les lignes sous PostgreSQL ; SQLite local utilise une transaction d’écriture `IMMEDIATE` et un délai de 20 s dans `backend/config/settings.py:28`. Tester les conflits sur l’instance jetable, ne pas annoncer une preuve de concurrence PostgreSQL sur la seule base d’un test SQLite.

## Recette nécessaire après implémentation

- Création d’un plat, lecture via l’API publique, modification partielle et relecture après une nouvelle requête ; les anciennes lignes de commandes gardent leur prix et nom.
- Prix `12,50`, `12.50`, négatif, plus de deux décimales, dépassement du nombre de chiffres ; aucune écriture partielle sur erreur.
- Photo réelle, fausse image, dépassement de taille, modification sans photo, erreur de formulaire avec photo déjà présente ; vérifier SQL et fichier sur média temporaire.
- Disponibilité répétée dans le même état, choix obligatoire indisponible et prix/disponibilité relus par le site et le serveur de commande.
- Planning à deux services, plage de nuit, jour fermé, créneau égal ou chevauchant, fermeture exceptionnelle dupliquée et erreur dans une ligne du lot.
- Statuts autorisés, retour interdit, paiement non confirmé, annulation Stripe simulée en erreur, action répétée, historique et course de deux actions concurrentes.

Exécuter ces écritures dans les bases et dossiers médias temporaires des tests Django et de `scripts/e2e.py`. Aucun test fonctionnel d’écriture de ce rapport n’a été exécuté sur la base locale.

## Préservation et retour arrière

Aucune migration, réinitialisation ni commande de seed n’est proposée. Le retour arrière applicatif du CRM reste donc un retrait des nouvelles routes/templates après sauvegarde, sans réécriture de données. Les enregistrements créés par un gérant doivent rester présents. Les procédures de `scripts/backup.py` et `docs/OPERATIONS.md` sauvegardent la base ; les photos demandent aussi une sauvegarde du répertoire/volume des médias. Une restauration remplaçant la base active est une opération distincte et destructive : elle ne fait pas partie de cet audit.

## Contrôle complémentaire sur PostgreSQL réel

Après gel du backend, Docker a été contrôlé en lecture : daemon 29.4.1 accessible et image `postgres:17-alpine` déjà présente. Un nouveau conteneur temporaire a été créé avec un nom unique, une publication limitée à `127.0.0.1` sur un port éphémère, un mot de passe généré non affiché et un stockage de données temporaire distinct. Aucune instance existante, aucun volume existant et aucun port des recettes navigateur n’ont été utilisés. Médias, e-mails et répertoire runtime des tests sont également temporaires.

Premier passage sur **PostgreSQL 17.10** :

```text
backend/.venv/bin/python backend/manage.py test shop --noinput --verbosity=1
Found 104 test(s).
Ran 104 tests in 167.590s
FAILED (errors=1)
```

Résultat : 103 tests réussis, une erreur et aucun test ignoré. Le contrôle de cache partagé propre à PostgreSQL a donc été exécuté.

Le défaut est concret : `CRMTests.test_create_and_edit_recipe_with_decimal_price_and_real_photo` échoue à la création du plat (`/crm/carte/ajouter/`) avec `duplicate key value violates unique constraint shop_product_pkey`, clé `id=1` déjà présente. Le chargement initial crée les produits avec des identifiants explicites 1–8 et 90, sans avancer la séquence PostgreSQL ; contrairement à SQLite, le premier identifiant automatique reste alors 1. Ce défaut n’est pas une anomalie du formulaire ou du montant décimal.

Le correctif est confié au développeur backend : réalignement **uniquement vers l’avant**, verrouillage des tables concernées et commande de réparation dédiée préservant les données. Le cas `MAX(id) == last_value` avec `is_called=false` doit aussi marquer le numéro comme consommé, sans consommer une séquence de table vide ni reculer une séquence déjà haute après suppression d’un plat.

Preuve d’isolation du premier passage : la base de test a été détruite, le conteneur temporaire a été supprimé en `finally`, et les 36 conteneurs préexistants étaient toujours présents après nettoyage. Code de sortie Django : 1. Journal expurgé : `/tmp/stc-crm-postgres-af56ad9b9a15.log`.

### Correctif et passage final

Le développeur backend a ajouté `backend/shop/sequences.py`, branché son réalignement après les insertions explicites de `seed_demo`, et fourni la commande séparée `repair_crm_sequences`. Cette commande ne charge pas de données de démonstration et ne recrée pas un plat supprimé. Elle verrouille les tables Product/Restaurant avant de comparer leurs identifiants aux séquences PostgreSQL, avance seulement lorsque nécessaire et préserve les valeurs déjà réservées. Les noms de séquence sont obtenus du catalogue PostgreSQL et chaque composant d’identifiant est quoté.

Après gel de ce correctif et ajout du test de remplacement d’une photo, un **nouveau** conteneur PostgreSQL 17.10 a été créé avec le même niveau d’isolation. Deux commandes ont été exécutées, avec `DATABASE_URL` fournie uniquement dans l’environnement privé du processus :

```text
backend/.venv/bin/python backend/manage.py test shop.test_seed_sequences --noinput --verbosity=1
Found 5 test(s).
Ran 5 tests in 1.777s
OK

backend/.venv/bin/python backend/manage.py test shop --noinput --verbosity=1
Found 110 test(s).
Ran 110 tests in 20.764s
OK
```

**Résultat final PostgreSQL : 110 tests réussis, aucun test ignoré, code de sortie 0.** Le passage complet inclut les cinq tests de séquences et les 35 tests CRM, dont création/modification d’un plat avec vraie photo, remplacement d’une photo et lecture de sa nouvelle URL publique. Le contrôle de cache partagé auparavant ignoré sous SQLite est bien couvert sur PostgreSQL.

Les cinq régressions de séquence vérifiées couvrent : création automatique après seed ; seed répété conservant les modifications du gérant ; réparation d’identifiants explicites sans charger les données de démonstration ; absence de recul après suppression d’un identifiant haut et absence de recréation d’un plat supprimé ; table vide dont le premier numéro n’est pas consommé. Le cas Restaurant `id=1`, séquence initialement non appelée, est aussi vérifié.

La base de test a été détruite et le second conteneur temporaire supprimé en `finally`. Les 36 conteneurs préexistants étaient toujours présents après les deux passages. Aucun accès de modification à leurs bases, fichiers ou volumes n’a été effectué. Les médias/e-mails/runtime temporaires ont été nettoyés. Journal final sans secret : `/tmp/stc-crm-postgres-c818b19e8cff.log`.

Pour une **instance PostgreSQL déjà initialisée**, la mise à jour applicative doit prévoir `python manage.py repair_crm_sequences` après sauvegarde et avant utilisation du nouveau CRM. Cela répare les compteurs sans réensemencement ni réécriture des plats. Cette opération n’a pas été exécutée sur une instance existante pendant la recette ; la validation a utilisé uniquement les bases jetables.
