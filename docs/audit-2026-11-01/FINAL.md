# Bilan technique de préparation à la livraison du 2 novembre

Date : 1er novembre 2026. Cible confirmée par l’utilisateur : **commandes réelles avec paiement sur place**. Le [plan](00-plan.md), le [registre initial](01-findings.md) et les rapports spécialisés conservent les défauts reproduits, leurs corrections et les revues. L’utilisateur a autorisé l’exécution autonome ; aucune validation intermédiaire de sa part n’a été requise pour les corrections.

## Résultat du travail local

Les lots de correction des parcours, du paiement sur place, de la sécurité et de l’exploitation ont reçu une revue indépendante. Le code fournit les quatre rubriques CRM demandées et les parcours client conservant leur palette et leur mise en page. Les données, secrets et accès de la démonstration ne sont pas inclus dans le code livré.

| Surface | Corrections et comportement contrôlé |
|---|---|
| Accueil, carte et fiches | Recherche, filtres, catégories, promotions, options et favoris vérifiés ; gabarit des cartes corrigé sur Linux à 388/390 px, sans élargir les tolérances. |
| Panier et validation | Réglages issus d’une source unique ; frais, pause, modes, zone, minimum et délais se répercutent sans perdre le brouillon. Confirmation fraîche après polling lent, reprise d’erreur et double soumission contrôlées. |
| Clavier et fenêtres | Contrôles réellement désactivés exclus du focus ; boucle clavier et fenêtre supérieure seules actives ; retour du focus et blocage du défilement conservés. |
| Compte et suivi | Inscription, connexion, adresses, favoris, suppression, réinitialisation et isolation des commandes couverts par les suites. Les échanges SMTP externes restent distincts des tests. |
| Commandes CRM | Recherche/page conservées après succès et conflit, transactions et permissions maintenues ; les badges d’un formulaire refusé reflètent les données enregistrées. |
| Horaires et carte CRM | Services nocturnes, fermetures et filtres malformés contrôlés ; création/édition, photo, prix, disponibilité et synchronisation réelle retestés. |
| Règlement sur place | Commande réelle `confirmed/due`, origine persistée, préparation avant règlement, encaissement nécessaire avant finalisation. Encaissement/remboursement complets autorisés, tracés, verrouillés et idempotents, sans faux débit ni acteur exposé au client. |
| Sécurité | Cache privé `no-store`, JSON et contrôles d’accès conservés, dépendance de développement corrigée ; aucun secret courant détecté dans les chemins versionnables. |
| Exploitation | Paquet VPS, sauvegardes complètes atomiques, manifeste/rétention/fraîcheur, volumes privés persistants et restauration contrôlée ; modes publics/privés et lecture réelle des photos par nginx vérifiés. |
| Préparation client | Contacts et documents configurables sans secret public ; commande de contrôle en lecture seule, alias internes de santé explicitement limités, aucune fausse déclaration d’ouverture commerciale. |

## Contrôles finaux réellement exécutés avant publication

| Contrôle | Résultat et portée |
|---|---|
| Suite Django complète PostgreSQL 17.10, code final | **199/199 réussis**, aucun ignoré, 22,359 s, après les correctifs d’alias et de suppression d’un ancien opérateur financier. Base de test détruite. |
| Précontrôles et registre | Les **22 cas de préparation**, les droits, l’immutabilité, les migrations historiques, la concurrence et le refus de suppression sans perte de données sont inclus dans la suite finale ; ils ne sont pas additionnés à nouveau. |
| Navigateur, campagne générale | **202 réussis, 6 ignorés**, 8,4 min. Les six cas de commande réelle sont volontairement réservés à la campagne suivante. |
| Navigateur, campagne sur place hors démonstration | **15/15 réussis**, 59,3 s : neuf scénarios réseau et six chaînes métier réelles sur base jetable, ordinateur/tablette/mobile. Les six cas ignorés dans la campagne générale sont ici réellement exécutés. |
| Linux, cartes et fenêtres | **24/24 réussis** dans l’image officielle Playwright ; écart de hauteur reproduit avant correction puis supprimé. |
| Outillage | **16/16 réussis** : sauvegardes, erreurs, manifeste, fraîcheur, rétention, verrou, paquet et politique des connexions. |
| Docker et restauration | Intégration sur image fraîche réussie : recréation, sauvegarde/restauration PostgreSQL, médias et fichiers privés restaurés ; lecture HTTP réelle des médias et refus d’accès aux privés par le frontend. Détails dans le rapport QA. |
| Qualité | TypeScript, ESLint, compilation de production, contrôle des migrations et diff-check réussis. Audits JavaScript complet/production et Python : aucune vulnérabilité connue signalée lors des contrôles. |

Les relances intermédiaires et les lots ciblés déjà inclus ne sont pas additionnés une seconde fois pour produire un total artificiel. Les scripts qui écrivent utilisent des bases, médias et comptes temporaires. La revue indépendante est détaillée dans [06-qa.md](06-qa.md).

## Publication et retour arrière

La CI, la construction distante et les contrôles après publication produisent leurs propres preuves après le commit. Consulter le workflow du commit et le marqueur privé `.runtime/deployed-revision` du serveur, ainsi que `.runtime/deployments/<révision>/state.json` et `online-validation.json`. Une copie de travail locale ou ce rapport ne suffisent pas à identifier une version en ligne.

La migration compare les anciens champs métier avant/après, puis contrôle séparément la nouvelle origine de paiement et le registre initialement vide. Le retour à l’ancien code `0c5c588` n’est testé que pour la démonstration actuelle en simulation, avec son défaut SQL durable. Une exploitation réelle exige une image comprenant le règlement sur place ou une maintenance ; aucune migration inverse supprimant les règlements n’est prévue.

Les scripts de bascule sauvegardent d’abord la base, les médias et les fichiers privés, préservent les autres services et vérifient la santé ainsi que le vrai formulaire CRM. Leur reprise retire seulement les fichiers nouvellement copiés, en refusant un conflit de modification. Un retour arrière réussi n’est annoncé qu’après les contrôles de santé et HTTP.

## Dépendances de l’ouverture commerciale

**Le dossier technique ne vaut pas autorisation d’ouvrir aux commandes réelles.** Les informations suivantes n’ont pas été fournies ou validées au cours de ces travaux :

- Identité et coordonnées du client, domaine final, carte/allergènes/photos, horaires, zones et frais approuvés.
- Mentions légales, confidentialité et conditions de commande propres au restaurant.
- SMTP réel, destinataires d’équipe et réception effective des confirmations/réinitialisations.
- Comptes nominatifs, retrait des accès partagés de démonstration dans la future base commerciale.
- Destination extérieure chiffrée, réception de la copie et restauration de cette copie ; exigences de caisse selon le pays et la situation du client.

Le contrôle `check_production` liste les blocages sans modifier les données. `configurationReady` signifie uniquement configuration et sondes annoncées ; réception des e-mails et sauvegarde extérieure restent séparées. Aucun secret, contenu juridique, certification fiscale ou accord client n’a été inventé. La démonstration existante conserve son mode tant que ces conditions ne sont pas levées.

Le [dossier de livraison client](../CLIENT-DELIVERY.md), la [procédure de sauvegarde](../BACKUPS.md) et le [guide du gérant](../crm/GUIDE_GERANT.md) donnent les actions concrètes pour terminer la mise en service. Aucun test fini ne garantit l’absence absolue de défaut ni une capacité de charge non mesurée.
