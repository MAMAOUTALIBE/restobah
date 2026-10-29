# STC — état de livraison après audit (25 octobre 2026)

## Verdict par environnement

| Environnement | État | Limites |
| --- | --- | --- |
| Local (`npm run dev:all`, SQLite) | **Opérationnel pour la démonstration et la recette.** Commandes réellement enregistrées, paiement simulé. | Mode démonstration : aucune préparation, aucun paiement. |
| Docker + PostgreSQL 17 (Nginx, gunicorn) | **Opérationnel en recette** : 41 parcours Playwright réussis sur une pile reconstruite à partir du code actuel. | DEBUG activé (instance de revue locale), paiement simulé. |
| Démonstration publique (VPS Hostinger, nginx + certbot, PostgreSQL 17) | **En ligne sur https://stc.srv2086522.hstgr.cloud** depuis le 25 octobre 2026 : 41 parcours Playwright réussis contre l'adresse publique en HTTPS, puis base réinitialisée. `stc.sonutech.tech` attend son enregistrement DNS. | Mode démonstration, paiement simulé, e-mails non envoyés, pas de sauvegarde planifiée. Détails : [OPERATIONS.md](OPERATIONS.md#démonstration-publique-déployée-25-octobre-2026). |
| Production commerciale (domaine, HTTPS, SMTP, Stripe) | **Prête à configurer.** `check --deploy` sans avertissement ; garde-fous de démarrage vérifiés. | Domaine, SMTP, clés Stripe **test**, informations du restaurant et documents légaux à fournir. |
| Exploitation commerciale avec paiement en ligne | **Bloquée volontairement.** Les clés Stripe réelles sont refusées au démarrage. | Une décision et une validation distinctes sont nécessaires (voir plus bas). |

Seule la démonstration ci-dessus a été publiée, à la demande de l'exploitant. Aucun paiement réel n'a été effectué et aucun autre service externe n'a été modifié. Le déploiement a révélé et fait corriger deux défauts de la configuration nginx du conteneur : les en-têtes de sécurité (CSP, X-Frame-Options, HSTS) étaient absents de la page HTML et des ressources statiques, et la vraie IP des visiteurs était perdue derrière un proxy (limites de débit communes à tous).

## État initial constaté

Les affirmations de l'ancien rapport ont été réexécutées avant toute modification : `npm run check` réussi, 40 tests Django réussis (SQLite), `makemigrations --check` et `check` sans anomalie, 23 tests Playwright réussis (sur une instance isolée créée pour l'audit). Ces preuves étaient exactes, mais ne couvraient pas les défauts ci-dessous, établis par lecture du code et reproduits par des essais :

| Prio | Défaut | Preuve |
| --- | --- | --- |
| P0 | Une commande Stripe annulée dans l'administration gardait sa session de paiement ouverte : le client pouvait encore payer et le webhook ignorait ce paiement (argent encaissé sans trace). | `payments.py` : paiement appliqué seulement aux statuts `pending`/`failed` ; aucune fermeture de session |
| P0 | Sessions Stripe valables 24 h (valeur par défaut) : commandes en attente pendant une journée, sans nettoyage. | Aucun `expires_at`, aucune tâche d'annulation |
| P1 | Le suivi d'un client connecté (`GET /api/orders/` toutes les 30 s) consommait le quota de création de commandes (60/h en production) : après 30 min, impossible de commander (429). Quota anonyme de 300/h par IP atteint par un seul visiteur actif ou une IP partagée. | Reproduit : la suite E2E échouait en 429 |
| P1 | Toutes les erreurs de validation et tous les refus métier apparaissaient sous la forme « Vérifiez les champs indiqués. » (mot de passe trop courant, hors zone, minimum de livraison…). | Requêtes API sur une base temporaire |
| P1 | Un plat dont les options obligatoires sont toutes indisponibles restait « disponible » mais ne pouvait pas être commandé. | Idem |
| P1 | Catégories codées en dur côté interface : une catégorie créée dans l'administration n'apparaissait jamais. | `src/data/products.ts` |
| P1 | Aucun e-mail de confirmation au client ni alerte au restaurant ; échec SMTP de réinitialisation ignoré sans journal. | `views.py` (`except: pass`) |
| P1 | Remise « −30 % » codée en dur ; nombre d'avis fictif « (1,2 k) » ; mentions « démonstration » affichées hors démo ; adresse fictive affichée pendant le chargement. | `App.tsx`, `Catalog.tsx`, `Footer.tsx` |
| P1 | Allergènes en JSON libre pouvant casser l'affichage, sans écran de secours en cas d'erreur React. | `ProductDetails.tsx` |
| P1 | E-mails locaux (liens de réinitialisation) créés en `0644`, alors que la documentation les annonçait privés : `.env.example` remplaçait le backend privé. | `ls -la backend/.private-emails` |
| P2 | Recherche sensible aux accents ; longueurs maximales différentes entre interface et serveur ; URL de retour de paiement jamais nettoyée ; commandes invitées invisibles après connexion ; administration des commandes peu lisible (recherche par référence seulement) ; horaires réduits à la première plage ; code mort ; E2E écrivant dans la base locale. | Lecture du code |

## Corrections effectuées

- **Stripe** (`backend/shop/payments.py`, `admin.py`, `models.py`) : l'annulation d'une commande en attente ferme d'abord la session (`Session.expire`) ; si le client a payé ou si Stripe ne répond pas, l'annulation est refusée avec un message. Un paiement arrivé sur une commande annulée est enregistré et signalé « Remboursement à effectuer ». Sessions de 31 à 41 min avec clé d'idempotence stable par fenêtre de 10 min. Paiement refusé pour une commande impayée de plus de 45 min. Nouvelle commande `cancel_stale_orders`. Les montants inattendus sont journalisés.
- **Débit** : le quota `orders` ne s'applique plus qu'à la création ; lectures limitées à 3000/h, configurables (`ANON_THROTTLE_RATE`, `USER_THROTTLE_RATE`).
- **Messages d'erreur** (`errors.py`) : le texte du refus, ou le champ en français suivi de l'erreur.
- **Catalogue** : disponibilité réelle (options obligatoires), `regularPrice`/`discountPercent`, API `/api/categories/`, validation des allergènes, note facultative (migration `0004`), photo téléversée testée.
- **E-mails** (`notifications.py`) : confirmation client avec lien de suivi personnel, alerte équipe (`STC_ORDER_NOTIFICATION_EMAIL`), envoyée après validation de la transaction ; échecs journalisés sans bloquer la commande. Backend privé par défaut, fichiers existants passés en `0600`, dossiers privés en `700` dans l'image Docker.
- **Interface** : catégories issues de l'administration (grille mobile inchangée pour 7 éléments), remise et prix du carrousel issus du serveur, recherche sans accents, « (1,2 k) » retiré, footer et informations sans mention de démonstration hors démo, `ErrorBoundary`, longueurs alignées sur le serveur, lien de suivi importé puis retiré de l'adresse, commandes invitées de l'appareil conservées après connexion, URL de retour Stripe nettoyée.
- **Administration** : colonnes client/téléphone/remboursement, recherche par nom, e-mail ou téléphone, coordonnées lisibles.
- **Seconde passe (problèmes restants)** : zone de livraison obligatoire tant que la livraison est active (auparavant, une zone vide acceptait toutes les adresses) ; délais de retrait et de livraison réglables dans l'administration ; suppression du compte en libre-service (mot de passe exigé, adresses et favoris effacés, commandes conservées et détachées, comptes de l'équipe exclus) ; compteurs de débit partagés entre workers sur PostgreSQL (`DatabaseCache`, table créée par la migration 0005) ; liste des commandes de l'administration rechargée toutes les 30 s sauf pendant une sélection ou une saisie ; tests Django indépendants de `collectstatic` (ils échouaient sur un poste neuf ou en CI faute de manifeste).
- **Outillage** : `scripts/e2e.py` / `npm run test:e2e:isolated` (base, dossier runtime et e-mails temporaires ; ports 8001/5174) ; CI mise à jour ; `vite.config.ts` configurable (`STC_API_TARGET`, `STC_WEB_PORT`).

Le design validé est conservé : fond crème, boutons rouges, cartes arrondies, navigation mobile de 44 px, footer de 197 px sur mobile, 151 px sur tablette et 147 px sur ordinateur, comme avant.

## Résultats vérifiés (code final)

| Vérification | Résultat |
| --- | --- |
| `npm run check` (TypeScript, ESLint sans avertissement, build Vite) | Réussi |
| Tests Django, SQLite | **69 réussis**, 1 ignoré (test réservé à PostgreSQL) sur 70 : 40 existants + 30 nouveaux dans `shop/test_reliability.py` ; mêmes résultats sans fichiers statiques collectés |
| Tests Django, PostgreSQL 17 (conteneur jetable) | **70 réussis**, base de test détruite |
| `makemigrations --check`, `check` | Aucun changement manquant, aucune anomalie |
| Playwright, instance isolée SQLite (`npm run test:e2e:isolated`) | **41 réussis** (23 existants + 18 nouveaux : 9 scénarios × ordinateur et mobile) |
| Playwright, pile Docker reconstruite (Nginx + gunicorn + PostgreSQL 17, projet `stc-e2e` jetable) | **41 réussis**, commandes persistées dans PostgreSQL, compteurs de débit présents dans `stc_cache`, aucune trace d'erreur dans les journaux |
| Actualisation de la liste des commandes derrière Nginx (CSP `script-src 'self'`) | Rechargement après 30 s au repos, aucun rechargement pendant une sélection, aucune erreur CSP |
| `check --deploy --fail-level WARNING` avec des paramètres de production | Aucun problème ; clé `sk_live_`, simulation hors démo et mode Stripe sans clés refusés au démarrage |
| Restauration de `backups/stc-20261025T131634Z.dump` dans une base isolée | Réussie, comptages identiques à la source (1 commande, 9 produits) |
| Restauration de `backups/stc-20261025T131634Z.sqlite3` sur une copie | `integrity_check` ok, 37 commandes conservées après la migration 0004 |
| `npm audit` / `pip-audit` | Aucune vulnérabilité connue |
| Captures 320, 390, 768 et 1440 px (`screenshots/audit-*.png`) | Aucun débordement horizontal, aucun contenu masqué par la navigation fixe, aucune erreur JavaScript (seul le 400 attendu du test de mot de passe refusé apparaît en console) |

Nature des preuves Stripe : les webhooks sont testés avec de **vraies signatures HMAC** (secret de test local, falsification, horodatage expiré, mode réel refusé). Les appels sortants vers Stripe (`Session.create/retrieve/expire`) sont simulés par des doubles, et les tests d'interface Stripe utilisent des réponses réseau simulées. **Aucun échange réel avec Stripe n'a été vérifié** : aucune clé de test n'est configurée.

## Instances non mises à jour

Le redémarrage de `npm run dev:all` (processus en cours depuis 08:09) a été refusé par le contrôle de permissions. Votre instance locale et l'instance Docker de revue (port 8080) exécutent donc encore l'ancien code, et leurs bases n'ont pas reçu les migrations 0004 et 0005. Sur PostgreSQL, exécuter `migrate` **avant** de démarrer le nouveau backend : sans la table `stc_cache`, les requêtes limitées en débit échoueraient. Pour les mettre à jour, suivre « Mise à jour d'une instance existante » dans [OPERATIONS.md](OPERATIONS.md).

## Problèmes restants

| Gravité | Point | Nature |
| --- | --- | --- |
| Bloquant commercial | Mentions légales, CGV, politique de confidentialité (RGPD), identité, SIRET, contact, allergènes réels, TVA et facturation | Informations métier à fournir ; rien n'a été inventé |
| Bloquant commercial | Paiement en ligne réel | Clés réelles volontairement refusées ; recette Stripe test à faire, puis décision (activation contrôlée, ou paiement sur place) |
| Bloquant production | Domaine, HTTPS, SMTP réel (délivrabilité), webhook Stripe public | Services externes non configurés |
| Moyen | Pas de double authentification sur `/admin/` | Évolution (dépendance à ajouter, par exemple django-otp) |
| Moyen | Budget de débit commun aux clients derrière une même IP ; compteurs en mémoire en développement SQLite | Choix de configuration (`ANON_THROTTLE_RATE`) |
| Moyen | Pas d'export des données personnelles en libre-service (RGPD) ; la suppression existe | Évolution ; durée de conservation des commandes à définir par le restaurant |
| Faible | Libellé « Accompagnements » en 4,5 à 7 px sur les plus petits mobiles (contrainte du design à 7 colonnes) | Accessibilité, à arbitrer avec le design |
| Faible | Images non optimisées (jusqu'à 416 Ko) | Performance ; visuels du design validé non modifiés |

## Étapes pour une mise en production

1. Fournir les informations et documents du restaurant, puis les saisir dans l'administration (identité, horaires, zone, frais, allergènes, photos réelles, notes vérifiées ou vides).
2. Préparer l'hôte, le DNS et les ports 80/443 ; créer le `.env` depuis `.env.production.example` (secrets uniques).
3. Configurer le SMTP et `STC_ORDER_NOTIFICATION_EMAIL` ; vérifier la réception d'une réinitialisation et d'une confirmation.
4. Renseigner les clés Stripe **test** et le webhook public, puis faire la recette réelle : paiement accepté, refusé, expiré, annulé depuis l'administration, remboursé.
5. Construire, migrer et lancer selon [OPERATIONS.md](OPERATIONS.md) ; exécuter `check --deploy` ; planifier `cancel_stale_orders` et les sauvegardes chiffrées hors serveur, puis tester une restauration.
6. Décider du mode de paiement commercial ; toute activation de clés réelles doit faire l'objet d'une évolution et d'une validation distinctes.
