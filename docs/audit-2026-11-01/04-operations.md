# Audit exploitation, base et livraison — 1er novembre 2026

Périmètre : Docker, Compose, proxys, CI, sauvegardes, restauration, paquet de livraison et préparation du déploiement client du 2 novembre. Référence auditée : `0c5c5885cd4fba186b1582f2068f3a5f88342bfb`. Skill appliqué : `project-tester`.

**Verdict initial : démonstration accessible, préparation commerciale incomplète.** Ce constat ne remplace pas les validations fonctionnelles des autres lots. Les corrections proposées ci-dessous n’ont pas été appliquées par cet audit.

## État réel contrôlé en lecture seule

| Contrôle | Observation exécutée |
|---|---|
| Version publiée | Marqueur serveur identique à `0c5c5885cd4fba186b1582f2068f3a5f88342bfb`. |
| Services | Backend et PostgreSQL sains ; frontend en cours d’exécution, sans healthcheck propre. PostgreSQL **17.11**. |
| Exposition | Frontend publié uniquement sur `127.0.0.1:18200`. Aucun port backend ou PostgreSQL publié. |
| TLS existant | Vérification TLS standard réussie sur `stc.srv2086522.hstgr.cloud`, certificat valable jusqu’au **23 janvier 2027**. Timer Certbot visible. |
| Domaine antérieurement envisagé | Aucun résultat DNS pour `stc.sonutech.tech` au moment du contrôle. Ce nom ne remplace pas la confirmation du domaine du client. |
| Configuration | `DEBUG=False`, démonstration active et paiement simulé. Backend e-mail fichier privé ; hôte, utilisateur et mot de passe SMTP non configurés ; destinataires d’alerte équipe absents. Aucun secret affiché. |
| Persistance | Volumes PostgreSQL et médias présents. Le backend ne monte **que `/app/media`** : `/app/.private-emails` et `/app/.runtime` restent dans la couche du conteneur. Leurs répertoires existent en `0700`, sans fichier lors du contrôle. |
| Sauvegardes | Deux sauvegardes privées de déploiement présentes, dossiers `0700`. Celle de `0c5c588` contient un dump de **80 543 octets** et une archive médias lisible. |
| Planification visible | Aucun job STC dans le crontab de `deploy`, aucun timer nommé STC visible. Cela ne constitue pas un inventaire de tous les crontabs root ou d’un service de sauvegarde externe. Aucun planning STC n’est documenté comme installé. |
| Capacité | Environ **158 Gio** libres sur le système de fichiers de `/opt/stc`. |

Les commandes distantes ont été limitées à des lectures ciblées : états et destinations des montages Docker, paramètres non secrets, marqueur, métadonnées de sauvegarde, DNS et certificat. Aucun environnement Docker complet, contenu `.env`, mot de passe, e-mail privé ou donnée client n’a été publié.

## Défauts confirmés et plan de correction

| Priorité | Constat et preuve | Correction minimale proposée | Acceptation |
|---|---|---|---|
| **P0 livraison commerciale** | Le mode demandé est désormais **commandes réelles avec paiement sur place**, alors que l’instance est en démonstration/simulation et que le code initial n’offre pas ce mode distinct. | Ajouter un mode sur place explicite, sans marquer une commande impayée comme payée ou simulée ; conserver les protections Stripe et les refus des configurations incohérentes. | Parcours invité et connecté, commande reçue dans le CRM, montants conservés et statut de paiement exact ; configuration hors démo vérifiée sur instance jetable. |
| **P1** | La CI du commit publié échoue : **154 parcours réussis, 3 en échec** sur l’égalité de hauteur des cartes à 388 px, écart réel **13,671875 px** attendu inférieur à 1 px. | Corriger la cause de rendu et les hypothèses de plateforme après reproduction ; ne pas élargir la tolérance pour dissimuler l’écart. | Même scénario vert sur les trois projets et CI complète verte. |
| **P1 recette/fiabilité** | Les journaux CI contiennent aussi `sorry, too many clients already`. La configuration impose des connexions persistantes de 60 s alors que la recette utilise le serveur Django multithreadé. | Désactiver les connexions persistantes en développement/recette, ou choisir un serveur adapté ; ne pas augmenter aveuglément la capacité PostgreSQL. | Suite PostgreSQL complète sans saturation et contrôle des connexions après une charge représentative. |
| **P1 exploitation** | Les e-mails privés et le runtime ne disposent pas de stockage persistant. Un `up --force-recreate` ordinaire perdrait ces fichiers ; les scripts manuels précédents compensent ce manque par une sauvegarde/restauration spécifique. | Ajouter un stockage privé persistant adapté et sa procédure d’initialisation des permissions ; sauvegarder avant la première migration de stockage. | Écrire un marqueur synthétique sur une pile jetable, recréer le backend, vérifier conservation et droits `0700/0600`, puis supprimer la pile. |
| **P1 exploitation** | Les sauvegardes constatées sont ponctuelles de déploiement ; aucun planning STC ou copie extérieure chiffrée n’est confirmé. | Fournir une procédure automatisable, une rétention et un contrôle de fraîcheur ; installer le planning seulement pour cette application et définir la destination externe avec le client. | Dump et médias restaurables ; erreurs non silencieuses ; surveillance d’une sauvegarde absente ou trop ancienne. Ne pas prétendre qu’une copie hors serveur existe sans destination vérifiée. |
| **P1 paquet de livraison** | `scripts/package.py` omet `compose.vps.yaml`, pourtant requis par le déploiement documenté sur VPS partagé. Reproduction sur un répertoire temporaire : configurations de base et Caddy présentes, configuration VPS absente ; SHA-256 correct. | Inclure la configuration VPS et ajouter un contrôle de contenu du paquet. | Archive contenant les trois fichiers Compose et les proxys nécessaires, sans secrets ni données métier. |
| **P2 sauvegarde SQLite** | Une source SQLite corrompue provoque `DatabaseError` mais laisse un nouveau fichier de sauvegarde de **0 octet**. La branche PostgreSQL nettoie déjà ses sorties incomplètes. | Supprimer la sortie SQLite en cas d’échec et publier une sauvegarde seulement après validation, idéalement par renommage atomique. | Test positif d’intégrité ; test négatif ne laissant aucune sauvegarde sélectionnable ; fichier final privé. |

Les informations de restaurant, le domaine final, les documents validés et les accès SMTP réels restent des dépendances externes. Le coordinateur les a demandés ; ils ne doivent pas être inventés. Le précontrôle de livraison doit signaler leur absence au lieu de déclarer le restaurant prêt.

## CI réellement consultée

La consultation GitHub est en lecture seule, sans relance de workflow :

```sh
gh run list --repo MAMAOUTALIBE/restobah --branch main --limit 4 --json databaseId,headSha,status,conclusion,displayTitle,url
gh run view 41271721589 --repo MAMAOUTALIBE/restobah --json jobs,conclusion,headSha,url
gh run view 41271721589 --repo MAMAOUTALIBE/restobah --log-failed
```

[Exécution CI du commit `0c5c588`](https://github.com/MAMAOUTALIBE/restobah/actions/runs/41271721589) : installation, TypeScript/lint/build, audit Python, contrôle des migrations et étape des tests Django réussis. L’étape `python3 scripts/e2e.py` échoue après 8,4 min. Les trois échecs visent `tests/product-cards.spec.ts:127`, même scénario sur ordinateur, tablette et mobile. Les deux commits précédents ont également une conclusion en échec ; le premier commit du dépôt avait une conclusion réussie.

Le nombre de tests Django n’a pas été déduit de la seule réussite de l’étape : ce rapport constate son statut, tandis que les totaux détaillés restent dans les journaux et le bilan de validation central.

## Restauration réellement effectuée

La sauvegarde du déploiement `0c5c588` a été copiée dans un répertoire temporaire local `0700`, avec fichiers `0600`, puis restaurée dans un **PostgreSQL 17 jetable**, sans réseau et sans port publié. Les données du conteneur utilisaient un stockage mémoire temporaire.

Contrôles effectués : `pg_restore --no-owner --exit-on-error`, puis comparaison des comptages de huit modèles avec `business-before.json` de la même sauvegarde : restaurant, produits, catégories, horaires, fermetures, commandes, lignes et historique. **PASS : huit comptages identiques.** Aucun contenu de ligne ni aucune coordonnée client n’a été imprimé.

Le conteneur, son stockage temporaire et la copie privée locale ont été supprimés dans un bloc `finally`. Aucun objet n’a été restauré dans la base en ligne. Ce test prouve que cette sauvegarde de déploiement est restaurable ; il ne prouve pas qu’elle contient tous les changements effectués après son horodatage.

## Essai isolé des connexions PostgreSQL

Un second PostgreSQL 17 jetable, limité à 20 connexions et publié sur un port local aléatoire, a servi une base de recette. Deux processus Django ont été démarrés successivement, avec les mêmes paramètres de base et 45 GET `/api/health/` chacun :

| Serveur | Réponses | Connexions ouvertes observées après la série |
|---|---|---|
| `runserver --noreload` multithreadé, persistance 60 s | 45/45 HTTP 200 | 15 |
| Même serveur avec `--nothreading` | 45/45 HTTP 200 | 2 |

Cet essai confirme la rétention accrue ; il **n’a pas reproduit la saturation** à cette charge. La saturation elle-même est constatée dans le journal CI. La [documentation primaire Django 5.2](https://docs.djangoproject.com/en/5.2/ref/databases/#caveats) explique que chaque thread possède sa connexion et déconseille la persistance avec le serveur de développement, qui crée des threads par requête. Cette source appuie le diagnostic, sans remplacer une nouvelle recette complète après correction.

Les deux processus Django, le conteneur et les fichiers privés temporaires ont été arrêtés et supprimés. La base locale de développement et ses services existants n’ont pas été utilisés.

## Vérifications de configuration exécutées

- `docker compose --env-file .env.production.example -f compose.yaml -f compose.vps.yaml config --quiet` : **PASS**.
- Même contrôle avec `compose.production.yaml` : **PASS**.
- `nginx:1.28-alpine nginx -t`, sans réseau, configurations montées en lecture seule et aucun port publié : **PASS**.
- `caddy:2-alpine caddy validate`, mêmes contraintes : **PASS**, avec avertissement de formatage du Caddyfile. Un premier lancement local avait échoué faute de binaire du gestionnaire de credentials Docker dans `PATH` ; l’ajout du chemin Docker Desktop a permis la vérification, sans changer le projet.
- Sur le backend en ligne : `check --deploy --fail-level WARNING` et `migrate --check --noinput`, tous deux en lecture seule : **PASS**, codes de sortie 0 ; aucun avertissement de déploiement, aucune migration en attente.
- Paquet sur fixture : SHA-256 conforme, absence des faux secrets et données privées, omission de la configuration VPS **reproduite**.
- Sauvegarde SQLite sur fixtures : cas sain, intégrité et mode final `0600` **PASS** ; cas corrompu laissant une sortie vide **défaut reproduit**.

## Recommandation de livraison

Construire et valider les corrections sur une pile isolée, sauvegarder avant la mise à jour et conserver les images précédentes. Sur le VPS partagé, continuer d’utiliser `compose.vps.yaml` ; ne pas lancer Caddy sur les ports 80/443 de l’hôte et ne pas toucher aux autres applications. Aucune réinitialisation, aucun `seed_demo`, aucune restauration destructive et aucun changement de DNS/SMTP/paiement n’ont été effectués par ce lot.

Le passage commercial doit rester conditionné aux contrôles du mode sur place, à une CI et une recette finales vertes, aux informations réelles du client et à la vérification effective des services externes indispensables. Aucun résultat de cet audit ne constitue une garantie d’absence absolue de défaut.

## Lot E — correctifs préparés après le plan

Le coordinateur a autorisé l’implémentation de ce lot après les gates précédents. Les changements sont prêts pour **validation indépendante**, sans installation sur le serveur :

- Connexions : âge maximal nul en développement/tests ; production 60 secondes par défaut, configurable par `DJANGO_DB_CONN_MAX_AGE` entre 0 et 3600. Aucun changement au contrat de paiement sur place dans ce fichier.
- Sauvegarde SQLite et PostgreSQL seule : publication atomique sans écrasement, fichiers `0600`, dossiers privés et nettoyage des sorties en erreur.
- Sauvegarde complète : PostgreSQL, médias, privés du backend et privés directs de l’hôte, manifeste SHA-256, vérification des chemins et liens, verrou, rétention limitée aux archives reconnues du même projet, contrôle de fraîcheur utilisant la date du manifeste. Les signaux d’arrêt ordinaires déclenchent le nettoyage ; un arrêt forcé du système peut laisser un répertoire temporaire privé, jamais publié comme sauvegarde valide.
- Persistance : volumes privés réservés au backend, hérités par les deux overrides. Aucun montage de sauvegarde dans le service public.
- Livraison : configuration VPS incluse ; liens, fichiers d’environnement réels, bases et types de clés privées exclus du paquet.
- Exploitation : [procédure complète](../BACKUPS.md), quatre modèles d’unités systemd strictement STC et limite explicite du repli vers un ancien code après activation de `on_site`. Aucune planification installée par ce lot.
- Précontrôle : seul `scripts/backup.py` est copié dans l’image backend. La lecture d’une sauvegarde de l’hôte se fait ponctuellement dans un conteneur supprimé après contrôle, sans port, avec montage en lecture seule ; le backend web reste sous son utilisateur habituel.

### Contrôles producteur exécutés

```sh
python3 -m unittest discover -s tests -p 'test_operations.py' -v
STC_RUN_DOCKER_TESTS=1 STC_OPS_BACKEND_IMAGE=IMAGE_DE_TEST python3 -m unittest discover -s tests -p 'test_operations_docker.py' -v
```

**16 tests d’outillage réussis** : sauvegarde réelle SQLite, corruption sans sortie vide, umask, paquet/VPS et secrets/liens, hachages et archive tronquée, traversée interne refusée, fraîcheur, verrou et rétention ; six variantes de la politique de connexion sont aussi contrôlées dans ce lot.

**Un test Docker d’intégration réussi**, 12,415 s : projet Compose aléatoire, base PostgreSQL jetable, aucun port applicatif publié, fichiers synthétiques dans médias/runtime/e-mails, vraie recréation du backend, conservation UID `10001` et modes `0700/0600`, sauvegarde complète puis restauration du dump dans une seconde base isolée, lecture des contenus médias et privés sauvegardés. Pile, volumes et fichiers temporaires nettoyés.

L’image locale ancienne `stc-backend` portait encore des répertoires privés `0755`. Le premier essai l’a refusée. Une image de fixture isolée, dérivée en changeant seulement les deux modes pour correspondre au Dockerfile actuel (`0700`), a permis le test. Sa configuration d’entrée a été neutralisée pour le processus `sleep` de fixture. Cette image a été supprimée. **La QA de release doit rejouer ce même test sur l’image backend fraîche**, comprenant aussi la nouvelle copie du script de vérification.

Compilation des scripts/tests et `git diff --check` réussis. Le serveur possède Python 3.14.4. La lecture `systemd-analyze calendar` a accepté le planning à 03 h 15 Europe/Paris (prochaine occurrence observée : 2 novembre 2026, 02 h 15 UTC) ainsi que le planning horaire. Aucune unité n’a été installée et aucune donnée d’instance n’a été modifiée par ces essais.

### Contrat transmis pour la livraison

```sh
python3 scripts/backup.py --postgres --full --project-name stc --compose-file compose.yaml --compose-file compose.vps.yaml --keep 7
python3 scripts/backup.py --project-name stc --check-freshness 26
```

Le contrôle de fraîcheur ne contacte pas Docker et n’écrit rien : succès en JSON (`status`, nom de l’archive, âge en heures), code 0 ; sinon message d’échec et code non nul. `--directory` redirige le dossier et `--verify` vérifie une archive sans la restaurer. Pour le précontrôle dans l’image, le coordinateur a validé un montage ponctuel `/opt/stc/backups:/audit-backups:ro` avec `--user 0`, jamais un montage permanent dans le service public. La création des sauvegardes reste une tâche de l’hôte.
