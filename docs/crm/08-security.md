# CRM STC — audit sécurité préalable

Audit du 1er novembre 2026, rôle spécialisé sécurité. Cette première passe est une revue du code et de sources officielles ; elle ne constitue pas encore une validation fonctionnelle du futur CRM. Aucun code produit, secret, compte ou donnée utilisateur n’a été modifié.

## Périmètre et constat

Le CRM sera une interface Django sous `/crm/`, avec quatre rubriques, des formulaires natifs et une session de l’équipe. Les fondations existantes sont réutilisables : middleware CSRF, sessions Django, permissions de modèles, `ModelForm`, transactions, transitions de commandes et vérification des webhooks Stripe.

Fichiers lus : `config/settings.py`, `shop/middleware.py`, `shop/views.py`, `shop/services.py`, `shop/models.py`, `shop/payments.py`, `shop/admin.py`, tests d’authentification/fiabilité existants et `docs/crm/02-architecture.md`.

## Corrections et contrôles P0 à intégrer

| Sujet | État observé et preuve | Mesure attendue pour le CRM |
|---|---|---|
| Connexion gérant | Le limiteur partagé couvre uniquement les POST `/admin/login` (`middleware.py:16`). | Couvrir aussi `/crm/connexion/`, avec le même compteur par adresse hachée et un refus 429 temporaire. Rejeter comptes inactifs ou non staff ; conserver des erreurs de connexion non discriminantes. |
| Autorisation | Les API courantes sont publiques/client ; aucun décorateur CRM n’existe encore (`views.py`). | Chaque page, fragment et mutation vérifie utilisateur authentifié, actif, staff et permission de l’opération. Cacher un bouton ne remplace pas ce contrôle. |
| Accès aux commandes | `services.authorized_order():66` considère tout `is_staff` comme propriétaire ; `views.OrderView` réutilise ce raccourci pour inclure les coordonnées. | Remplacer l’accès staff global par un droit explicite `shop.view_order`. Conserver l’accès du véritable propriétaire et le suivi invité par jeton ; ne jamais ajouter les coordonnées au simple suivi invité. |
| Photos | `Product.photo` est un `ImageField`; le test existant rejette un faux PNG, mais aucun plafond métier/nom aléatoire/réencodage n’est présent pour un formulaire CRM (`models.py`, `test_reliability.py:310`). | Accepter uniquement des raster JPEG/PNG/WebP réellement décodables ; refuser SVG/GIF/autres formats, fichiers invalides et images trop lourdes/grandes. Limite proposée : 5 Mio et plafond explicite de dimensions/pixels. Réencoder en format autorisé, retirer les métadonnées inutiles et générer un nom UUID côté serveur. |
| CSRF et méthodes | `CsrfViewMiddleware` est actif ; `ProtectedView` protège déjà les POST API (`settings.py:24`, `views.py:24`). | Aucune exemption CRM. Toutes mutations, y compris déconnexion/disponibilité/statut, sont POST avec `{% csrf_token %}` ; les GET restent sans mutation. Le JS envoie `X-CSRFToken` et ne transforme pas une erreur/session expirée en réussite. |
| Données privées | Les futures pages contiendront noms/téléphones/adresses de clients ; aucune politique CRM n’existe encore. | `never_cache` sur pages privées, fragments et réponses de connexion. Ne pas rendre les jetons invités, secrets ou données de paiement dans les attributs HTML/JSON ni dans des journaux client. |
| Écriture ciblée | Les modèles exposent aussi des champs techniques et des permissions de comptes. | Listes explicites de champs `ModelForm`. Ignorer/rejeter les champs ajoutés au POST : `is_staff`, prix/total/paiement de commande, restaurant d’un horaire, promotion technique non exposée. |

Ces constats P0 sont fondés sur la source ; les scénarios ci-dessous doivent confirmer leur correction avant livraison. L’existence d’un `ImageField` ne permet pas d’affirmer que tout contenu téléversé est sans risque.

## Matrice minimale de permissions

La session doit aussi appartenir à un utilisateur actif et staff. Un client connecté ou un staff sans permission ne reçoit pas les données protégées.

| Opération | Permission attendue |
|---|---|
| Voir les plats | `shop.view_product` |
| Ajouter un plat | `shop.add_product` ; lecture des catégories pour le choix |
| Modifier prix/photo/recette/disponibilité | `shop.change_product` |
| Voir commandes, coordonnées, indicateurs de commandes | `shop.view_order` |
| Faire avancer ou annuler une commande | `shop.change_order`, avec les règles métier existantes |
| Voir les réglages | `shop.view_restaurant` |
| Modifier les réglages | `shop.change_restaurant` |
| Ajouter/modifier/supprimer des créneaux ou fermetures | Droits `OpeningHour`/`Closure` correspondants, ou politique gérant explicitement documentée et testée ; jamais une autorisation implicite par `is_staff` seul |

L’accueil ne doit pas dévoiler chiffre d’affaires, nombre de commandes ou coordonnées à un membre sans `view_order`. Une lecture seule ne doit pas autoriser une mutation directe en fabriquant un POST. Le compte superutilisateur conserve ses permissions natives. Un groupe « Gérant STC » peut réunir les droits nécessaires sans donner la gestion des utilisateurs ou des permissions.

## Connexion, navigation et rendu

- La cible `next` doit être vérifiée par `url_has_allowed_host_and_scheme` avec le domaine courant et HTTPS lorsque requis ; à défaut, retour vers l’accueil CRM. Tester URL externe et URL commençant par `//`.
- Une page refusée à un utilisateur connecté retourne une réponse 403 lisible, sans boucle de redirection. La connexion ne doit jamais modifier `is_staff` ni créer automatiquement un gérant.
- Conserver l’échappement des templates pour noms/descriptions/notes client ; éviter `safe`, `mark_safe` et la construction HTML à partir de saisies. Les valeurs de formulaire et attributs restent entre guillemets.
- La vue d’échec CSRF actuelle renvoie du JSON (`views.py:25`). Une réponse HTML dédiée au CRM peut proposer de revenir à la connexion tout en gardant le statut 403 ; le contrat JSON des API doit rester inchangé.
- Le rafraîchissement progressif n’affiche pas un formulaire de connexion comme s’il était une liste de commandes : détecter redirection, URL finale et statut de réponse. Arrêter/reprendre proprement sans effacer une saisie ouverte.

## Transactions et paiements à préserver

`Order.check_transition()` impose l’ordre des statuts et le paiement confirmé avant préparation. `Order.transition()` crée l’historique. Le CRM doit verrouiller la commande, contrôler le statut attendu et appeler ces fonctions ; il ne doit pas affecter directement `status`, `total`, `payment_status` ou les lignes.

Pour une annulation Stripe en attente, appeler `payments.release_checkout()` avant la transition, gérer son refus et ne pas annuler silencieusement si Stripe est indisponible ou si le paiement est déjà terminé. Une commande payée ne s’annule pas avant le remboursement confirmé. Ne pas assouplir le contrôle des clés test, des signatures, des montants/devise ou de l’idempotence du webhook (`payments.py:143–165`, `settings.py:83–93`).

`PaymentView` utilise aussi `authorized_order()` : en durcissant ce dernier, vérifier que les vrais propriétaires et jetons de paiement invités continuent à fonctionner, et qu’un membre sans droit de consultation ne gagne pas un accès paiement à une commande d’autrui.

## Recette sécurité à exécuter sur base de test

| Famille | Scénarios et résultat attendu |
|---|---|
| Accès | Anonyme redirigé connexion ; client connecté et staff sans droit refusés ; lecteur autorisé en GET mais POST refusé ; superutilisateur/gérant autorisé. Vérifier aussi fragments et URL d’édition directe. |
| Connexion | Mot de passe faux, non-staff, inactif, adresse normalisée ; tentatives répétées donnent 429 ; retour `next` externe neutralisé ; déconnexion POST et GET refusé. |
| CSRF | Client Django `enforce_csrf_checks=True` : chaque mutation sans jeton ou avec jeton incorrect donne 403 et ne change aucune donnée. |
| Commandes/PII | Staff sans `view_order` ne voit pas une commande étrangère via API ; propriétaire et gérant autorisés ; jeton invité autorise le suivi mais aucune coordonnée client. Jeton incorrect et référence inconnue ont le même refus. |
| Photos | Vraies images autorisées ; faux fichier à extension PNG, SVG, image corrompue, format non autorisé, fichier >5 Mio et dimensions hors plafond refusés. Nom `../../photo.php.png` remplacé par un nom généré. Le résultat stocké se redécode et n’inclut pas les données ajoutées après l’image. |
| Injection | Nom de plat et note client contenant balises/attributs rendus comme texte ; aucun script exécuté. Champs cachés ajoutés au POST ne modifient ni permissions, ni total, ni paiement, ni objet appartenant à une autre portée. |
| Méthodes/persistance | GET des endpoints de mutation sans effet ; erreurs gardent les anciennes valeurs ; réessai de disponibilité ne produit pas une inversion accidentelle ; modification rechargée persiste. |
| Commandes concurrentes | Ancien statut soumis après une autre transition : message de conflit, pas de retour arrière ni doublon d’historique ; annulation Stripe refusée sans session réellement fermée. |
| Réponses privées | Pages/fragments avec `Cache-Control` interdisant le cache partagé, pas de jeton/secret dans HTML, session expirée identifiée par le JS. |

Les tests du CRM doivent utiliser l’instance temporaire de `scripts/e2e.py` et les bases de test Django. Ne pas remplir/effacer la base locale ni imprimer les accès de `.runtime`.

## Défenses existantes et limites d’exploitation

Vérifié dans `settings.py:50–61` : session HttpOnly, SameSite Lax, cookies Secure et redirection HTTPS lorsque DEBUG est désactivé, HSTS et nosniff, cadrage interdit. Le proxy média ajoute nosniff et une CSP restrictive. Ces réglages doivent être conservés ; leur présence dans la source n’est pas une preuve de déploiement HTTPS effectif.

La présente mission ne constitue pas un audit d’infrastructure en production, un scan complet des dépendances ou une validation PCI. Aucun paiement réel n’est activé. L’antivirus et l’isolation du processeur image ne sont pas annoncés comme présents. Les traitements raster bornés et le service média sûr réduisent le risque, sans promesse absolue de fichiers inoffensifs.

## Sources primaires consultées

- [Django 5.2 — authentification et permissions](https://docs.djangoproject.com/en/5.2/topics/auth/default/#the-permission-required-decorator) : distinction entre connexion, statut staff et permission d’une opération.
- [Django 5.2 — sécurité et contenus envoyés](https://docs.djangoproject.com/en/5.2/topics/security/#user-uploaded-content) : limites d’ImageField, restriction des tailles et service sûr des fichiers.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) : autorisation, liste de formats, contenu réel, nom généré, bornes et réencodage.

## Contrôles réellement effectués

Lecture des fichiers cités, recherche des frontières staff/CSRF/photos et consultation des sources primaires. `git diff --check` réussi après création du rapport. Aucun test de sécurité fonctionnel ni mutation de la base n’est revendiqué à cette étape. Une seconde revue de l’implémentation et les résultats QA restent requis.
