# Comptes clients — préparation de l’envoi d’e-mails

Le fournisseur n’est pas encore choisi. Cette livraison prépare la configuration et les contrôles ; elle n’active aucun service et ne prouve aucune réception réelle.

## Comportement sans fournisseur

L’inscription, la connexion, le profil et la commande sans compte fonctionnent sans SMTP. En production, la récupération du mot de passe est annoncée indisponible si la configuration d’envoi manque. Un échec de lecture de cette disponibilité propose **Réessayer**. Aucun champ ni bouton ne prétend alors envoyer un lien.

Le backend conserve une réponse générique aux demandes de récupération pour protéger l’existence des comptes. Un fichier de développement privé ne distribue pas d’e-mails aux clients. Ne pas exposer ce répertoire sur le serveur web.

## Configuration privée à renseigner après choix du fournisseur

Utiliser les valeurs réellement fournies par le service dans l’environnement privé du serveur, jamais dans Git, un ticket ou le chat :

- `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` et `DEFAULT_FROM_EMAIL` : valeurs du fournisseur et expéditeur autorisé.
- STARTTLS : `EMAIL_PORT=587`, `EMAIL_USE_TLS=1`, `EMAIL_USE_SSL=0`.
- Ou TLS dès la connexion : `EMAIL_PORT=465`, `EMAIL_USE_TLS=0`, `EMAIL_USE_SSL=1`.
- `FRONTEND_URL` : origine HTTPS publique réellement utilisée, sans chemin, paramètres ni identifiants. Par exemple, l’instance de démonstration actuelle utilise `https://stc.srv2086522.hstgr.cloud`. Remplacer par le domaine du client lorsqu’il est prêt.

Un seul des modes TLS/SSL doit être activé. Adapter les ports aux instructions du fournisseur. Les modèles `.env.example` et `.env.production.example` ne sont pas des identifiants utilisables.

Vérifier aussi `DJANGO_ALLOWED_HOSTS` et `DJANGO_CSRF_TRUSTED_ORIGINS` lors d’un changement de domaine. Une ancienne valeur `FRONTEND_URL` qui ne résout plus doit être remplacée dans la configuration privée avant d’activer l’envoi.

## Contrôles sans envoi

Depuis le backend et son environnement configuré :

```sh
python manage.py check_account_delivery --json
python manage.py check_account_delivery --json --check-url --smtp-check
```

La première commande contrôle les valeurs. La seconde teste aussi le DNS, le certificat, la réponse HTTPS directe et la connexion SMTP authentifiée. Elle n’envoie aucun message et n’écrit aucune donnée métier. Le code de sortie est `1` si un contrôle demandé échoue. Le rapport ne contient pas les identifiants ni les exceptions du fournisseur.

Le champ `passwordResetAvailable` de `/api/auth/capabilities/` indique seulement que la configuration permet de proposer la récupération ; il ne réalise pas de connexion SMTP à chaque visite.

## Recette après activation

Sur une adresse de recette choisie, demander un lien depuis **Mot de passe oublié**, vérifier sa réception, son domaine et son ouverture sur mobile. Changer le mot de passe, vérifier que l’ancien mot de passe est refusé et que le lien ne fonctionne pas deux fois. Contrôler ensuite les confirmations de commande et les notifications d’équipe si elles sont configurées. Ces vérifications de réception restent à faire lorsqu’un fournisseur sera disponible.

L’inscription ne comporte pas encore de validation de l’adresse par e-mail. L’e-mail du profil reste donc en lecture seule ; aucun rapprochement automatique des anciennes commandes invitées n’est réalisé.

## Coupure réseau pendant une action sur le compte

Si une réponse de connexion ou d’inscription est perdue, le site vérifie le compte auprès du serveur avant de reprendre le panier. Si la vérification ne passe pas, **Réessayer** ou une nouvelle connexion permet de la reprendre ; les coordonnées du panier restent en mémoire dans l’onglet. Un compte différent de celui saisi ne valide pas automatiquement cette reprise.

Après une suppression dont la réponse est perdue, le site indique que le résultat n’a pas pu être confirmé. Il vérifie la session sans recommencer la suppression. Une session fermée ne suffit pas à prouver que le compte a été supprimé.

## Migration et accès CRM

La migration `0007_account_profile` ajoute le téléphone facultatif du compte et le droit `shop.view_customer`. Exécuter les migrations avec la procédure habituelle de sauvegarde et de livraison, sans réinitialiser ni réensemencer la base existante. La colonne possède une valeur par défaut côté base pour préserver les insertions d’une ancienne version pendant le remplacement du backend.

Pour la rubrique **Mon restaurant → Clients**, attribuer explicitement à chaque membre du personnel autorisé `shop.view_customer` et `shop.view_order`. Aucun compte existant ne reçoit automatiquement ces nouveaux droits.
