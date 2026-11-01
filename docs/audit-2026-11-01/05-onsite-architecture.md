# Paiement sur place — architecture de livraison

Rôle : architecte logiciel. Référence lue : `0c5c588`. Date : 1er novembre 2026. Ce document définit le lot C du plan ; il ne revendique ni implémentation ni validation fonctionnelle.

## Décisions de périmètre

Le choix confirmé est **commandes réelles, paiement sur place**. L’application enregistre la déclaration d’un règlement effectué physiquement par l’équipe. Elle ne débite aucun moyen de paiement, ne remplace pas une caisse fiscale et ne produit pas une facture. Les remboursements partiels et les changements de moyen de paiement d’une commande existante sont exclus de ce lot.

Le retrait et la livraison restent gouvernés par les réglages existants. Pour une livraison activée par le restaurant, le texte indique **« À régler à la livraison »** ; pour le retrait, **« À régler au restaurant »**. Ne pas promettre un mode de règlement physique particulier sans information du client.

## Modèle et invariants

### Origine du paiement

Ajouter `Order.payment_method`, `CharField` non éditable, avec trois valeurs : `simulation`, `stripe`, `on_site`. Le service de création le fixe depuis le réglage serveur après validation du `paymentMethod` fourni. L’origine ne change jamais après la création, même si le réglage général change.

Le champ doit être absent des formulaires publics et CRM de modification, et en lecture seule dans l’administration technique. Toute méthode applicative qui modifierait l’origine d’une commande existante doit être refusée. Une migration contrôlée reste autorisée à renseigner les anciennes lignes.

### État financier

Ajouter uniquement `due` aux choix de `Order.payment_status` : **« À régler sur place »**. Les états `paid`, `refunded` et `cancelled` existants sont réutilisés ; `payment_method` permet de distinguer leur origine. `simulated` reste réservé à la simulation, `pending`/`failed` au parcours Stripe.

| Origine | Création | Préparation et prête | Terminer | Annuler |
|---|---|---|---|---|
| Simulation | `confirmed` / `simulated` | Règles existantes | Règles existantes | Règles existantes |
| Stripe | `pending_payment` / `pending` | Après webhook payé | Après paiement | Fermeture de session/remboursement selon les règles existantes |
| Sur place | `confirmed` / `due` | Autorisées avant règlement | Après encaissement enregistré (`paid`) | Possible avant règlement ; après règlement, remboursement complet enregistré d’abord |

Une commande sur place annulée avant règlement passe à `payment_status=cancelled` : elle ne demeure pas présentée comme une somme à encaisser. Une commande remboursée ne peut plus avancer en préparation ou être terminée comme payée.

### Trace d’encaissement

Ajouter `OnSitePaymentEvent` :

- `order`, FK protégée vers la commande ;
- `kind`, choix `collected` ou `refunded` ;
- `amount`, décimal fixé au total de la commande par le serveur ;
- `actor`, compte de l’équipe ayant enregistré l’opération ;
- `created_at`, horodatage serveur.

Une contrainte unique `(order, kind)` autorise au maximum un encaissement et un remboursement complet. Une contrainte impose un montant non négatif ; les commandes gratuites déjà permises par le catalogue ne doivent pas casser le parcours. Les événements ne sont ni ajoutables librement, ni modifiables, ni supprimables dans l’administration. Protéger la suppression d’un acteur référencé ; un compte d’équipe peut être désactivé sans perdre la trace.

Ce registre est distinct de `OrderHistory`, réservé à l’état de préparation. Les détails CRM montrent les événements financiers avec leur acteur et leur date ; l’API client ne divulgue aucun identifiant ou nom d’employé.

## Services et autorisations

Ajouter la permission `shop.record_onsite_payment` sur `Order`. Les deux opérations financières exigent une session active, `is_staff`, `view_order`, `change_order` et cette permission dédiée. Un compte qui ne fait que préparer les commandes ne reçoit pas automatiquement le droit d’enregistrer leur règlement.

Routes CRM POST proposées :

- `/crm/commandes/<id>/encaissement/` : **« Enregistrer l’encaissement »** ;
- `/crm/commandes/<id>/remboursement/` : **« Confirmer le remboursement »**, ou **« Confirmer le remboursement et annuler »** pour une commande active.

Chaque action conserve CSRF, réponses privées, contexte de recherche/pagination du lot B et confirmation explicite. Aucun montant, acteur, origine ou horodatage fourni par le navigateur n’est accepté. Un champ d’état attendu permet de présenter une erreur de concurrence claire ; l’autorité reste la ligne verrouillée en base.

Dans `transaction.atomic()`, recharger la commande via `select_for_update()` avant toute décision :

1. Vérifier l’origine `on_site` et l’état courant.
2. Encaisser seulement une commande active `confirmed`, `preparing` ou `ready` avec `due` ; créer l’événement au montant `order.total` et passer à `paid` dans la même transaction.
3. Répéter l’action lorsque le paiement est déjà `paid` et que son événement existe ne crée ni second événement ni second changement. Un ancien encaissement rejoué après remboursement doit produire un conflit clair, sans remettre la commande à `paid`.
4. Rembourser seulement un encaissement sur place précédemment enregistré. Créer l’événement complet et passer à `refunded`. Annuler atomiquement la commande si elle est encore active, comme le fait déjà le traitement de remboursement Stripe ; une commande terminée conserve son état de service et affiche le remboursement.
5. Un second remboursement identique est sans effet. Une incohérence historique, un mauvais état ou une origine différente donne un refus sans écriture partielle.

Les méthodes communes de transition doivent être utilisées par le CRM et l’administration. `PaymentView`, `release_checkout` et les webhooks doivent refuser ou ignorer explicitement les commandes dont l’origine n’est pas Stripe : changer le mode général ne doit jamais transformer une commande sur place en session Stripe.

## Création, interface et notifications

- Accepter `STC_PAYMENT_MODE=on_site` ; autoriser `DEMO_MODE=0` avec ce mode. Conserver le refus de la simulation hors démonstration et des clés Stripe réelles.
- Étendre `OrderInputSerializer` et les types TypeScript. Le serveur crée immédiatement la commande sur place en `confirmed`/`due`, calcule les montants et garde l’idempotence existante.
- La confirmation client et l’alerte équipe partent après commit lors de la création, une seule fois. Le texte annonce le règlement physique à effectuer, jamais un paiement Stripe confirmé. Un échec SMTP garde la commande ; son absence de configuration reste un blocage de mise en service des notifications.
- L’API ajoute `paymentMethod` en lecture. Le statut public devient **« À régler au restaurant »**, **« À régler à la livraison »**, **« Réglé sur place »** ou **« Remboursé sur place »** selon l’origine et l’état. Aucun bouton Stripe n’apparaît pour une somme due sur place.
- Le panier affiche un bouton **« Commander et régler au restaurant »**, ou **« Commander et régler à la livraison »**, avec le total clairement visible et une indication du règlement physique. Le libellé exprime l’engagement de paiement même si le règlement intervient ensuite ; un simple « Confirmer » ne suffit pas à le communiquer. Les textes de simulation restent conditionnés au vrai mode démonstration. Cette décision suit la présentation officielle française de l’obligation de paiement lors d’un achat à distance : [Service Public — moyens et date de paiement](https://www.service-public.gouv.fr/particuliers/vosdroits/F10486).
- Dans le CRM, `Préparer` et `Marquer prête` restent disponibles pour `on_site`/`due`. `Terminer` attend l’encaissement ; montrer un message utile plutôt qu’un bouton disparu sans explication. Le bouton financier dépend de la permission dédiée.
- Ne pas présenter l’indicateur de commandes du jour comme un livre de caisse. Les sommes dues ne comptent pas comme encaissées ; les événements constituent la trace des règlements, sans prétention de conformité fiscale.

## Migration et préservation

Migration additive recommandée : champ temporairement nullable, remplissage contrôlé des anciennes commandes, puis champ obligatoire ; ajout du registre et de ses contraintes/permission.

L’ancienne application n’a que deux origines : `payment_status=simulated` correspond à `simulation`, les autres états historiques valides correspondent à `stripe`. Une annulation simulée conserve déjà son statut financier `simulated`. Vérifier les états inconnus et les contradictions avec une relation `Payment` existante ; arrêter avec un diagnostic au lieu de requalifier silencieusement une ligne ambiguë.

Ne modifier ni identifiants, montants, prix historiques, clients, statuts de préparation, états financiers existants, jetons, lignes ni historique. Aucun `seed_demo` lors de la mise à jour. Les fixtures qui créent directement des commandes Stripe doivent renseigner leur nouvelle origine ; les tests de migration partent réellement du schéma précédent.

Le contrôle de déploiement actuel compare toutes les valeurs des modèles avant/après. Il faut conserver, **avant migration**, la liste des champs de chaque modèle protégé puis calculer les empreintes après migration sur ces mêmes champs. Sinon, le simple ajout de `payment_method` provoquera un faux échec de préservation. Vérifier séparément le remplissage du nouveau champ et l’absence d’événements financiers créés par la migration. Sauvegarde et restauration sont contrôlées sur une base isolée ; aucun retour de schéma destructeur automatique.

Le champ obligatoire conserve un défaut SQL durable `simulation`, en plus du défaut Python, afin que le vrai modèle historique `0005` puisse encore insérer une commande depuis l’ancienne image `0c5c588`. Ce périmètre de compatibilité est limité au repli de la démonstration actuelle, avec `STC_DEMO_MODE=1` et `STC_PAYMENT_MODE=simulation` conservés. Le test de migration exécute réellement cet INSERT historique après `0006` et vérifie les valeurs enregistrées ; les commandes existantes ne sont pas requalifiées.

**Garde de repli :** une instance recevant des commandes réelles sur place exige une image de secours comprenant `payment_method`, `on_site`, `due` et le registre financier. Si aucune image compatible n’est disponible, maintenir le service en maintenance plutôt que relancer un ancien binaire. Le défaut SQL `simulation` ne rend pas un ancien binaire Stripe ou sur place compatible et ne doit jamais servir à reclasser une commande réelle. Toute opération de repli conserve la base et les événements, annonce l’indisponibilité temporaire des actions financières et ne lance jamais de migration inverse supprimant ces données.

## Fichiers attendus et ordre de réalisation

1. `models.py`, nouvelle migration, service financier dédié et tests serveur/migration.
2. `services.py`, `serializers.py`, `payments.py`, `notifications.py`, `settings.py`, administration : intégration et protection des anciens parcours.
3. `crm_views.py`, `crm_urls.py`, formulaire/actions et détail des commandes : encaissement/remboursement autorisés.
4. `types.ts`, `Cart.tsx`, `Orders.tsx`, éventuels textes FAQ : libellés exacts et aucune fausse simulation.
5. Exemples `.env`, contrat API, guide gérant et contrôles de déploiement/préparation commerciale.

## Recette requise avant acceptation

| Famille | Contrôles minimaux |
|---|---|
| Création | Invité et compte, retrait et livraison configurée, horaires réels/fermeture/pause, quantités/options/prix/frais recalculés, nouvelle origine persistée, confirmation unique, rejeu et concurrence idempotents. |
| Droits | Anonyme, client, staff lecteur, préparateur sans permission financière, gérant autorisé, compte désactivé ; POST sans CSRF ; champs de paiement/acteur/montant falsifiés. |
| Encaissement | Somme exacte, trace acteur/date, double clic/rejeu et deux opérateurs ; impossibilité de terminer avant règlement ; terminé après encaissement. |
| Remboursement | Refus sans encaissement ou sur Stripe/simulation ; événement complet unique ; annulation d’une commande active ; conservation du service terminé et de la trace. |
| Compatibilité | Tous les tests Stripe/simulation existants ; webhooks sans effet sur une commande sur place ; notifications et API sans fausse mention de carte ou de paiement effectué. |
| Migration | Schéma précédent vers nouveau sur SQLite et PostgreSQL ; toutes les anciennes valeurs protégées identiques ; origines correctement remplies, registre vide, compteurs automatiques fonctionnels. |
| Navigateur | Commande réelle jetable de bout en bout, total et statut identiques entre client et CRM ; encaissement, finalisation, remboursement ; mobile et ordinateur, clavier, erreurs et absence de doublon. |

## Limites d’ouverture

Ce lot ne fournit pas les coordonnées, horaires, zones, allergènes, textes légaux validés, domaine et accès SMTP du client encore demandés. Il ne transforme pas la démonstration publique en service commercial sans ces données et les contrôles de préparation. Les comptes de démonstration partagés ne doivent pas garder leurs droits d’écriture dans la future base commerciale ; les comptes nominatifs doivent recevoir explicitement les permissions adaptées.

La juridiction et la situation TVA du client restent inconnues. **Si le restaurant relève des règles françaises applicables**, la mémorisation des règlements peut faire entrer cette fonctionnalité dans le champ des logiciels ou systèmes de caisse, selon sa situation et les exceptions prévues. La doctrine fiscale publiée le 25 mars 2026 précise ce champ et les exigences de sécurisation. Le fait d’écrire « ne remplace pas une caisse » ne constitue aucune dérogation juridique. Aucun certificat, attestation de conformité ou statut de caisse certifiée n’est annoncé ni généré par cette livraison. L’applicabilité doit être clarifiée avec le client avant l’ouverture commerciale ; elle ne bloque pas la conception et la recette sur données jetables. [BOFiP — BOI-TVA-DECLA-30-10-30, version du 25 mars 2026](https://bofip.impots.gouv.fr/bofip/10691-PGP.html/identifiant=BOI-TVA-DECLA-30-10-30-20260325).

## Preuve de ce rôle

Lecture de `models.py`, `services.py`, `payments.py`, `serializers.py`, `admin.py`, `crm_views.py`, routes/templates CRM, types du frontend et notifications. Aucun code produit, base locale ou distante, compte, secret, configuration privée ni paiement n’a été modifié. La conception ci-dessus doit être implémentée puis validée indépendamment avant qu’un gate fonctionnel soit annoncé.

Complément documentaire : les deux sources officielles liées ci-dessus ont été ouvertes et consultées le 1er novembre 2026. Il s’agit de limites conditionnelles de mise en service, sans affirmation d’applicabilité universelle ni production de documents légaux pour le client.
