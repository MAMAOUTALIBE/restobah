# Sauvegardes et restauration STC

Ces commandes concernent uniquement le projet Compose **stc** dans `/opt/stc`, avec `compose.yaml` et `compose.vps.yaml`. Ne pas lancer Caddy sur le VPS partagé. Les fichiers privés et les sauvegardes ne sont pas des fichiers de livraison et ne doivent jamais être versionnés.

## Sauvegarde complète automatisable

Depuis `/opt/stc` :

```sh
python3 scripts/backup.py --postgres --full --project-name stc --compose-file compose.yaml --compose-file compose.vps.yaml --keep 7
python3 scripts/backup.py --project-name stc --check-freshness 26
```

La première commande crée dans `backups/` une archive `stc-full-stc-<date>-<identifiant>.tar.gz`, accompagnée de son SHA-256. Le dossier est privé (`0700`) et les fichiers sont `0600`. Un verrou refuse les exécutions concurrentes. Le contenu est construit et vérifié dans un dossier temporaire privé ; une erreur ne publie aucun fichier vide ou partiel et nettoie ce dossier.

| Fichier dans l’archive | Contenu |
|---|---|
| `database.dump` | Dump PostgreSQL au format custom ; lecture de son sommaire contrôlée. |
| `media.tar.gz` | Volume des photos, sous `media/`. |
| `container-private.tar.gz` | E-mails fichiers et runtime du backend, sous `emails/` et `runtime/`. |
| `host-private.tar.gz` | `.env` de l’hôte sous `environment.env`, et fichiers directs d’accès/marqueur de `.runtime/` sous `host-runtime/`. Aucun ancien dossier de déploiement n’est réarchivé. |
| `manifest.json` | Format, projet, date UTC, taille et SHA-256 de chacun des quatre fichiers. Aucune valeur de configuration ni coordonnée client. |

Les liens et fichiers spéciaux sont refusés. Les archives de fichiers sont contrôlées avant publication et pendant la vérification. Les anciens fichiers photos sont conservés par l’application : le dump en ligne peut donc retrouver les photos qu’il référence. Un fichier modifié pendant sa copie fait échouer la sauvegarde, à rejouer. Pour une copie strictement simultanée entre base, photos, e-mails et configuration, organiser une fenêtre sans écriture ; le dump utilise un instantané PostgreSQL, sans verrouiller toutes les écritures de l’application.

La rétention conserve **sept sauvegardes complètes valides de ce projet** par défaut. `--keep` ajuste ce nombre entre 1 et 365. Elle ne touche ni les sauvegardes ponctuelles de déploiement, ni les fichiers inconnus ou corrompus, ni les sauvegardes d’autres projets. Les fichiers invalides restent disponibles pour diagnostic et doivent être surveillés afin qu’ils n’occupent pas indéfiniment le disque.

`--check-freshness 26` ne contacte pas Docker : il exige un manifeste valide, des empreintes correctes et une sauvegarde terminée depuis moins de 26 heures. Il sort avec un code non nul si aucune sauvegarde valide n’est assez récente. La date du manifeste est utilisée, pas un simple changement de date du fichier. `--directory /chemin/prive` permet de choisir un autre dossier.

Vérifier une archive précise sans restaurer :

```sh
python3 scripts/backup.py --project-name stc --verify backups/ARCHIVE.tar.gz
```

Les anciennes commandes `python3 scripts/backup.py` (SQLite) et `python3 scripts/backup.py --postgres` (base seule) restent disponibles. Elles publient aussi un fichier final atomique après vérification ; elles ne remplacent pas la sauvegarde complète.

## Précontrôle ponctuel de mise en service

L’image backend contient une copie de `scripts/backup.py` pour vérifier une archive en lecture seule. La création des sauvegardes reste une commande de l’hôte. Les sauvegardes **ne sont jamais montées dans le service web public**.

Le contrôle de production s’exécute dans un conteneur temporaire, sans port publié, avec un montage en lecture seule. Le compte root de ce seul processus de contrôle lui permet de lire les archives `0600` appartenant à `deploy` ; il ne change pas le compte `stc` du backend public :

```sh
docker compose -p stc -f compose.yaml -f compose.vps.yaml run --rm -T --no-deps --user 0 --volume /opt/stc/backups:/audit-backups:ro backend python manage.py check_production --backup-directory /audit-backups --backup-project stc
```

Le contrôle doit refuser la mise en service si la sauvegarde ou les paramètres réels nécessaires ne sont pas valides. Un tel refus n’est pas contourné par un changement du mode démonstration. Ce conteneur est supprimé après la commande et ne sert aucune requête utilisateur.

## Stockage privé persistant et première mise à jour

`compose.yaml` monte `stc-runtime` et `stc-emails` seulement dans le backend, sous `/app/.runtime` et `/app/.private-emails`. Le frontend ne voit que les médias en lecture seule. Les overrides VPS et Caddy héritent de ces volumes. À la création, Docker reprend les répertoires `0700` et leur propriétaire `10001:10001` depuis l’image.

Avant le premier redémarrage d’une ancienne installation sans ces volumes, sauvegarder le contenu existant de ces deux répertoires depuis l’ancien conteneur, ainsi que `.env`, les fichiers d’accès de l’hôte, la base et les médias. Après la création des volumes, recopier les seuls fichiers privés sauvegardés dans les chemins correspondants et vérifier propriétaire `10001:10001`, dossiers `0700` et fichiers `0600`. Ne pas remplacer aveuglément les volumes par un dossier vide et ne pas lancer `down --volumes` sur l’instance active. Les scripts de bascule supervisés conservent déjà les anciens fichiers ; ils doivent garder cette étape pour la première mise à jour.

## Installer le planning après validation de la version

Les unités fournies sont des **modèles non installés automatiquement**. Elles s’exécutent comme `deploy` et ciblent uniquement `/opt/stc`/le projet `stc`. Adapter les chemins et le compte si l’installation du client diffère. Le compte doit pouvoir utiliser le Docker de cette application.

Après une première sauvegarde complète réussie et son contrôle :

```sh
sudo install -m 644 deploy/systemd/stc-backup.service /etc/systemd/system/stc-backup.service
sudo install -m 644 deploy/systemd/stc-backup.timer /etc/systemd/system/stc-backup.timer
sudo install -m 644 deploy/systemd/stc-backup-check.service /etc/systemd/system/stc-backup-check.service
sudo install -m 644 deploy/systemd/stc-backup-check.timer /etc/systemd/system/stc-backup-check.timer
sudo systemctl daemon-reload
sudo systemctl start stc-backup.service
sudo systemctl start stc-backup-check.service
sudo systemctl enable --now stc-backup.timer stc-backup-check.timer
systemctl list-timers stc-backup.timer stc-backup-check.timer
```

La sauvegarde tourne vers **03 h 15, heure de Paris**, avec un décalage aléatoire maximal de cinq minutes. Le contrôle tourne chaque heure et après démarrage. Consulter `journalctl -u stc-backup.service -u stc-backup-check.service` et les états `systemctl status`. Un échec reste non nul et apparaît dans l’état de l’unité ; une notification externe nécessite un outil de supervision configuré, aucune réception d’alerte n’est présumée.

Retirer uniquement ces plannings, si nécessaire : `sudo systemctl disable --now stc-backup.timer stc-backup-check.timer`. Aucune autre unité de l’hôte ne doit être modifiée.

## Restauration contrôlée

Tester d’abord la restauration dans une pile **isolée**, jamais en remplaçant les données du client pour une simple vérification. Une restauration de la base active remplace les données actuelles et exige une fenêtre de maintenance et une sauvegarde de l’état courant.

1. Placer l’archive dans un répertoire privé, lui donner le mode `0600`, exécuter `--verify`, puis extraire son contenu dans un nouveau dossier `0700` avec un umask `077` et sans reprendre les propriétaires du tar. Ne jamais extraire un contenu non vérifié directement à la racine du système.
2. Créer une base cible isolée, puis y exécuter `pg_restore --no-owner --exit-on-error`. Sur une instance active en maintenance, arrêter les écritures et utiliser explicitement la procédure de remplacement décrite dans [OPERATIONS.md](OPERATIONS.md#restauration), après sauvegarde de l’état courant.
3. Extraire les trois archives de fichiers dans le dossier privé de travail. **Les archives normalisent tous les dossiers à `0700` et tous les fichiers à `0600`, y compris les photos** : l’extraction de travail reste ainsi privée. `media/` contient le contenu à remettre dans `/app/media` ; `emails/` et `runtime/` correspondent à `/app/.private-emails` et `/app/.runtime`. Copier leurs contenus dans les volumes du backend de la pile cible, sans reprendre le propriétaire du tar. Avant de servir les photos, remettre **uniquement les médias publics** à `0755` pour les dossiers et `0644` pour les fichiers, avec propriétaire `10001:10001`. Conserver les dossiers e-mails/runtime à `0700` et leurs fichiers à `0600`, avec le même propriétaire. Sans cette distinction, le worker nginx (`UID 101` sur l’image VPS) ne peut pas lire les photos restaurées.
4. Examiner séparément `environment.env` et `host-runtime/`. Ils contiennent des secrets : ne pas les afficher, les envoyer ou les rendre publics. Restaurer uniquement la configuration cohérente avec la base et l’environnement cible, avec fichiers `0600`.
5. Démarrer la pile cible, contrôler migrations, connexion, catalogue, photos, montant et statut des commandes. Comparer les comptages attendus. Les secrets et les chemins d’un autre environnement ne doivent pas écraser la configuration active par défaut.
6. Supprimer la copie privée temporaire après vérification. Conserver l’archive d’origine selon la rétention convenue.

Exemple de remise des droits, **depuis le dossier de la pile cible isolée**, une fois les contenus copiés. `stc-restauration-test` doit être le nom du projet cible, avec ses propres volumes ; vérifier ce nom avant exécution. Ce conteneur temporaire ne publie pas de port. Pour une restauration réelle, employer le projet actif seulement pendant la maintenance autorisée.

```sh
docker compose -p stc-restauration-test -f compose.yaml -f compose.vps.yaml run --rm -T --no-deps --user 0 backend sh -eu -c '
  chown -R 10001:10001 /app/media /app/.private-emails /app/.runtime
  find /app/media -type d -exec chmod 0755 {} +
  find /app/media -type f -exec chmod 0644 {} +
  find /app/.private-emails /app/.runtime -type d -exec chmod 0700 {} +
  find /app/.private-emails /app/.runtime -type f -exec chmod 0600 {} +
'
```

Contrôler ensuite qu’un processus du backend (`10001:10001`) peut lire les photos et écrire dans les trois volumes ; contrôler qu’un worker du frontend peut lire une photo restaurée, mais pas les fichiers privés. Charger aussi l’URL d’une photo par le serveur web cible : une extraction réussie et un dump restauré ne suffisent pas à valider les droits de service. Ne jamais appliquer `0755`/`0644` à la racine `/app`, aux sauvegardes ou aux fichiers de configuration privés.

## Copie chiffrée hors du serveur

Une sauvegarde locale ne protège pas contre la perte de l’hôte. Définir avec le client une destination extérieure, une rétention et une clé de chiffrement détenue séparément ; copier les archives **chiffrées** et contrôler leur réception. Aucun secret de sauvegarde ni destination externe n’est inventé par le logiciel. Les modèles ci-dessus ne prétendent pas qu’une copie hors serveur existe. Rejouer périodiquement une restauration de cette copie extérieure dans une pile isolée.
