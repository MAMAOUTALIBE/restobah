# Exploiter STC

## Administration et commande

Ouvrir `/admin/` sur le même domaine que le site. En local, les identifiants générés sont dans `.runtime/admin-credentials.txt` (fichier privé). La commande `dev_admin` ne fonctionne qu’en développement. En production, utiliser `python manage.py createsuperuser`, puis créer des comptes du personnel avec seulement les permissions nécessaires.

Dans l’administration :

1. Restaurant : nom, adresse, frais, codes postaux acceptés, minimum de livraison, activation du retrait/livraison, délais affichés (« 15–20 min », « 30–40 min »). La livraison exige au moins un code postal ; une zone vide ferme la livraison au lieu d’accepter toutes les adresses.
2. Horaires et fermetures : créneaux par jour, dates exceptionnelles. En mode démo, l’ouverture horaire est simulée ; hors démo, les créneaux réels sont appliqués.
3. Produits : recette, photos, allergènes, disponibilité, groupes d’options et ordre d’affichage. Une option obligatoire est définie par le minimum de son groupe ; si aucun choix disponible ne permet d’atteindre ce minimum, le plat est affiché « Temporairement indisponible ». Les allergènes se saisissent en liste JSON (`["gluten", "lait"]`), toute autre forme est refusée. La note (`4,9`) doit provenir d’avis vérifiés ; laissée vide, elle n’est pas affichée. Les catégories créées ici apparaissent automatiquement sur le site dès qu’elles contiennent un plat.
4. Promotions : produit source, pourcentage et dates. Le prix promotionnel est recalculé côté serveur.
5. Commandes : la liste se recharge toutes les 30 secondes (sauf pendant une sélection ou une saisie) et affiche client, téléphone, statut, paiement et la colonne « Remboursement à effectuer » ; la recherche accepte la référence, le nom, l’e-mail ou le téléphone. Consulter les coordonnées et le détail, puis passer de « Confirmée » à « En cuisine », « Prête » et « Terminée ». Le site client actualise le suivi. Les transitions incohérentes sont refusées.

Un paiement en attente ne peut pas partir en préparation. Un paiement payé doit être remboursé dans Stripe et confirmé par webhook avant une annulation administrative. Annuler une commande « En attente de paiement » ferme d’abord sa session Stripe ; si Stripe est injoignable ou si le client vient de payer, l’annulation est refusée avec un message explicite. Si un paiement arrive malgré tout sur une commande annulée, il est enregistré (« Annulée » + « Payé »), signalé dans les journaux et dans la colonne « Remboursement à effectuer » : rembourser dans Stripe, le webhook passe alors le paiement en « Remboursé ». Les statuts et les prix historiques sont conservés.

## Comptes clients

Un client peut supprimer son compte depuis « Mon espace » en confirmant son mot de passe : compte, adresses et favoris sont effacés, les commandes déjà passées restent enregistrées (coordonnées comprises) et ne sont plus rattachées au compte. Les comptes de l’équipe se suppriment depuis l’administration. L’export des données et la durée de conservation des commandes relèvent de la politique du restaurant.

## Notifications de commande

À chaque commande confirmée (création en mode simulation, webhook payé en mode Stripe), le client reçoit un e-mail récapitulatif avec un lien de suivi personnel. Si `STC_ORDER_NOTIFICATION_EMAIL` contient une ou plusieurs adresses (séparées par des virgules), l’équipe reçoit aussi une alerte avec coordonnées, précision du client et lien vers l’administration. Un échec SMTP n’annule jamais la commande : il est journalisé (`shop.notifications`). En local, ces e-mails sont des fichiers privés de `backend/.private-emails/`.

## Paiement Stripe de test

Renseigner dans `.env` :

```dotenv
STC_PAYMENT_MODE=stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
FRONTEND_URL=http://localhost:5173
```

Redémarrer Django. Pour les webhooks locaux, installer et authentifier la CLI Stripe puis lancer :

```sh
stripe listen --forward-to localhost:8000/api/payments/webhook/
```

Utiliser le secret `whsec_...` fourni par cette session. Les événements traités incluent les sessions payées, expirées et échouées ainsi que les remboursements complets. Le serveur vérifie la signature, le mode test, la session, la devise et le montant ; les événements déjà traités ne sont pas appliqués une seconde fois. Un montant inattendu n’est jamais appliqué et produit une erreur dans les journaux (`shop.payments`).

Les sessions Stripe expirent après 31 à 41 minutes. Les commandes restées impayées plus de `STC_PENDING_PAYMENT_MINUTES` (45 par défaut) sont annulées par la commande suivante, à planifier toutes les 5 à 10 minutes en production (cron de l’hôte) :

```sh
docker compose -f compose.yaml -f compose.production.yaml exec -T backend python manage.py cancel_stale_orders
```

Elle ferme la session Stripe avant d’annuler et conserve toute commande dont le paiement est peut-être en cours.

La redirection de retour sert seulement à afficher le suivi. Elle ne confirme pas le paiement. Les clés manquantes, les erreurs réseau et les annulations ne doivent pas vider le panier. Sans clés de test, seuls les tests automatisés avec doubles et les erreurs de configuration peuvent être vérifiés : un test de bout en bout sur le service Stripe reste nécessaire.

## E-mails et réinitialisation du mot de passe

En local, les e-mails sont écrits dans `backend/.private-emails/`, avec accès privé (`EMAIL_BACKEND=shop.email_backend.PrivateFileEmailBackend`, valeur de `.env.example` ; un ancien `.env` avec le backend fichier standard de Django produit des fichiers lisibles par les autres comptes de la machine). Ce dossier contient des liens de réinitialisation sensibles ; il n’est ni exposé par le serveur ni inclus dans les images Docker. Ne pas le partager ni le versionner.

En hébergement, configurer `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` et `DEFAULT_FROM_EMAIL`. `FRONTEND_URL` doit correspondre au domaine public HTTPS. Vérifier une vraie réception avant d’ouvrir les inscriptions.

## Sauvegardes

SQLite local :

```sh
python3 scripts/backup.py
```

Le script crée une sauvegarde cohérente via l’API SQLite et vérifie son intégrité. Les fichiers sont privés dans `backups/`.

PostgreSQL Docker :

```sh
python3 scripts/backup.py --postgres
```

Sauvegarder aussi le volume des médias :

```sh
mkdir -p backups
# Archive locale à conserver dans un emplacement privé.
docker compose exec -T backend tar -C /app/media -czf - . > backups/media.tar.gz
chmod 600 backups/media.tar.gz
```

Conserver les sauvegardes chiffrées hors du serveur, avec une rétention adaptée, et tester périodiquement une restauration sur une instance isolée. Elles contiennent les coordonnées des clients. Les secrets de configuration sont sauvegardés séparément.

## Restauration

Arrêter les écritures avant de restaurer. Sauvegarder d’abord la base actuelle.

Pour SQLite, arrêter le serveur, remplacer `backend/db.sqlite3` par la sauvegarde choisie, vérifier `PRAGMA integrity_check`, puis relancer migrations et application.

Pour PostgreSQL, restaurer d’abord dans une base isolée afin de contrôler le résultat. Une restauration remplaçant la base active est une opération destructive à effectuer explicitement après sauvegarde :

```sh
# Pendant la maintenance : arrêter l’API qui écrit dans la base.
docker compose stop backend frontend
# Le fichier choisi remplace les données de la base cible.
docker compose exec -T db pg_restore -U stc -d stc --clean --if-exists < backups/SAUVEGARDE.dump
docker compose up -d
```

Restaurer les médias correspondants si nécessaire et tester connexion, catalogue et commandes avant réouverture.

Contrôle de restauration sans risque (effectué le 25 octobre 2026 sur les sauvegardes du jour) :

```sh
# PostgreSQL : base temporaire, la base active n’est pas modifiée.
docker compose exec -T db psql -U stc -d postgres -c "CREATE DATABASE restore_check"
docker compose exec -T db pg_restore -U stc -d restore_check --no-owner --exit-on-error < backups/SAUVEGARDE.dump
docker compose exec -T db psql -U stc -d restore_check -c "select count(*) from shop_order"
docker compose exec -T db psql -U stc -d postgres -c "DROP DATABASE restore_check"
# SQLite : copie de travail.
cp backups/SAUVEGARDE.sqlite3 /tmp/restore.sqlite3 && sqlite3 /tmp/restore.sqlite3 "PRAGMA integrity_check"
```

## Réparer les compteurs d’identifiants PostgreSQL

Une ancienne initialisation par `seed_demo` pouvait laisser le compteur automatique des plats ou du restaurant derrière les identifiants déjà présents. Le symptôme est une erreur de clé primaire à l’ajout d’un plat. Après installation de la version corrigée, réparer une base existante avec :

```sh
docker compose -f compose.yaml -f compose.production.yaml exec -T backend python manage.py repair_crm_sequences
```

Adapter les fichiers Compose à l’instance utilisée. En environnement Python direct : `python manage.py repair_crm_sequences`. L’option `--database` permet de choisir un alias Django ; par défaut, la commande utilise `default`.

Cette commande avance uniquement les compteurs automatiques `Product` et `Restaurant`, en tenant compte des valeurs déjà réservées. Elle ne réduit jamais un compteur, ne charge aucun exemple, ne recrée aucun plat supprimé et ne modifie ni prix ni réglages. Elle peut être relancée. Sur SQLite, ces compteurs sont déjà gérés automatiquement et la commande ne change rien.

Le verrou de tables laisse les lectures ouvertes et fait attendre brièvement les écritures concurrentes pendant le contrôle. Les valeurs de séquence déjà consommées ne sont pas réutilisées, conformément au fonctionnement de [PostgreSQL 17](https://www.postgresql.org/docs/17/functions-sequence.html). Il n’y a aucune migration de schéma à exécuter pour cette réparation. L’initialisation `seed_demo` corrigée applique le même contrôle ; sur une base personnalisée, utiliser la réparation seule pour conserver les suppressions décidées par le restaurant.

## Préparer la production

La configuration est prête à renseigner, mais aucune publication n’est effectuée automatiquement.

1. Renseigner l’identité, l’adresse, les allergènes, les horaires, les zones et les documents d’information réels.
2. Préparer un hôte Docker, un domaine pointant vers cet hôte et les ports 80/443.
3. Créer un `.env` privé à partir de `.env.production.example` ; générer une clé Django et un mot de passe PostgreSQL uniques. Aucun secret dans une variable `VITE_*`.
4. Configurer et tester SMTP et Stripe test. Renseigner `STC_ORDER_NOTIFICATION_EMAIL` (alerte de l’équipe). Le code refuse les clés Stripe réelles ; les paiements commerciaux demandent une validation distincte.
5. Faire une sauvegarde avant chaque mise à jour de schéma.
6. Construire avec `docker compose -f compose.yaml -f compose.production.yaml build`.
7. Exécuter `migrate` via cette même combinaison de fichiers. Les fichiers statiques sont collectés pendant la construction de l’image. Charger les données de démonstration seulement si la base doit être initialisée comme telle, puis remplacer leur contenu.
8. Lancer avec `docker compose -f compose.yaml -f compose.production.yaml up -d`. Caddy gère les certificats HTTPS quand le domaine est correctement configuré.
9. Exécuter `python manage.py check --deploy` dans le conteneur, puis vérifier santé, sécurité, comptes, livraison et paiements test depuis le domaine réel.
10. Planifier `cancel_stale_orders` (voir « Paiement Stripe de test ») et la sauvegarde quotidienne.

Limites de débit : `ANON_THROTTLE_RATE` et `USER_THROTTLE_RATE` (3000/heure par défaut, lectures et suivi), `ORDER_THROTTLE_RATE` (création de commande seulement, 60/heure hors développement) et `AUTH_THROTTLE_RATE` (connexion, inscription, réinitialisation, 20/heure). Elles sont comptées par IP pour les invités ; plusieurs clients derrière une même IP (CGNAT mobile, entreprise) partagent ce budget. Sur PostgreSQL, les compteurs sont partagés entre les workers dans la table `stc_cache` (créée par la migration 0005 : toujours migrer avant de démarrer une nouvelle version) ; en développement SQLite, ils restent en mémoire.

Le backend et PostgreSQL ne publient aucun port directement. Les médias sont servis séparément des fichiers exécutables, les ressources de l’interface viennent du même domaine et les cookies deviennent sécurisés hors développement. Le proxy écrase les en-têtes de protocole ; les logs d’accès n’enregistrent pas les paramètres de requête qui peuvent contenir un jeton invité.

## Déploiement derrière un nginx existant (VPS partagé)

Quand le serveur sert déjà d’autres sites sur les ports 80/443, ne pas lancer Caddy (`compose.production.yaml`) : utiliser `compose.vps.yaml`, qui n’expose l’application que sur `127.0.0.1:${STC_HTTP_PORT}` (18200 par défaut). Le nginx de l’hôte termine TLS ; le conteneur nginx conserve l’IP réelle du client (`X-Real-IP`) et le schéma HTTPS (`X-Forwarded-Proto`), indispensables aux limites de débit et à la redirection HTTPS de Django.

```sh
# Dans le dossier de l’application sur le serveur ; .env privé (600) avec DJANGO_SECRET_KEY,
# POSTGRES_PASSWORD, DJANGO_ALLOWED_HOSTS, DJANGO_CSRF_TRUSTED_ORIGINS, FRONTEND_URL, STC_HTTP_PORT.
C="docker compose -p stc -f compose.yaml -f compose.vps.yaml"
$C build
$C up -d db
$C run --rm -T backend python manage.py migrate --noinput </dev/null
$C run --rm -T backend python manage.py seed_demo </dev/null        # démonstration uniquement
$C run --rm -T -e DJANGO_SUPERUSER_EMAIL -e DJANGO_SUPERUSER_PASSWORD backend python manage.py createsuperuser --noinput </dev/null
$C up -d
# Vhost de l’hôte : adapter server_name et port de deploy/nginx-host.conf.example.
sudo install -m 644 deploy/nginx-host.conf.example /etc/nginx/sites-available/stc.example.com
sudo ln -s /etc/nginx/sites-available/stc.example.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d stc.example.com      # une fois le DNS pointé vers le serveur
```

`-T` et `</dev/null` évitent que `docker compose run` consomme l’entrée d’un script. Mise à jour : synchroniser le code (sans `.env`, `.runtime/`, bases ni sauvegardes), sauvegarder (`python3 scripts/backup.py --postgres` depuis ce dossier), puis `$C build && $C run --rm -T backend python manage.py migrate --noinput </dev/null && $C up -d`.

## Démonstration publique déployée (25 octobre 2026)

| Élément | Valeur |
| --- | --- |
| Adresse en service | https://stc.srv2086522.hstgr.cloud (certificat Let’s Encrypt, renouvelé par `certbot.timer`) |
| Adresse définitive | https://stc.sonutech.tech : vhost prêt, **enregistrement DNS absent** |
| Serveur | VPS Hostinger `srv2086522` (72.61.193.220), utilisateur `deploy` |
| Code et configuration | `/opt/stc`, `.env` privé (600), projet Compose `stc` |
| Accès administrateur | `/opt/stc/.runtime/admin-credentials.txt` (600, sur le serveur uniquement) |
| Exposition | `127.0.0.1:18200`, vhost `/etc/nginx/sites-available/stc.sonutech.tech`, journal `/var/log/nginx/stc.access.log` sans paramètres de requête |
| Mode | Démonstration, paiement simulé ; aucun SMTP : e-mails conservés dans le conteneur, non envoyés |

Pour activer l’adresse définitive : dans le DNS Hostinger de `sonutech.tech`, créer `A stc → 72.61.193.220` (et `AAAA stc → 2a02:4780:28:7bf3::1`), attendre la propagation (`dig +short stc.sonutech.tech`), puis exécuter sur le serveur `sudo certbot --nginx -d stc.sonutech.tech`. Tant que ce certificat n’existe pas, `http://stc.sonutech.tech` redirige vers une adresse HTTPS sans certificat. Aucune sauvegarde planifiée n’est encore configurée sur ce serveur pour STC.

## Mise à jour d’une instance existante

Sauvegarder, appliquer les migrations, puis redémarrer :

```sh
# Local (arrêter npm run dev:all avec Ctrl+C au préalable)
python3 scripts/backup.py
backend/.venv/bin/python backend/manage.py migrate
npm run dev:all
# Docker de revue (migrer AVANT de démarrer le nouveau backend)
python3 scripts/backup.py --postgres
docker compose build
docker compose run --rm backend python manage.py migrate --noinput
docker compose up -d
```

## Mise à jour et retour arrière

Conserver la version des images déployées, une sauvegarde de la base et les migrations associées. Tester les migrations sur une copie avant déploiement. Ne pas lancer une migration inverse destructrice par défaut : revenir au code précédent seulement s’il reste compatible avec le schéma, sinon restaurer une sauvegarde pendant la maintenance.

## Limites de la livraison locale

Les tests locaux ne valident pas un domaine, un certificat externe, la délivrabilité d’un SMTP ou un paiement Stripe réel. Les commandes sont persistantes, mais le mode par défaut est une démonstration et ne doit pas être présenté comme un restaurant commercial ouvert. Les prix affichés sont TTC dans la démonstration ; les taux de TVA, la facturation et les obligations propres au restaurant doivent être renseignés avant exploitation commerciale.

## Limitation de la connexion administrateur

Les tentatives POST sur `/admin/login/` sont limitées avec un compteur en base, partagé entre les workers : 10 tentatives par fenêtre de 300 secondes hors développement, puis HTTP 429 avec `Retry-After`. Les réglages `ADMIN_LOGIN_LIMIT` et `ADMIN_LOGIN_WINDOW` permettent de l’adapter. En développement, la limite est plus haute pour la recette. Le proxy local ajoute une limite Nginx. `STC_TRUST_PROXY=1` n’est activé dans Docker que parce que le backend n’est pas exposé et que le proxy écrase `X-Real-IP`. Ne pas activer cette confiance sur un backend directement accessible.

## Paquet de livraison

Après compilation et validation, `python3 scripts/package.py` produit `artifacts/STC-livraison.zip` et son SHA-256. Le paquet inclut le code, les dépendances verrouillées, les fichiers compilés, les tests, la documentation et les exemples de configuration. Il exclut les secrets, la base locale, les e-mails privés, les médias téléversés et les identifiants administrateur. Ces données ne doivent pas être transmises comme du code source.
