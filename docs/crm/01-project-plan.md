# CRM STC — audit et plan du chef de projet

Date de l’audit : 1 novembre 2026. Rôle spécialisé : chef de projet. Ce document constate le code lu ; il ne constitue pas une validation fonctionnelle.

## État constaté

- Aucune consigne `AGENTS.md` trouvée par `rg --files -g AGENTS.md -g '!node_modules' -g '!backend/.venv' -g '!dist'` (sortie vide, code 1).
- Le site client est une application React/TypeScript (`src/App.tsx`, `src/components/`, `src/services/api.ts`). Le travail visuel antérieur est déjà présent et doit être conservé.
- Le seul outil de gestion existant est l’administration Django générique `/admin/` : `backend/config/urls.py`, `backend/shop/admin.py`. Il expose de nombreux modèles et formulaires techniques ; aucune interface professionnelle organisée en quatre rubriques n’existe au moment de cet audit.
- Les modèles métier sont déjà persistants : `Product`, `Category`, `OptionGroup`, `Choice`, `Restaurant`, `OpeningHour`, `Closure`, `Order`, `OrderLine`, `OrderHistory` et paiements dans `backend/shop/models.py`.
- L’administration permet déjà de modifier les photos, prix, disponibilités et horaires. Les commandes disposent de transitions autorisées et d’un historique ; `OrderAdmin` utilise les règles du modèle et une transaction. Ces règles doivent être réutilisées par le CRM, plutôt que recodées dans le navigateur.
- Les routes API publiques actuelles sont en lecture seule pour catalogue, catégories et restaurant. Les routes commandes clientes n’offrent pas une gestion complète de l’équipe (`backend/config/urls.py`, `backend/shop/views.py`). Il manque une API de gestion protégée et ses contrôles de droits.
- Le catalogue public n’est chargé qu’au montage dans `src/App.tsx`. Seules les informations restaurant sont repollées toutes les 60 s ; le suivi client dans `src/components/Orders.tsx` est repollé toutes les 30 s. La synchronisation automatique d’un catalogue déjà ouvert manque.
- Un plat épuisé demeure consultable sur le site, mais l’ajout est désactivé (`ProductCard.tsx`, tests existants). La maquette indique « masqué » : conserver la règle existante et afficher « indisponible sur le site » évite de promettre un comportement différent ou de casser les tests antérieurs.
- Les paiements réels sont volontairement bloqués ; le README décrit un mode démonstration/simulation et des limites de mise en production. Rendre le CRM fonctionnel ne transforme pas cette instance en service marchand réel.

## Périmètre de livraison prioritaire

Le CRM doit utiliser les mêmes données Django et conserver exactement quatre rubriques principales : **Accueil**, **Commandes**, **Ma carte**, **Mon restaurant**. L’administration Django demeure disponible comme outil technique de secours. Aucun nouveau stockage métier dans `localStorage`.

| Priorité | Livraison | Critère d’acceptation observable |
|---|---|---|
| P0 | Accès professionnel protégé | Un visiteur et un compte client ne lisent ni ne modifient les données de gestion ; un gérant autorisé ouvre le CRM. Les écritures vérifient aussi CSRF et les permissions côté serveur. |
| P0 | Navigation et design simples | Exactement quatre rubriques ; palette crème/violet/orange ; libellés explicites ; état actif visible ; rendu utilisable à 320 px et sur ordinateur ; erreurs et chargements compréhensibles. |
| P0 | Ma carte : création et modification | Un plat créé avec catégorie, prix et description requise est enregistré puis retrouvé après rechargement. Une modification ne détruit pas ses options ou allergènes existants. Prix négatif/invalide, nom vide et catégorie inconnue sont refusés côté serveur avec un message exploitable. |
| P0 | Photos | Une vraie photo acceptée remplace l’illustration et persiste après rechargement. Un fichier non image ou trop volumineux est refusé ; un échec d’envoi préserve les données et la photo précédentes. |
| P0 | Disponibilité | Un bouton explicite modifie réellement le plat et sa disponibilité publique. Il est désactivé pendant l’enregistrement ; un refus ne laisse pas afficher un faux succès. Les promotions rattachées restent cohérentes. |
| P0 | Commandes | Liste réelle, détail et coordonnées autorisées ; filtres métier simples ; passage confirmé → en cuisine → prêt → terminé conforme aux transitions existantes ; refus des états invalides et des préparations sans paiement confirmé. Historique et suivi client mis à jour. |
| P0 | Mon restaurant | Coordonnées, activation des commandes, modes de service et horaires sont persistants. Horaires identiques ou invalides refusés. Fermetures et périodes de nuit respectées. Le statut affiché distingue une pause manuelle des horaires d’ouverture. |
| P0 | Synchronisation | Une page client déjà ouverte reçoit prix/photo/disponibilité/horaires modifiés, sans perdre sa recherche, son panier ou un formulaire en cours. Les modifications de commande remontent au suivi client. |
| P0 | Persistance et erreurs | Après succès, un rechargement restitue les valeurs. Sur panne réseau, aucun succès simulé et aucune perte silencieuse de saisie. Données métier stockées exclusivement sur le serveur. |
| P1 | Accueil opérationnel | Compteurs réels du jour et commandes à traiter ; raccourcis vers les actions utiles ; aucun chiffre fictif. Une éventuelle somme distingue correctement commandes annulées ou impayées. |
| P1 | Rafraîchissement sûr | Les données de consultation s’actualisent automatiquement lorsque la page est visible ; les brouillons d’édition ne sont pas écrasés. Prévenir ou limiter les doubles écritures et conflits concurrents. |
| P1 | Exploitation | Documentation d’accès et d’usage, procédure de vérification, sauvegarde/migrations si nécessaires. Aucun secret dans les rapports ou captures. |
| P2 | Extensions ultérieures | Rapports avancés, fidélité, exports marketing et comptabilité : hors du noyau requis, sans créer de nouvelles rubriques dans cette livraison. |

## Répartition des missions spécialisées

1. **Chef de projet** : présent audit, priorités, critères d’acceptation et suivi des preuves.
2. **Architecte** : entrée CRM et contrat API, découpage des composants, réutilisation des services Django et stratégie de synchronisation.
3. **Expert UX** : parcours connexion → tâche courante → confirmation ; formulaires courts, erreurs proches du champ, prévention des pertes de saisie.
4. **Designer UI** : adaptation fidèle de la maquette et des quatre rubriques ; listes de plats et commandes, états et mobile.
5. **Frontend** : implémentation des écrans, client API, upload, états d’attente/échec, rafraîchissement et synchronisation publique.
6. **Backend** : routes de gestion protégées, validation, sérialisation et transitions transactionnelles ; aucune confiance dans les prix ou statuts fournis par le client.
7. **Base de données** : contraintes existantes, conservation des relations et historiques, migrations strictement nécessaires, intégrité après réouverture des données.
8. **Sécurité** : session, CSRF, accès non authentifié/client/équipe, permissions de lecture et d’écriture, upload et exposition des données de commandes.
9. **QA** : matrice de tests indépendante et parcours réels sur instance jetable ; erreurs de saisie, persistance, mobile et synchronisation CRM/site.
10. **Validation** : revue indépendante des changements et des preuves, vérification des régressions ; gate PASS uniquement après les contrôles effectivement exécutés.

Les quatre slots simultanés de l’environnement imposent plusieurs vagues. Chaque spécialiste remet un rapport ou du code/test vérifiable ; le nombre de rôles ne doit pas être confondu avec le nombre d’agents actifs en même temps.

## Phases et gates

1. **Audit et contrat** : inventorier, choisir l’entrée CRM et le contrat de gestion ; sortie attendue : rapports spécialisés et périmètre partagé. Pas de mutation de la base locale pendant l’audit.
2. **Implémentation du noyau** : backend et frontend sur fichiers séparés ; connecter les quatre rubriques aux données réelles. Chaque tranche reçoit revue et tests ciblés avant d’être déclarée terminée.
3. **Recette et durcissement** : examiner erreurs, droits, photos et concurrence ; corriger les défauts constatés puis rejouer les tests concernés.
4. **Validation finale** : exécuter les contrôles de compilation et les parcours d’intégration nécessaires ; rendre un bilan distinguant fonctions opérationnelles, commandes exécutées, corrections et limites.

## Vérifications à exécuter, non exécutées par cet audit

- `npm run check` : TypeScript, ESLint, compilation.
- `npm run test:backend` : modèles, API et sécurité ; compléter la suite par des tests de gestion staff.
- `python3 scripts/e2e.py <tests-ciblés>` : démarrage d’une base et de services jetables, accès administrateur de test privé, puis Playwright. Ce chemin protège les données locales.
- Tests de parcours à ajouter : création/modification/photo/disponibilité, horaires et statut restaurant, statut commande et suivi client, refus anonyme/client/équipe sans droits, invalidations de formulaires, rechargement et synchronisation automatique.
- Contrôles visuels 320/390/430 px et ordinateur : listes, formulaires, dialogues, erreurs, absence de débordement et boutons utilisables.

`npm run test:e2e` direct peut ajouter des données au serveur déjà démarré ; l’utiliser pour les écritures CRM sans isolation ne satisfait pas l’exigence de préservation du travail existant. Les chiffres de tests historiques du README ne prouvent pas la validation de la nouvelle livraison.

## Blocages et limites

- Pas de blocage technique majeur observé dans le code pour une livraison locale : dépendances et architecture existantes couvrent le noyau demandé.
- L’hébergement, les coordonnées et allergènes réels, SMTP et paiements réels restent des éléments de mise en production distincts ; aucune activation ou publication externe n’est autorisée par cet audit.
- Aucune compilation, migration, requête de mutation ou suite de tests n’a été exécutée par le chef de projet. Les seuls contrôles effectués sont les recherches et lectures de fichiers rapportées ci-dessus.
