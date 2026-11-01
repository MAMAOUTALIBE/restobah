# Corrections UI — modales et cartes mobiles

Date : 1er novembre 2026. Rôle d’implémentation UI, avec le skill `project-coder`. Les écritures sont limitées aux composants et régressions ci-dessous ; aucune base, donnée client ou configuration en ligne n’a été modifiée.

## Périmètre

- `src/components/Modal.tsx`
- `src/components/ProductCard.css`
- `tests/modal-focus.spec.ts`
- `tests/product-cards.spec.ts` : ajout de largeurs de régression, sans modifier les assertions ni leur tolérance.

## Focus de la modale

Le défaut de départ est reproduit dans l’audit des pages : pendant l’envoi d’une commande, les champs désactivés par leur `fieldset` étaient encore comptés comme contrôles focalisables. Tab pouvait alors sortir du dialogue.

Le calcul exclut maintenant les éléments réellement `:disabled`, invisibles ou inertes. Tab et Maj+Tab restent dans la fenêtre, même si le contrôle actif vient d’être désactivé ou si aucun contrôle n’est actif. Échap, le retour du focus et la valeur précédente du verrouillage du défilement sont conservés.

Un second cas réel a été testé avant de figer le correctif : la notification d’ajout, au-dessus d’une fiche plat, peut ouvrir le panier et produire deux modales. Le test échouait avant la gestion de pile. Désormais seule la modale supérieure traite focus et Échap ; les fenêtres inférieures deviennent inertes et masquées aux technologies d’assistance, puis sont réactivées. Le défilement demeure verrouillé tant qu’une fenêtre reste ouverte.

Les quatre scénarios durables couvrent la navigation et le retour du focus, l’absence de contrôle actif, l’ouverture du panier depuis la notification et l’envoi occupé suivi d’une erreur 503 contrôlée. Cette dernière est interceptée avant tout serveur métier et ne crée aucune commande.

**Contrôle de développement Mac : 12 tests réussis**, soit quatre scénarios sur ordinateur, tablette et mobile, en 16,2 s. ESLint ciblé, TypeScript et `git diff --check` réussissent. La revue indépendante est effectuée séparément par le validateur du lot.

## Hauteur des cartes sous Linux

L’écart de la CI a été reproduit avec **l’image officielle Playwright 1.64.1 Noble**, Chromium Linux arm64 et les véritables polices du site chargées. Le diagnostic lit les fixtures publiques des tests, intercepte toutes les API et n’utilise pas de base.

Avant correction, les largeurs **388 et 390 px** présentent exactement **13,671875 px** d’écart : la formule mesure 115,671875 px, contre 102 px pour les autres catégories. Sa description occupe deux lignes sous Linux ; le palier de 116 px s’arrêtait à 387 px. Ce n’est donc pas un échec à masquer en augmentant la tolérance.

Le seul changement de gabarit prolonge ce palier jusqu’à **395 px**. À partir de 396 px, la description de la fixture tient sur une ligne ; le gabarit de 102 px reste disponible. Les marges crème, la colonne image à 50 %, les prix et les actions de 44 px sont conservés.

Après correction, le diagnostic obtient **zéro écart** sur ses treize largeurs : 320, 360, 364, 365, 375, 387, 388, 390, 400, 410, 420, 430 et 760 px. Le test durable ajoute notamment les deux bornes 395/396 et conserve les vérifications d’alignement, de cadrage, de débordement et de zone tactile.

Preuves hors dépôt : `/tmp/stc-ui-linux/before.json` et `after.json`. Les premiers essais de panier à travers le nom de passerelle Docker ne fournissaient pas de contexte sécurisé à Web Crypto ; ils ne sont pas comptés comme validation du panier. Le lot final utilise un relais TCP interne sur `localhost`, comme la CI, sans désactiver la vérification TLS du site public ni changer le code de paiement.

## Validation finale Linux

**24 tests réussis en 42,4 s** : douze contrôles de cartes et douze contrôles de modale, sur ordinateur, tablette et mobile. Les relances Mac et les essais intermédiaires ne sont pas ajoutés à ce total. Les résultats et le harnais sont dans `/tmp/stc-ui-linux/linux-loopback-final-results` et `run-tests.cjs`. La commande de reproduction utilise le dépôt monté en lecture seule et un répertoire d’artefacts distinct :

```sh
docker run --rm --ipc=host \
  --mount type=bind,src=/Users/bahmamadou/Desktop/restobah,dst=/work,readonly \
  --mount type=bind,src=/tmp/stc-ui-linux,dst=/artifacts \
  --workdir /work mcr.microsoft.com/playwright:v1.64.1-noble \
  node /artifacts/run-tests.cjs
```

Les fichiers `/tmp` sont des preuves locales de cette exécution, pas des ressources de production. La recette Linux ne remplace pas la recette finale PostgreSQL ni la CI complète du coordinateur.
