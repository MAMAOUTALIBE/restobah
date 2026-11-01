# Livraison client — commandes réelles et règlement sur place

La cible du 2 novembre 2026 est un restaurant prenant de vraies commandes, avec règlement physique déclaré par un membre autorisé de l’équipe. La démonstration publique reste en démonstration tant que ses données et services ne sont pas remplacés et vérifiés. Les fichiers d’exemple ne sont pas une configuration client validée.

## Informations à obtenir du responsable

- Domaine final, identité et adresse du restaurant, téléphone et e-mail publics.
- Plats, photos utilisables, prix, compositions et allergènes validés ; horaires, fermetures, modes de service, délais, zones et frais réels.
- URLs HTTPS des mentions légales, de la politique de confidentialité et des conditions de commande préparées pour ce restaurant. Ne pas utiliser de lien privé comportant un jeton d’accès.
- Accès SMTP transmis par un canal privé, adresse d’expédition et destinataires des alertes d’équipe. Le responsable doit recevoir et contrôler un vrai message de confirmation et un lien de réinitialisation avant ouverture.
- Comptes nominatifs de l’équipe ; qui prépare les commandes et qui peut déclarer les encaissements/remboursements. Le compte partagé de démonstration doit être désactivé dans une base commerciale.
- Politique de conservation, copie extérieure chiffrée et responsable de restauration. L’applicabilité des obligations de caisse doit être clarifiée avec le client ; voir les [limites documentées du paiement sur place](audit-2026-11-01/05-onsite-architecture.md#limites-douverture).

Aucune identité ni aucun texte juridique n’est généré ou certifié par le logiciel. `STC_CONTENT_APPROVED=1` signifie que le responsable déclare avoir contrôlé les contenus ; ce drapeau n’en prouve ni l’exactitude ni la conformité juridique.

## Configuration privée

Partir de `.env.production.example`, conserver le fichier privé hors Git et remplacer ses marqueurs. Les réglages suivants préparent le fonctionnement choisi :

```dotenv
DJANGO_DEBUG=0
STC_DEMO_MODE=0
STC_PAYMENT_MODE=on_site
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STC_CONTACT_PHONE=
STC_CONTACT_EMAIL=
STC_LEGAL_NOTICE_URL=
STC_PRIVACY_URL=
STC_TERMS_URL=
STC_CONTENT_APPROVED=0
```

Laisser les coordonnées et documents vides tant qu’ils ne sont pas fournis. Le site masque ces liens vides ou invalides. Les URL de documents doivent utiliser HTTPS, sans mot de passe, domaine réservé d’exemple, hôte local ni port alternatif. Le client fournit ses valeurs réelles et confirme les contenus avant que le responsable passe le drapeau à `1`. Les cinq champs publics sont les seuls nouveaux champs exposés par `/api/restaurant/` ; les mots de passe SMTP, secrets Django et drapeaux de validation restent privés.

Renseigner aussi le domaine HTTPS dans `FRONTEND_URL`, `DJANGO_ALLOWED_HOSTS` et `DJANGO_CSRF_TRUSTED_ORIGINS`, puis SMTP, `DEFAULT_FROM_EMAIL` et `STC_ORDER_NOTIFICATION_EMAIL`. Ne mettre aucun secret dans `VITE_*`. Le retrait et la livraison restent configurés dans « Mon restaurant » ; une livraison sans zone reste fermée.

## Contrôle en lecture seule

Le contrôle ne crée ni restaurant, compte, commande, paiement, sauvegarde ou migration. `--smtp-check` ouvre une connexion chiffrée, s’authentifie et la ferme **sans envoyer d’e-mail**. `--check-urls` teste DNS, certificat et réponse HTTPS directe 2xx du site et des trois documents ; les redirections et les adresses privées sont refusées. Ces options produisent des échanges réseau réels lorsqu’elles sont utilisées ; les tests automatisés utilisent des doubles réseau.

Sur le VPS décrit dans OPERATIONS, après sauvegarde, construction et migrations de la version validée :

```sh
docker compose -p stc -f compose.yaml -f compose.vps.yaml run --rm -T \
  --user 0 --volume /opt/stc/backups:/audit-backups:ro \
  backend python manage.py check_production --json \
  --backup-directory /audit-backups --backup-project stc --backup-max-age 26 \
  --check-urls --smtp-check
```

Ce conteneur ponctuel utilise root pour **lire** le dossier privé de sauvegardes appartenant à l’utilisateur de déploiement. Le service web ordinaire conserve son utilisateur non privilégié et ne monte aucune sauvegarde. Adapter le chemin au dossier réel ; le montage est explicitement en lecture seule. L’outil de sauvegarde embarqué vérifie le manifeste, les empreintes et la fraîcheur sans Docker ni écriture. Voir [BACKUPS.md](BACKUPS.md) pour créer, planifier et restaurer les sauvegardes.

En environnement Python préparé, avec PostgreSQL jetable pour une recette :

```sh
backend/.venv/bin/python backend/manage.py check_production --json \
  --backup-directory /chemin/prive/vers/les/sauvegardes --backup-project stc
```

Le code de sortie est `0` sans blocage et `1` si la configuration est incomplète. Le JSON indique `configurationReady`, la liste `checks` et `externalChecks`. Il n’expose ni identités des comptes, coordonnées SMTP privées, secret de connexion, nom d’archive ni chemin privé. Sans les options réseau, les sondes correspondantes restent `not_checked`.

Un résultat favorable signifie **configuration vérifiée dans le périmètre annoncé**. Il ne prouve pas la réception des e-mails, la présence/restauration de la copie extérieure, la validation juridique ou l’acceptation commerciale. `emailDelivery` et `offsiteBackup` restent `not_checked`, même après une connexion SMTP réussie et une sauvegarde locale fraîche. `check --deploy` reste un contrôle complémentaire à exécuter dans l’environnement final.

## Recette avant ouverture

1. Conserver la sauvegarde complète et une image compatible avant migration ; migrer avant de lancer la nouvelle version. Aucune migration inverse automatique.
2. Vérifier sur mobile et ordinateur les coordonnées, horaires, liens des documents, plats et photos. Faire approuver les contenus par le responsable.
3. Créer un compte nominatif staff avec prénom/nom et, pour les opérateurs concernés, `view_order`, `change_order` et `record_onsite_payment`. Tester le refus avec un préparateur sans droit financier ; désactiver les accès de démonstration dans la base commerciale.
4. Sur une recette isolée, passer une commande « À emporter » puis une livraison si ce service est activé. Vérifier total, frais, commande confirmée et montant « À régler ». Préparer, déclarer l’encaissement depuis le CRM puis terminer ; contrôler le refus avant encaissement et la trace acteur/date. Tester le remboursement complet autorisé.
5. Contrôler une réception réelle de confirmation client, d’alerte équipe et de réinitialisation sur des adresses explicitement choisies pour cette recette. Une connexion SMTP seule ne suffit pas. Ne pas passer une commande de test non identifiée parmi les commandes commerciales.
6. Exécuter les contrôles de configuration et HTTPS finaux, vérifier la tâche de sauvegarde, transférer une copie extérieure chiffrée et restaurer une archive sur une instance isolée. Noter la date, la version et le résultat de chaque contrôle.
7. Autoriser les nouvelles commandes commerciales seulement après ces vérifications et la levée des dépendances client. Garder une surveillance des commandes et des erreurs d’e-mail le premier jour.

Le logiciel ne débite pas une carte, ne fournit pas un moyen physique de règlement, ne produit pas une facture et n’annonce aucune certification de caisse. La situation propre du client reste à valider. Une ancienne image ignorant `on_site` ne constitue pas un retour arrière métier pour une base ayant déjà reçu ces commandes ; utiliser une version compatible ou arrêter temporairement les nouvelles commandes pendant l’intervention.
