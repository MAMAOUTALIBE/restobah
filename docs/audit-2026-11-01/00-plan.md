# Audit et plan de livraison STC — 1er novembre 2026

## Objectif et périmètre

Préparer la livraison client du **2 novembre 2026**, avec **commandes réelles et paiement sur place**, choix confirmé par l’utilisateur. Auditer les parcours publics, les comptes clients, le CRM, l’API, les droits, la persistance et l’exploitation. Conserver le design crème/violet/orange et les données existantes.

Le plan est exécuté sans attente de validation intermédiaire. Les informations du client et les services externes manquants sont traités comme dépendances explicites : aucune identité, mention légale, réception SMTP ou ouverture commerciale ne sera inventée. L’instance publique existante reste une démonstration tant que les conditions d’ouverture réelles ne sont pas satisfaites.

## Méthode et critères d’acceptation

- Lecture des consignes, du code et des rapports précédents ; aucune consigne `AGENTS.md` trouvée au démarrage. Référence initiale : `0c5c588`, copie de travail propre.
- Chaque défaut doit avoir une reproduction, un correctif limité et un contrôle après correction. Les revues indépendantes précèdent le passage à la phase suivante.
- Les parcours qui écrivent utilisent uniquement des bases, comptes et médias jetables. Le contrôle public reste sans écriture métier.
- La livraison doit passer TypeScript, ESLint, build, tests serveur et navigateur adaptés ; les migrations sont vérifiées sur PostgreSQL, les fichiers statiques en mode production et les configurations proxy dans leurs conteneurs.
- Les preuves distinguent les tests locaux, les doubles réseau, les échanges externes réels et les contrôles après déploiement. Aucun résultat ne signifie une garantie absolue d’absence de défaut.

## Matrice d’audit

| Surface | Sections et fonctions à contrôler |
|---|---|
| Accueil et carte | En-tête, menu, recherche, filtres, catégories, carrousel, promotions, cartes, images, options, allergènes, favoris, pied de page et fenêtres d’information. |
| Panier et commande | Quantités, suppression, prix/options actualisés, retrait/livraison, frais/minimum/zone, coordonnées, pannes, double soumission, commande invitée ou connectée et paiement sur place. |
| Comptes | Inscription, connexion, déconnexion, réinitialisation, adresses, favoris, suppression et isolation des données. |
| Suivi client | Références invitées, compte connecté, statuts, historique, actualisation, confidentialité et reprise des erreurs. |
| CRM | Connexion/droits, accueil, commandes/filtres/recherche/pagination/actions, plats/photos/prix/disponibilités, réglages/horaires/fermetures, révisions concurrentes. |
| Infrastructure | PostgreSQL/migrations, sauvegarde/restauration, médias et fichiers privés, conteneurs/proxys, CI, dépendances, paquet de livraison et contrôles avant ouverture. |
| Écrans et accès | Mobile 320/390 px, tablette 768 px, ordinateur 1280 px, clavier/focus, absence de débordement, messages et boutons utilisables. |

## Plan de correction autonome

Les priorités ci-dessous sont établies à partir des reproductions et contrôles de l’audit. Les preuves détaillées et les résultats de clôture sont consignés dans les rapports voisins.

| Lot | Priorité | Travaux | Acceptation | État initial |
|---|---|---|---|---|
| A — État de référence | P0 | Exécuter les suites existantes, auditer chaque surface et consulter les contrôles CI réels. | Matrice documentée, défauts reproduits, résultats sans extrapolation. | Audit effectué ; voir 01–05 |
| B — Cohérence des parcours | P1 | Corriger le panier qui masque les nouveaux réglages ; conserver recherche et pagination après action CRM ; corriger les incohérences d’horaires et de statut confirmé par l’audit. | Régressions rouges puis vertes ; prix, modes et pause cohérents ; aucune perte de contexte ou fausse confirmation d’enregistrement. | PASS technique ; preuves dans 06-qa |
| C — Paiement sur place | P0 commercial | Ajouter un mode serveur dédié, distinct de la simulation et de Stripe ; confirmer la commande, suivre le montant dû et l’encaissement autorisé, préserver les historiques et l’idempotence. | Commande réelle testée de bout en bout ; droits/CSRF/concurrence ; aucun faux paiement, appel Stripe ni changement des anciennes commandes. | PASS indépendant : métier, migration et concurrence |
| D — Sécurité et stabilité | P1/P2 | Corriger le cache des réponses API privées, les dépendances vulnérables de développement et les régressions CI/cartes/connexions PostgreSQL. | Tests de cache et permissions ; audits dépendances ; suite Linux/PostgreSQL et gabarits mobiles réussis. | PASS technique ; preuves dans 06-qa |
| E — Exploitation | P1 | Réparer le paquet VPS et les sauvegardes en échec ; rendre les fichiers privés persistants ; fournir sauvegarde planifiable, restauration contrôlée et vérification avant ouverture. | Contrôles sur répertoires/DB jetables ; archive sans secrets ; restauration effective ; déploiement réversible et données conservées. | PASS technique ; preuves dans 06-qa |
| F — Recette et livraison | P0 | Rejouer les suites finales, relire les corrections, produire le bilan et publier la version vérifiée sur l’environnement autorisé. | Résultats finaux traçables, revue indépendante, contrôles HTTPS et version publiée identifiée. | Recette locale finale réussie ; CI et publication après commit |

## Dépendances de l’ouverture commerciale

Demandées à l’utilisateur pendant les travaux : domaine final, identité/coordonnées réelles, horaires/zones/frais, contenus légaux et allergènes validés, configuration SMTP privée et destinataires des notifications. Le choix de paiement sur place évite une dépendance à Stripe pour l’encaissement commercial ; l’équipe reste responsable du règlement physique.

Le compte de démonstration partagé ne doit pas conserver un accès d’écriture à une base commerciale. Sa désactivation et la création de comptes nominatifs font partie du contrôle d’ouverture, sans supprimer l’accès de démonstration actuellement demandé par l’utilisateur.

Le bilan final indiquera les corrections exécutées, les tests réellement passés et chaque dépendance externe restant ouverte. Le terme « 100 % » ne sera pas employé pour masquer un service non configuré ou un contrôle non réalisé.
