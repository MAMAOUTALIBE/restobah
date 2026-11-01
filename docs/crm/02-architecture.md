# Architecture du CRM STC

Audit du 1er novembre 2026. Rôle : architecte logiciel. Aucune modification du code produit, migration ou donnée pendant cet audit.

## Décision

Le CRM sera une interface Django dédiée sous `/crm/`, composée de templates, formulaires Django et JavaScript progressif. Cette décision a été confirmée par le coordinateur. Les quatre rubriques sont **Accueil, Commandes, Ma carte et Mon restaurant**. Une nouvelle SPA React et une seconde API CRUD ne sont pas nécessaires.

Cette architecture réutilise les sessions, permissions, validations de modèles, fichiers téléversés et transactions existants. Le site client React demeure indépendant et conserve ses composants, son panier et son identité visuelle.

## État vérifié par lecture du dépôt

- `backend/config/urls.py` ne contient actuellement que l’administration Django et les API publiques/client. Il n’existe pas de CRM métier dédié ni d’API de mutation staff du catalogue.
- `backend/shop/admin.py` permet déjà la gestion des produits/photos/options, horaires/fermetures et commandes. Son formulaire technique et ses champs JSON sont inadaptés à l’interface demandée ; il reste disponible comme outil administratif avancé.
- `backend/shop/models.py` fournit les entités nécessaires : `Restaurant`, `OpeningHour`, `Closure`, `Category`, `Product`, `Order`, `OrderLine`, `OrderHistory`. Aucun nouvel ensemble de tables n’est indispensable au CRM initial.
- `services.product_data()` expose la photo téléversée, le prix calculé et la disponibilité effective. `services.restaurant_data()` fournit les coordonnées, horaires et réglages de commande utilisés par le site.
- `Order.check_transition()` et `Order.transition()` définissent les transitions et l’historique ; `payments.release_checkout()` protège l’annulation d’un paiement Stripe en attente. Ces règles doivent rester la référence.
- L’accès staff au détail d’une commande publique est actuellement accordé par `is_staff` seul dans `authorized_order()` et `OrderView`, sans permission `view_order`. C’est une frontière à revoir avec l’expert sécurité si le CRM introduit des droits métier granulaires ; cette observation de source n’est pas encore une reproduction fonctionnelle.
- `src/App.tsx` recharge le catalogue au montage ; seul le restaurant est ensuite actualisé périodiquement. En l’état, une page client déjà ouverte ne reflète pas automatiquement un nouveau prix ou une disponibilité modifiée.
- Vite et Nginx transmettent `/api`, `/admin`, `/static`, `/media` au backend. Il faut ajouter `/crm` aux proxys pour le développement et la recette Docker.

Sources principales : [routes](../../backend/config/urls.py), [modèles](../../backend/shop/models.py), [administration](../../backend/shop/admin.py), [services métier](../../backend/shop/services.py), [paiements](../../backend/shop/payments.py), [site client](../../src/App.tsx), [proxy Vite](../../vite.config.ts), [proxy Nginx](../../deploy/nginx.conf).

## Structure et propriété des fichiers

| Couche | Emplacement recommandé | Responsabilité |
| --- | --- | --- |
| Routes CRM | `backend/shop/crm_urls.py` + inclusion dans `config/urls.py` | Noms stables et namespace `crm` |
| Contrôle et mutations | `backend/shop/crm_views.py` | Permissions, formulaires, transactions, redirections et fragments |
| Saisie | `backend/shop/crm_forms.py` | Champs français courts, validation prix/photos/horaires et conversions |
| Templates | `backend/shop/templates/shop/crm/` | Base et quatre rubriques ; formulaires et fragments réutilisés |
| Présentation progressive | `backend/shop/static/shop/crm.css`, `crm.js` | Responsive, boutons explicites, actualisation et retours d’état |
| Synchronisation publique | `src/App.tsx` ou hook dédié | Catalogue/restaurant actualisés sans écran de chargement récurrent |
| Intégration | `vite.config.ts`, `deploy/nginx.conf`, documentation | `/crm/` accessible par le même domaine que le site |
| Tests | `backend/shop/test_crm.py`, `tests/crm.spec.ts` | Permissions, données invalides, persistance et parcours complets |

Le frontend possède templates/CSS/JS CRM ; le backend possède vues/formulaires/routes. Ils coordonnent les noms de contexte et d’URL avant les modifications simultanées. La validation reste indépendante.

## Contrat des routes

Les noms ci-dessous sont proposés pour stabiliser les liens de templates. Les libellés affichés restent français.

| URL | Nom proposé | Comportement |
| --- | --- | --- |
| `/crm/connexion/` | `crm:login` | GET formulaire, POST authentification d’un membre autorisé |
| `/crm/deconnexion/` | `crm:logout` | POST uniquement, protection CSRF |
| `/crm/` | `crm:dashboard` | Accueil et indicateurs réellement calculés |
| `/crm/commandes/` | `crm:orders` | Liste filtrée et accès au détail des commandes |
| `/crm/commandes/<id>/statut/` | `crm:order_status` | POST transition validée, jamais de changement par GET |
| `/crm/carte/` | `crm:menu` | Plats, photos, prix, disponibilité et recherche simple |
| `/crm/carte/ajouter/` | `crm:product_add` | GET/POST création d’un plat |
| `/crm/carte/<id>/modifier/` | `crm:product_edit` | GET/POST modification sans écraser les autres champs |
| `/crm/carte/<id>/disponibilite/` | `crm:product_availability` | POST d’une valeur booléenne explicite, pas d’inversion aveugle |
| `/crm/restaurant/` | `crm:restaurant` | GET/POST coordonnées, commandes ouvertes, retrait/livraison et horaires |
| Fragments GET sous `/crm/` | `crm:orders_fragment`, `crm:dashboard_fragment` | Actualisation protégée des blocs non édités ; réponses HTML sans données publiques supplémentaires |

Après une mutation réussie, utiliser POST–redirection–GET et un message français. Une saisie invalide réaffiche le formulaire rempli avec les erreurs près des champs. Une session expirée ne doit pas être interprétée comme une réussite d’un rafraîchissement : le JS détecte la redirection/login ou une réponse d’erreur et conserve le contenu en cours.

## Contexte de templates à partager entre agents

Contrat minimal recommandé ; les agents peuvent convenir de noms différents avant implémentation, mais les vues et templates doivent les partager explicitement.

| Page | Données nécessaires |
| --- | --- |
| Base commune | `section` (`accueil`, `commandes`, `carte`, `restaurant`), `restaurant`, `operator_name`, `demo_mode`, `ordering_enabled`, `is_open`, `permissions` (lecture/modification produits, commandes et restaurant) |
| Accueil | Nombre de commandes du jour, commandes en cours, total des commandes correspondant au filtre annoncé, nombre de plats indisponibles, dernières commandes ; aucune métrique inventée |
| Commandes | `orders` avec lignes et historique préchargés, filtre actuel, libellés français, actions autorisées par commande et état de paiement ; coordonnées uniquement si permission de lecture |
| Ma carte | `products` avec catégorie, `image_url` déjà résolue, prix `Decimal`, disponibilité configurée et effective, URL de modification et droit d’édition ; `categories`, recherche et filtre actuels |
| Formulaire plat | `form`, objet courant ou absence pour création, aperçu photo, URL de retour ; ne jamais vider les options/promotions non incluses au formulaire |
| Mon restaurant | `form` et `opening_formset` (ainsi que fermetures si gérées), ensemble des erreurs et état enregistré ; validation et sauvegarde atomiques |

L’URL photo doit être résolue côté vue : `photo.url` si photo présente, sinon `/images/<clé>.jpg` pour une clé locale existante. Les photos téléversées restent sous `/media/`, qui est déjà séparé des ressources exécutables. Les templates conservent l’échappement automatique ; aucune description de plat n’est rendue comme HTML de confiance.

## Règles métier et sécurité aux frontières

1. **Accès** : session Django active et membre `is_staff`, puis permissions de modèle pour chaque lecture/mutation (`view_product`, `add_product`, `change_product`, `view_order`, `change_order`, `view_restaurant`, `change_restaurant`). Un client connecté ne devient pas gérant. Le serveur contrôle les droits même si un bouton est caché.
2. **Authentification** : formulaire de connexion staff explicite ; protéger et limiter ses tentatives. Valider toute cible `next` au même domaine. Ne pas exposer le compte administrateur local ni ses fichiers d’accès.
3. **CSRF** : conserver le middleware Django et `{% csrf_token %}` sur tous les formulaires. Les requêtes JS de mutation transmettent `X-CSRFToken` ; aucune exemption de convenance.
4. **Plats** : `ModelForm` limité à une liste explicite de champs ; `full_clean()` et erreurs françaises ; montants `Decimal`, pas de calcul monétaire en flottants. Validation du vrai contenu image, poids et dimensions raisonnables. Allergènes saisis comme texte/choix simples, jamais JSON demandé au patron.
5. **Disponibilité** : enregistrer la valeur souhaitée, puis recalculer la disponibilité effective via les règles existantes (options obligatoires/promotions). Préserver la protection serveur de la commande.
6. **Commandes** : ne jamais modifier prix/lignes/total historiques. Verrouiller la commande lors d’une transition, appeler `check_transition()`/`transition()`, conserver `OrderHistory`. Pour annuler une commande Stripe en attente, utiliser `release_checkout()` avant la transition ; un paiement confirmé exige son traitement Stripe préalable.
7. **Horaires** : conserver les services qui passent minuit. Rejeter heures identiques, jours invalides et périodes superposées ; sauvegarder configuration et périodes dans une transaction, sans supprimer les horaires avant d’avoir validé l’ensemble.
8. **Concurrence** : une action de disponibilité exprime un booléen explicite ; une transition peut vérifier l’ancien statut attendu et afficher qu’une autre personne a déjà mis la commande à jour. Aucun retour silencieux à un statut antérieur.
9. **Données** : pas de nouvelle base CRM ni de duplication des commandes/catalogue. Les modifications doivent être immédiatement vérifiables par les API publiques et la base déjà utilisée.

L’expert sécurité et l’expert base de données doivent confirmer les permissions et les contraintes ; ce rapport ne vaut pas audit de sécurité exécuté.

## Actualisation et synchronisation

- **CRM commandes/accueil** : rafraîchissement court des seuls fragments utiles, lorsque l’onglet est visible ; reprise au retour sur l’onglet. Ne pas remplacer un formulaire en cours de saisie. Bouton d’actualisation/reprise explicite en cas d’échec réseau et état « dernière mise à jour » fiable.
- **Site client déjà ouvert** : rafraîchissement silencieux du catalogue et du restaurant à intervalle raisonnable (10–15 s) et au retour de focus/visibilité. Réutiliser la réconciliation du panier existante ; éviter de remettre `loading=true` et de faire clignoter les cartes à chaque cycle. Le serveur reste l’autorité lors d’une commande.
- **Disponibilité et maquette** : le site existant laisse un produit indisponible consultable et bloque son ajout ; un test existant le vérifie. La maquette indique « masqué ». Pour préserver le comportement accepté, préférer un libellé CRM exact, tel que « Indisponible à la commande », sauf décision explicite de changer le contrat public et les tests.
- **Modes démonstration/réel** : le statut effectif `isOpen` est forcé ouvert par `DEMO_MODE`, alors que `ordering_enabled` reste un vrai interrupteur. Le CRM doit distinguer clairement fermeture manuelle et horaires ; il ne doit pas promettre un restaurant ouvert réel à partir du mode démonstration. Aucun paiement réel n’est débloqué dans cette mission.

## Validation attendue avant livraison

- Tests Django sur base de test : visite anonyme/client/staff sans permission/staff autorisé ; CSRF ; création/modification/photos/prix invalides ; disponibilité effective ; horaires valides/incomplets/superposés/nocturnes ; transitions de commandes et intégrité historique ; rollback d’une saisie invalide.
- Playwright sur instance isolée (`scripts/e2e.py`) : connexion staff, quatre rubriques, création/modification d’un plat avec vraie photo, persistance après rechargement, bascule disponible, commande client puis suivi staff/client, modification horaires, synchronisation d’un onglet public déjà ouvert, erreurs et rendu mobile.
- `npm run check`, tests Django, `makemigrations --check --dry-run` et `manage.py check` selon les changements ; compilation/collecte des fichiers statiques et routage proxy vérifiés.
- Les tests d’écriture ne doivent pas altérer la base locale du patron ; utiliser l’instance jetable documentée.

## Contrôles réellement effectués pour cet audit

Lecture de `README.md`, `API_CONTRACT.md`, `backend/config/{urls,settings}.py`, `backend/shop/{admin,models,views,serializers,services,payments}.py`, `src/services/api.ts`, `src/App.tsx`, `vite.config.ts`, `deploy/nginx.conf`, `scripts/e2e.py` et du test d’administration existant. Recherche des fichiers `AGENTS.md` : aucun résultat dans le dépôt accessible. Aucun test fonctionnel, migration ni déploiement exécuté dans ce rôle d’audit ; les contrôles ci-dessus restent à réaliser par QA et validation.
