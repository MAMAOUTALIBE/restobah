# Registre des constats et corrections

Référence initiale : `0c5c588`. Les états seront clôturés par les validations indépendantes ; les tests existants verts ne ferment pas les nouveaux défauts reproduits.

## État de référence exécuté

- `npm run check` : TypeScript, ESLint et build réussis.
- Django SQLite mémoire : **119 collectés, 118 réussis, un cas PostgreSQL ignoré**, 11,704 s.
- `python3 scripts/e2e.py --workers=1 --output=/tmp/stc-audit-baseline-browser-results` : **157 réussis**, 7,1 min, instance et médias jetables.
- Audit visuel indépendant : huit parcours réussis, 82 observations, 68 captures hors dépôt à 320/390/768/1280 px ; défaut clavier supplémentaire reproduit.
- Audit sécurité : 57 tests ciblés réussis, partiellement inclus dans les 119 cas, sans les additionner à nouveau.
- CI Linux du même commit : **154 réussis, trois échecs** de gabarit à 388 px. La réussite locale Mac ne ferme pas ce défaut.
- Sauvegarde PostgreSQL publiée restaurée réellement en isolation : huit comptages métier conformes ; cela ne prouve pas l’existence d’une copie extérieure planifiée.

## Registre à clôturer

| ID | Priorité | Constat confirmé et preuve | Lot / état initial |
|---|---|---|---|
| REL-01 | P1 | Panier figé sur les anciens frais/modes/pause après prévalidation. Reproduction API mockées, zéro POST métier. | B — PASS indépendant |
| REL-02 | P2 | Action CRM perd recherche/page en succès et en conflit. Formulaires réels, 31 commandes filtrées et une étrangère. | B — PASS indépendant |
| REL-03 | P1 | Formulaire restaurant refusé annonçant une pause non enregistrée : base `true`, contexte `false`. | B — PASS indépendant |
| REL-04 | P2 | Lundi 01h, service de dimanche jusqu’à 02h : `isOpen=true` mais résumé « Fermé ». | B — PASS indépendant |
| REL-05 | P2 | Catégories malformées (chiffres Unicode ou chaîne trop longue) provoquant une erreur serveur. | B — PASS indépendant |
| UI-01 | P2 | Tab quitte le panier pendant validation : `activeElement=BODY`, champs désactivés ; POST intercepté. | B — PASS indépendant |
| UI-02 | P1 recette | Hauteur des cartes différente sur Linux : trois échecs CI, écart 13,671875 px à 388 px. | D — PASS Linux 24 cas ; CI complète après commit |
| SEC-01 | P2 | Six GET API personnels sans `no-store`. Autorisations intactes, aucune lecture étrangère démontrée. | D — PASS ; cache privé et régressions |
| SEC-02 | P2 | Minimatch vulnérable entraîne onze alertes modérées de développement ; production JS/Python sans alerte connue. | D — PASS ; override 11.0.3, audits complets sans alerte |
| OPS-01 | P1 recette | Connexions persistantes inadaptées à runserver multithreadé : saturation CI, rétention accrue vérifiée. | D — corrigé, recette PG passée ; charge CI finale à confirmer |
| OPS-02 | P1 livraison | `compose.vps.yaml` absent du paquet, omission reproduite sur fixture. | E — PASS ; fixtures et intégration |
| OPS-03 | P2 | SQLite corrompu laisse une sauvegarde finale vide après exception. | E — PASS ; fixtures et intégration |
| OPS-04 | P1 | Runtime/e-mails privés non persistants au recreate ordinaire ; montage média seul confirmé. | E — PASS ; recréation et vraie restauration |
| OPS-05 | P1 | Sauvegardes ponctuelles présentes ; aucun planning STC ni copie extérieure confirmé. | E — outils et timers validés ; installation après publication, extérieur non fourni |
| BUS-01 | P0 commercial | Mode réel avec règlement physique inexistant : simulation/Stripe test seuls au départ. | C — PASS indépendant ; origine, registre et migration |
| BUS-02 | Externe | Données/documents client, domaine et SMTP réel non fournis ; configuration actuelle de démonstration. | Précontrôle et dossier de livraison |

## Règles de clôture

Pour chaque correction : fichiers, reproduction, contrôle après correction et revue indépendante. La recette finale inclura PostgreSQL et Linux ; les preuves de publication resteront distinctes des preuves de test. Les détails des contrôles figurent dans les rapports 02 à 05.

Aucun secret, document légal ou renseignement client ne sera inventé ou ajouté à Git. Les écritures de recette restent jetables et les données du site existant sont conservées.

## Défauts supplémentaires découverts pendant la relecture

- Réécriture interne du registre par upsert ou instance au même identifiant : deux tests rouges, gardes corrigées et tests PostgreSQL verts ; aucun contournement HTTP démontré.
- SEC-04 : ancien modèle incapable d’insérer après migration ; défaut SQL durable ajouté et vrai INSERT historique testé. Compatibilité limitée au repli de la démonstration en simulation.
- SEC-05 : alias internes de santé provoquant un faux blocage ; domaine public exact et trois alias autorisés, 22 tests ciblés et probe indépendant verts.
- SEC-06 : ancien membre du personnel avec trace financière, ensuite devenu client, obtenant une erreur 500 à la suppression ; refus métier 400 sans suppression partielle, protection du registre et cache privé conservés. Tests ciblés puis recette finale du code figé.
- Restauration des médias : modes publics explicitement rétablis après extraction privée ; lecture réelle par nginx et refus d’accès aux fichiers privés vérifiés.

Les conditions d’ouverture commerciale de BUS-02 restent externes et sont listées dans FINAL.md et CLIENT-DELIVERY.md. Les contrôles ne sont pas présentés comme une garantie absolue.
