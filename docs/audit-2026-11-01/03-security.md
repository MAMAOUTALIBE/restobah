# Audit sécurité, authentification et API — 1er novembre 2026

Périmètre de départ : commit `0c5c588`, avant les corrections de cet audit complet. Rôle spécialisé sécurité ; skill `project-tester` appliqué. Ce document rapporte les contrôles exécutés et les changements encore nécessaires. Aucun code produit, secret, compte réel ou enregistrement métier existant n’a été modifié par ce rôle.

## Résultat à intégrer au plan

Les contrôles ciblés des accès existants passent. Aucun contournement d’autorisation P0/P1 n’a été reproduit dans ce périmètre. Deux points doivent être traités dans le plan : protection explicite du cache des API personnelles et alerte de dépendance de développement. Le nouveau paiement sur place demandé par le client exige une implémentation et une recette distinctes avant de pouvoir déclarer les commandes commerciales opérationnelles.

| Référence | Niveau | Constat vérifié | Correction et acceptation |
|---|---|---|---|
| SEC-01 | P2, confidentialité | Six GET API sensibles répondent 200 sans `Cache-Control`, avec seulement `Vary: Cookie`. La protection `no-store` du CRM n’est pas appliquée à ces réponses API. | Appliquer `no-store` aux réponses personnelles et de session, y compris les erreurs pertinentes. Conserver les contrats JSON et le comportement des API publiques. Rejouer le probe et les tests auth/commandes. |
| SEC-02 | P2, outillage | `npm audit` signale 11 alertes modérées en cascade, issues d’une seule vulnérabilité Minimatch, sans alerte haute ou critique. Les dépendances de production JavaScript ne sont pas touchées par ce résultat. | Corriger par une mise à jour compatible de l’outillage, puis lint/build/tests et nouveau scan. Ne pas accepter le downgrade ESLint 4 proposé par `npm audit fix --force`. |
| SEC-03 | Prérequis de mise en service | Le code de départ ne possède que simulation et Stripe test ; aucun vrai mode de règlement au restaurant. | Réaliser le mode sur place, ses droits, ses états et sa recette avant ouverture commerciale. Les exigences détaillées figurent ci-dessous. |

SEC-01 est un défaut de politique de cache reproduit, **pas la preuve d’une lecture des données d’un autre utilisateur**. Les contrôles de propriétaire et de permission passent. Le client React utilise déjà `cache: 'no-store'` pour ses requêtes ; cela ne remplace pas une politique de réponse serveur pour les autres consommateurs et caches.

## Parcours et frontières contrôlés

| Zone | Contrôles exécutés ou revue |
|---|---|
| Inscription et connexion client | Mot de passe faible, adresse dupliquée, normalisation, session et historique du bon propriétaire ; rejet sans CSRF. |
| Réinitialisation | Réponse générique, jeton à usage unique et ancien mot de passe invalidé ; aucun envoi SMTP réel effectué. |
| Adresses et favoris | Données limitées au propriétaire, refus d’une adresse étrangère et validation des saisies ; remplacement des favoris dans la portée du compte. |
| Suppression du compte | Mot de passe exigé ; adresses/favoris supprimés, commandes conservées et détachées ; comptes staff exclus de cette suppression. |
| CRM | Anonyme redirigé ; client, staff sans permission et staff inactif refusés ; lecteur autorisé en lecture mais refusé en écriture ; pages/fragments privés non stockables. |
| Commandes et paiement | Vrai propriétaire et staff avec permission autorisés ; suivi invité sans coordonnées ; absence de droit de paiement d’une commande étrangère pour un simple lecteur. Totaux calculés au serveur et idempotence couverts par les tests API. |
| CSRF | Refus de création/édition sans modification de données ; rejet d’Origin/Referer interdits même avec jeton valide ; page CRM 403 sans saisie ni raison technique exposée ; JSON API/admin conservé. |
| Limites de connexion | Fenêtre expirée, limitation des POST, maintien du GET et en-tête d’adresse non fiable ne permettant pas de contourner la limite. |
| Photos et HTML | Revue du décodage/réencodage raster, bornes poids/dimensions, UUID et échappement des templates ; tests supplémentaires ciblés des fichiers interdits et champs techniques. |
| Secrets et livraison | 350 chemins suivis par Git contrôlés : aucun `.env` privé, runtime, média utilisateur, sauvegarde, clé privée ou base de données suivi. `.gitignore` et `.dockerignore` relus. |

Les verrous SQL, compteurs partagés PostgreSQL et signatures Stripe sont présents dans le code et dans les tests existants. Ce rôle n’a pas effectué de nouvelle recette PostgreSQL ni d’échange externe Stripe ; les appels Stripe sortants des tests restent simulés.

## Tests réellement exécutés

### Lot authentification, accès et CSRF

**55 tests réussis, zéro ignoré, 8,011 s**, sur SQLite en mémoire. La base de test a été détruite.

```sh
DATABASE_URL=sqlite:///:memory: backend/.venv/bin/python backend/manage.py test shop.tests.APITests shop.tests.AdminThrottleTests shop.test_reliability.AccountDeletionTests shop.test_crm_csrf shop.test_crm.CRMTests.test_anonymous_customer_and_staff_without_permissions_are_denied shop.test_crm.CRMTests.test_reader_can_read_but_cannot_modify_any_module shop.test_crm.CRMTests.test_private_pages_and_fragments_are_never_cacheable shop.test_crm.CRMTests.test_public_order_access_requires_staff_permission_and_hides_guest_pii shop.test_crm.CRMTests.test_nonstaff_permission_and_inactive_staff_do_not_grant_order_access shop.test_crm.CRMTests.test_read_only_staff_cannot_initiate_another_customers_payment --noinput --verbosity 1
```

Deux tests supplémentaires, disjoints du lot précédent, réussissent en **0,651 s** : refus des photos invalides ou excessives et protection des champs techniques/rendu HTML du formulaire plat. Total ciblé de ce rôle : **57 réussites**, sans additionner une nouvelle fois les relances du coordinateur.

```sh
DATABASE_URL=sqlite:///:memory: backend/.venv/bin/python backend/manage.py test shop.test_crm.CRMTests.test_bad_or_excessive_photos_are_rejected shop.test_crm.CRMTests.test_product_form_does_not_allow_technical_fields_or_html_execution --noinput --verbosity 1
```

### Probe rouge de cache personnel

Script temporaire : `/tmp/stc-security-private-cache-probe.py`. Exécution :

```sh
backend/.venv/bin/python /tmp/stc-security-private-cache-probe.py
```

Un test **échoue comme attendu avant correction** sur l’absence de `no-store`. Les six réponses observées sont `/api/auth/csrf/`, `/api/auth/me/`, `/api/orders/`, `/api/orders/<référence>/`, `/api/addresses/` et `/api/favorites/` : statut 200, `Cache-Control` absent, `Vary: Cookie`. Toutes les écritures du probe utilisent une base SQLite mémoire détruite à la fin, avec utilisateurs et coordonnées synthétiques.

### Dépendances

- `npm audit --omit=dev --json` : **0 vulnérabilité** signalée.
- `npm audit --json` : **11 alertes modérées**, 0 haute et 0 critique, liées à [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249), avis primaire consulté le 1er novembre. Le correctif annoncé est Minimatch 11.0.1 ; l’arbre contient notamment 10.2.6 sous TypeScript ESLint et 3.1.5 sous ESLint. L’exploitation du site public n’a pas été démontrée : ces outils servent au développement et à la compilation.
- `pip-audit -r backend/requirements.txt --no-deps --disable-pip --format=json` : **19 dépendances, aucune vulnérabilité connue signalée**, sortie 0. Le scanner a été installé dans un environnement temporaire, sans modifier le venv ou les dépendances du projet. Rapport : `/var/folders/3g/s_97f3pn1kvdwk6c7dmwx14w0000gn/T/stc-security-pip-audit-gy_ibw7e/audit.json`.

### Contrôles HTTPS publics, sans connexion ni POST

TLS vérifié par le client Python standard, sans désactiver la validation du certificat. L’accueil renvoie 200 et les en-têtes HSTS, `nosniff`, `DENY`, `same-origin` et CSP attendus. La connexion CRM renvoie 200 avec `no-store` ; le bootstrap CSRF confirme aussi l’absence de politique de cache de SEC-01.

Les cookies observés ont `Secure` et `SameSite=Lax` ; la session possède `HttpOnly`. Le cookie CSRF est accessible au JavaScript, conformément au client qui construit l’en-tête CSRF. Aucune valeur de cookie n’a été imprimée.

Les GET de `/.env`, `/.git/config`, `/.runtime/admin-credentials.txt` et `/backend/db.sqlite3` retournent le HTML de la SPA, dont l’empreinte est exactement celle de l’accueil, **aucun contenu de fichier privé**. Leur statut 200 est un fallback de routage ; il n’est pas présenté comme une exposition de secrets.

## Conditions de sécurité du paiement sur place

Décision client reçue pendant cet audit : commandes réelles, paiement sur place. La référence de départ ne satisfait pas ce besoin. Le plan doit conserver une origine de paiement explicite par commande afin de ne pas confondre une dette sur place, une simulation, un paiement Stripe et un paiement encaissé.

- Création réelle confirmée avec montant dû sur place, sans la marquer payée et sans appel Stripe ; prix et mode toujours validés côté serveur.
- Préparation autorisée pour ce seul cas de règlement différé ; les restrictions Stripe existantes restent intactes.
- Encaissement uniquement par action staff autorisée, POST + CSRF, verrou de commande et contrôle de l’état attendu ; rejet anonyme, client et compte de lecture seule.
- Réessai idempotent, montant historique immuable, événement d’encaissement traçable ; aucun champ client permettant de s’auto-déclarer payé.
- Annulation et libellés adaptés à l’origine du paiement, sans prétendre rembourser une somme ni demander Stripe pour un règlement sur place.
- Avant une ouverture commerciale sur la même base, remplacer ou désactiver le compte démo aux droits d’écriture dont les accès ont été partagés. Aucun compte de la démonstration n’a été désactivé par cet audit.

## Références et limites

La recommandation de cache repose sur [OWASP REST Security, en-têtes de sécurité](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html#security-headers) et le comportement du décorateur [Django `never_cache`](https://docs.djangoproject.com/en/5.2/topics/http/decorators/#caching).

Ce contrôle n’est ni un test de charge, ni un pentest exhaustif de l’hôte, ni une certification juridique ou de paiement. L’absence de MFA reste une amélioration de défense ; elle n’a pas été présentée comme une faille d’autorisation reproduite. Domaine client, SMTP réel, identité et documents du restaurant, sauvegardes hors serveur et politique de conservation doivent recevoir leurs contrôles propres avant la livraison. Une formulation « sécurisé ou opérationnel à 100 % » n’est pas justifiée par ces seuls résultats.

## Actualisation après les corrections : SEC-01 et SEC-02

Les constats et scans ci-dessus décrivent bien la référence initiale `0c5c588`. Les deux corrections suivantes ont ensuite été livrées au coordinateur, sans commit ni publication par ce rôle :

- **SEC-01 corrigé** : base `PrivateAPIView` avec `never_cache`, héritée par les réponses personnelles, de session et les vues protégées ; le gestionnaire de rejet CSRF ajoute aussi ces en-têtes directement. Le JSON et les API publiques conservent leur contrat. Le probe initial devient vert pour les six GET ; **8 nouveaux tests réussissent**, puis **57 régressions réussissent** sur bases mémoire détruites. Ces tests d’implémentation ne remplacent pas le gate indépendant global du coordinateur.
- **SEC-02 corrigé** : seul l’override `minimatch: 11.0.3` et son lockfile ont été nécessaires. Dépendances directes et versions installées conservées ; `npm install`, installation propre `npm ci`, lint, TypeScript et build réussissent. Les deux scans NPM, complet et sans dépendances de développement, signalent désormais **0 vulnérabilité**. Aucun downgrade forcé ni migration majeure ESLint effectué.

## Revue indépendante du nouveau règlement sur place

Ce rôle n’est pas l’auteur des opérations financières. Relecture effectuée de `onsite_payments.py`, des modèles et registres, migration `0006`, permissions CRM, formulaire d’opération, routes/templates, API, garde-fous Stripe, notifications et libellés client.

Contrôles confirmés dans le code puis dans les cas ciblés :

- Origine du paiement persistée, strictement vérifiée au serveur et protégée contre les réécritures ORM ordinaires ; pas de champ client autorisant à se déclarer encaissé.
- Droit financier dédié `shop.record_onsite_payment`, ajouté aux droits de lecture/modification de commande et au statut staff actif. Les routes financières exigent POST et CSRF ; le service vérifie lui-même l’acteur et ses droits.
- Montant repris du total historique serveur, jamais du POST ; acteur et date pris côté serveur. Verrou de commande et transaction pour décision, état et création du registre.
- Préparation d’un montant dû sur place autorisée, clôture avant encaissement refusée ; remboursement sans encaissement ou d’une origine différente refusé. Reprises, conflits et incohérences du registre vérifiés.
- Événements non modifiables par les voies ORM/applicatives prévues et administration en lecture seule ; les deux régressions de réécriture par upsert et par nouvelle instance au PK existant sont couvertes. Il ne s’agit pas d’une certification d’inaltérabilité d’un logiciel de caisse ni d’une protection contre un administrateur SQL.
- Aucune trace d’acteur ou de registre financier dans l’API client ou invitée. Stripe ignore les commandes sur place, y compris avec une relation de paiement artificiellement ajoutée.

**10 tests ciblés indépendants réussissent, zéro ignoré, 1,466 s**, sur SQLite mémoire détruite. Aucun PostgreSQL ni suite complète n’a été relancé par ce rôle en parallèle de QA :

```sh
DATABASE_URL=sqlite:///:memory: backend/.venv/bin/python backend/manage.py test shop.test_onsite.OnSiteTests.test_service_denies_customers_reader_preparer_inactive shop.test_onsite.OnSiteTests.test_crm_actions_require_staff_finance_permission_and_post shop.test_onsite.OnSiteTests.test_csrf_and_forged_financial_inputs_rejected shop.test_onsite.OnSiteTests.test_private_api_has_origin_but_no_financial_actor_or_ledger shop.test_onsite.OnSiteTests.test_stripe_paths_never_touch_onsite_even_with_malicious_payment_relation shop.test_onsite.OnSiteTests.test_collect_exact_server_amount_actor_and_time_then_complete shop.test_onsite.OnSiteTests.test_no_refund_without_recorded_collection_or_wrong_origin shop.test_onsite.OnSiteTests.test_invalid_states_stale_request_and_inconsistent_amount_fail_without_write shop.test_onsite_integrity.OnSiteLedgerIntegrityTests --noinput --verbosity 1
```

### SEC-04 — retour arrière applicatif incompatible, reproduit avant correction

La migration `0006` initialement relue rend `payment_method` obligatoire avec un défaut Python, mais sans défaut SQL durable. Le retour vers l’image `0c5c588` après cette migration ne peut donc pas être annoncé fonctionnel : l’ancien modèle ne fournit pas cette colonne à l’INSERT.

Preuve réelle, et pas seulement lecture de métadonnées : `/tmp/stc-security-legacy-insert-probe.py` utilise le **modèle historique de la migration `0005`** obtenu par `MigrationExecutor.loader.project_state`, puis tente sa création après application de `0006`, dans une base jetable. Le modèle historique ne possède pas `payment_method` ; la colonne actuelle est `NOT NULL`, défaut SQL nul. L’INSERT échoue par **`IntegrityError: NOT NULL constraint failed: shop_order.payment_method`**. La base a été détruite.

**SEC-04 corrigé et retesté** : le modèle et la migration `0006` conservent désormais `db_default='simulation'`. Le même probe historique réussit : **1 test PASS, 0,009 s**, colonne `NOT NULL`, défaut SQL `'simulation'`, ancien modèle toujours dépourvu du champ. Le test durable `test_legacy_simulation_insert_after_migration_uses_durable_sql_default` vérifie aussi la vraie création historique, l’origine simulation, les états et tous les champs antérieurs conservés, sans événement financier créé.

Ce défaut SQL couvre uniquement le repli actuel vers l’ancienne **démonstration/simulation** ; il ne rend **pas** un ancien binaire Stripe ou sur place universellement compatible. Le premier déploiement commercial `on_site` demande une image de repli qui comprend ce mode, ou un maintien en maintenance ; aucune commande réelle ne doit être reclassée en simulation et aucune migration inverse destructrice n’est recommandée. Cette limite est explicitée dans `OPERATIONS.md` et `CLIENT-DELIVERY.md`.

## Revue finale des informations publiques et du contrôle de livraison

Relecture en lecture seule de `public_details.py`, `production_readiness.py`, `check_production.py`, du footer, des deux exemples d’environnement et de la procédure client. La liste publique contient seulement les cinq coordonnées/liens prévus : ni réglages privés, ni secrets SMTP/Django, ni déclaration d’approbation des contenus. Les URL sont limitées à HTTPS, sans authentification embarquée ni port alternatif ; les valeurs invalides sont masquées. Les liens sont rendus comme texte/attributs React, sans injection HTML. Les sondes refusent les adresses privées résolues et les redirections ; aucune donnée saisie par un utilisateur public ne déclenche ces sondes d’administration.

Le rapport emploie `configurationReady`, conserve `emailDelivery` et `offsiteBackup` à `not_checked`, même après une connexion SMTP ou une sauvegarde locale fraîche. La connexion SMTP n’envoie pas de message ; ni ce contrôle ni les documents ne constituent une autorisation commerciale automatique ou une certification de caisse. La validation déclarative des contenus n’est pas présentée comme une preuve juridique. Les exemples ne contiennent que des champs vides et marqueurs explicites ; aucun secret client n’a été inventé.

**13 tests ciblés supplémentaires réussissent, zéro ignoré, 0,747 s**, sur base mémoire détruite : les quatre tests de migration, validation des coordonnées/liens, absence de secret dans l’API et les erreurs de connexion, sondes explicites sans envoi, refus des schémas/adresses privés et commande JSON sans écriture. Ils ne sont pas additionnés aux suites PostgreSQL du coordinateur :

```sh
DATABASE_URL=sqlite:///:memory: backend/.venv/bin/python backend/manage.py test shop.test_onsite_migrations shop.test_production_readiness.PublicDetailsValidationTests shop.test_production_readiness.ProductionReadinessTests.test_configuration_and_public_api_never_expose_private_settings shop.test_production_readiness.ProductionReadinessTests.test_database_failure_does_not_leak_connection_secrets shop.test_production_readiness.ProductionReadinessTests.test_optional_probes_are_explicit_and_do_not_send_email shop.test_production_readiness.ProductionReadinessTests.test_smtp_probe_opens_and_closes_without_sending shop.test_production_readiness.ProductionReadinessTests.test_url_probe_refuses_private_addresses_redirects_and_invalid_schemes shop.test_production_readiness.ProductionReadinessTests.test_command_json_is_read_only_and_exits_nonzero_on_blockers --noinput --verbosity 1
```

### SEC-05 — faux blocage du préflight avec les alias de santé internes

**P2, fiabilité du contrôle de configuration, reproduit et transmis au correcteur.** Le domaine public exact seul passe. Le même domaine accompagné de `backend`, `localhost` et `127.0.0.1` est refusé par `all(public_host(...))`, alors que ces alias internes peuvent coexister avec la configuration HTTPS publique. La compose de production remplace les hôtes via l’environnement : il s’agit du blocage d’une configuration valide contenant ces alias, pas d’un échec systématique de toute production.

Preuve sans base ni réseau : `backend/.venv/bin/python /tmp/stc-security-readiness-hosts-probe.py` exécute deux tests : **1 échec attendu avant correction** pour le domaine public avec les trois alias ; **1 réussite** pour le refus du wildcard, d’un suffixe générique, de l’absence du domaine public et d’alias privés arbitraires. Correction retenue par le coordinateur : autoriser ces seuls trois alias de santé, conserver le domaine `FRONTEND_URL` public exact obligatoire et tous les refus précédents. Le retest reste à effectuer par la vague de correction/QA suivante ; aucune modification produit n’a été faite dans cette revue.

### Contrôle des fichiers livrables

`/tmp/stc-security-delivery-files-scan.py` contrôle la liste Git suivie **et** les nouveaux fichiers non ignorés : **384 chemins, 197 fichiers UTF-8 analysés**. Aucun chemin privé/runtime/base/sauvegarde/clé, aucune signature courante de clé privée ou jeton fournisseur et aucune valeur secrète non vide/non-placeholder dans les exemples d’environnement détectés. Seuls comptes et valeurs synthétiques explicitement destinés aux tests sont utilisés dans les nouveaux tests relus. Aucun contenu des fichiers privés ignorés ni aucune valeur secrète n’a été affiché. `.gitignore`, `.dockerignore` et `git diff --check` contrôlés. Ce scan ciblé de signatures ne prétend pas démontrer l’absence universelle de tout secret.

**Conclusion finale de ce rôle : contrôles financiers ciblés PASS ; SEC-01, SEC-02 et SEC-04 corrigés avec contrôles exécutés. La publication reste conditionnée au retest de SEC-05, aux gates PostgreSQL/navigateur/exploitation du coordinateur et à la levée des prérequis réels du client.** Aucun autre défaut matériel n’a été identifié dans cette relecture ciblée. Aucun compte, moyen de paiement, envoi SMTP, sauvegarde ou donnée de production n’a été modifié par cette revue.

### SEC-06 — suppression publique d’un ancien opérateur financier

**P2, erreur serveur reproduite puis corrigée.** Après un encaissement créé par le service autorisé, un opérateur démis de son rôle `is_staff` pouvait accéder au parcours de suppression de compte client. Le POST réel avec session et CSRF valides rencontrait la clé étrangère `OnSitePaymentEvent.actor` en `PROTECT` et renvoyait une erreur 500 non gérée. Le test durable `PrivateAPICacheTests.test_former_staff_with_financial_history_cannot_self_delete` a d’abord reproduit **500 au lieu de 400** dans une base jetable.

La vue conserve `PROTECT` et intercepte uniquement `ProtectedError`, après la sortie de la transaction atomique. Elle répond 400 avec un message générique invitant à contacter le restaurant, sans identifiant de commande, donnée du registre ni détail SQL ; les en-têtes privés `no-store` restent présents. La déconnexion n’est effectuée qu’en cas de suppression réussie. Le test vérifie aussi le refus sans CSRF, la conservation exacte du compte, de toutes ses commandes, de ses adresses/favoris et du registre, ainsi que la session toujours active après refus.

Validation d’implémentation : **11 tests réussis, zéro ignoré, 1,536 s**, incluant les deux tests historiques de suppression et les neuf tests de cache privés ; base SQLite mémoire détruite. Aucun schéma ni garde financière modifié. `git diff --check` réussit. Le code est figé pour la recette indépendante du coordinateur ; cette validation d’implémentation ne remplace pas ce gate.

```sh
DATABASE_URL=sqlite:///:memory: backend/.venv/bin/python backend/manage.py test shop.test_api_cache shop.test_reliability.AccountDeletionTests --noinput --verbosity 1
```
