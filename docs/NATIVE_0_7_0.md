# SDK natif 0.7.0 — pilotage injecté, PPO réel et reprise d’entraînement

Le worker C++ injecté par LoadLibrary a terminé Automne 2026 - 01 en
**24,114 s, médaille d’or**. L’écran du jeu et son replay sauvegardé sont
concordants. Le second essai du même contrôleur donne 32,643 s avec une
récupération en marche arrière : la variabilité reste importante.

| Essai conservé | Résultat | Source de mesure |
|---|---|---|
| `injected-v10` — référence, aucun résidu appris | **24,114 s**, or | Écran et replay automatique |
| `injected-baseline-v11` — mêmes réglages | **32,643 s** | Écran et replay sauvegardé |
| `injected-ppo-v1` — collecte exploratoire | Arrêt après quatre récupérations | Trace et erreur conservées ; préfixe PPO valide |
| `injected-ppo-v2` — reprise entraînement | Endpoint atteint, worker revenu normalement | Trace ; chrono officiel non archivé pour cet essai |
| `injected-eval-v1` — modèle appris sans exploration | **31,555 s** | Écran : 24,114 + 7,441 ; replay sauvegardé : 31,555 |

Ce sont des essais de développement sur un seul circuit connu, pas une
comparaison statistique ni une preuve de supériorité du PPO. Le contrôleur
par défaut reste le suivi de référence qui possède le meilleur chrono
confirmé. Il utilise une démonstration et un retour de position/orientation.

## Utilisation locale

Depuis `H:\Projects\Trackmania2020-RE`, avec le jeu au premier plan dans
une course Solo active d’Automne 2026 - 01 :

```powershell
./scripts/run-native-live-bootstrap.ps1 -ConfirmLocalSolo -Samples 30
./scripts/run-injected-bot.ps1 -ConfirmLocalSolo -Seconds 55
```

Le bootstrap est lié au PID, à son instant de création et au SHA256 du
jeu. Les adresses sont éphémères. Après un redémarrage du jeu, refaire le
bootstrap. La découverte des copies visuelles peut prendre plusieurs
dizaines de secondes. Le pilote vérifie ensuite un nouveau départ, sa
position et une horloge qui avance ; cette découverte n’entre plus dans
le chrono qualifié de 24,114 s.

Le premier lancement de cette session a rencontré un échec de création de
manette ViGEm, `0xe0000007`. Un lancement suivant a réussi sans changer de
pilote ni élever les privilèges. L’ajout de périphérique peut bloquer dans
la bibliothèque ViGEm ; ce délai n’est pas borné par la durée de pilotage.
Les échecs `v7`, `v8`, `v9`, ainsi que ceux de 0.6, restent conservés.
La source officielle de [ViGEmClient](https://github.com/nefarius/ViGEmClient/blob/master/src/ViGEmClient.cpp)
montre l’attente du périphérique opérationnel et le chemin d’erreur ; la
cause système précise du premier échec n’a pas été établie.

L’injection charge explicitement notre DLL puis appelle notre worker.
Le bot, la lecture, les décisions et les mises à jour s’exécutent dans
Trackmania ; les commandes passent par les entrées normales clavier/manette.
Aucun hook de physique, patch d’instruction ou propriétaire physique validé
n’est revendiqué. L’observation reste `CSceneVehicleVisState`.
Les contrôles sont relâchés à la fin, à la perte du focus ou sur erreur.
Échap permet d’interrompre le pilotage.

## Entraîner et évaluer

```powershell
# Un épisode avec mise à jour réelle sur les transitions complètes.
./scripts/run-injected-bot.ps1 -ConfirmLocalSolo -Seconds 55 `
  -PpoModel local/native-datasets/live-residual-v2.tmppo

# Une évaluation du modèle existant, sans bruit et sans mise à jour.
./scripts/run-injected-bot.ps1 -ConfirmLocalSolo -Seconds 55 `
  -PpoModel local/native-datasets/live-residual-v2.tmppo -Evaluate

# Variante externe ; -Evaluate est également disponible.
./scripts/run-local-ppo.ps1 -ConfirmLocalSolo -Episodes 3 -Seconds 40
```

Les deux mises à jour réelles comprennent respectivement **285 et 317
transitions**, chacune avec quatre epochs et vingt minibatches. Le modèle
reste inchangé pendant une collecte. Les anciennes valeurs et probabilités
sont vérifiées avant la mise à jour. Les intervalles réellement mesurés
entrent dans GAE ; un préfixe interrompu bootstrappe et reste tronqué.
La récompense décrit la progression sur la référence, pas le score du jeu.
Le premier épisode échoué a produit une mise à jour sur son préfixe valide.

L’outil indépendant `tm2020_rollout_audit` recharge chaque `.behavior.tmppo`
et recalcule les anciennes log-probabilités et valeurs de **toutes les 602
transitions**. Les écarts mesurés sont exactement zéro sur cette build.
Les `.rollout.csv`, `.ppo.csv`, traces et erreurs restent disponibles.

L’évaluation possède une voie distincte : action déterministe tenue pendant
100 ms, aucune création de rollout, aucun optimizer ni sauvegarde du modèle.
Le SHA256 du modèle d’évaluation est resté
`68a81f33155bcf189269b58dfe1bc783d7c6a01ab383c9c1e4e70cf00b634992`.
L’évaluation de 31,555 s ne justifie pas de
promouvoir ce modèle devant le contrôleur de référence.

## Checkpoint d’entraînement complet

`PpoTrainer::save_checkpoint` / `load_checkpoint` ajoutent le format
**TMTRAIN1**, indépendant du modèle d’inférence **TMPPO001** déjà utilisé
par les ABI C et Rust. Il contient : politique, critique, log-écarts-types,
moments Adam, compteur de minibatches, hyperparamètres, RNG de mélange et
RNG d’échantillonnage de la collecte. Il se sauvegarde entre les rollouts.
Le snapshot du monde, les entrées déjà jouées et un épisode en cours ne
sont pas restaurés.

Le pilote écrit `modele.tmppo.train` avant l’export d’inférence. Ce fichier
complet est la source de reprise ; un crash entre les deux exports ne fait
pas perdre Adam. Les anciens fichiers d’inférence peuvent initialiser une
nouvelle session avec Adam vierge, ce qui est indiqué dans les métriques.
Le checkpoint réel atteint **40 pas Adam**, et le second essai indique
`adam_state_restored=1`.

Écriture Windows : création exclusive du `.tmp`, écriture et
`FlushFileBuffers`, fermeture, remplacement par `MoveFileExW` avec
`WRITE_THROUGH`. Un ancien temporaire est préservé et provoque une erreur.
Les écritures concurrentes sur un même modèle doivent être sérialisées par
l’appelant. Chargement : taille bornée, checksum, schéma, architecture,
dimensions, nombres finis et RNG sont validés avant toute mutation.
Le checksum FNV détecte une corruption accidentelle ; il n’authentifie pas
un fichier hostile. L’égalité exacte de reprise est qualifiée avec le même
compilateur et la même bibliothèque standard, pas entre tous les runtimes.

## Reverse supplémentaire

`scripts/reverse_member_types.py` suit des constructeurs de descripteurs
dans les bornes `.pdata` et reconnaît des getters feuilles complets.
Il extrait **1 453 relations de types**, avec instructions et octets de preuve,
en plus des 386 classes et 1 705 propriétés précédemment récupérées.

`CSceneVehicleVis::AsyncState` à `0x130` référence le type enregistré
**CSceneVehicleVisState**, ID **0x0a00c000**, getter `0x726420`, constructeur
de descripteur `0x740140`. Le mode brut du descripteur est **1** ; sa
sémantique de stockage n’est pas interprétée. Il ne permet toujours pas de
soustraire 0x130 à une copie visuelle pour en déduire un propriétaire.
Le tag des snapshots `0x02000006` n’est pas cet ID de classe.

Un nouveau relevé borné du PID 17776 a trouvé trois horloges qui avancent
parmi dix-neuf copies décodables. Cela corrobore l’existence de buffers
actifs et périmés ; cela ne prouve aucune racine physique stable.

## Validation et preuves

```powershell
./scripts/run-release-checks.ps1
./scripts/status.ps1
```

La validation regroupe les seize groupes historiques, huit tests CTest,
le consommateur CMake externe, les ABI C/Rust, le lint Rust, la réflexion
SHA-pinnée et l’audit des collectes réelles. Le test de reprise compare
quatre mises à jour avec une exécution ininterrompue, bit pour bit ; il
vérifie aussi qu’un checkpoint rejeté ne modifie pas l’état caché d’Adam.

La première validation complète a révélé une course au démarrage du
processus de test du chargeur : son inventaire de modules pouvait être
demandé avant l’initialisation. Le fixture signale désormais explicitement
qu’il est prêt. L’inventaire réessaie seulement `ERROR_BAD_LENGTH`, dans
une limite de cent tentatives, conformément au comportement documenté de
[CreateToolhelp32Snapshot](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot).
Les deux tests de chargement ont ensuite chacun réussi trente répétitions.
Le journal initial de l’échec est conservé ; les huit tests et les checks
de release ont été relancés après réparation.

Preuves locales principales :

- `local/recon/finish-injected-v10.json` + PNG + replay du jeu : 24,114 s.
- `local/recon/finish-injected-baseline-v11.json` : 32,643 s.
- `local/recon/finish-injected-eval-v1.json` : 31,555 s, modèle évalué.
- `local/recon/injected-learning-qualification.json` : essais, échecs, audit.
- `local/recon/live-driving-qualification.json` : toutes les traces retenues.
- `local/recon/reflected-member-types.json` : graphe de types et instructions.
- `local/release-0.7.0.json` : validation et capacités historiques vérifiées.

SDK installé : `dist/sdk-windows-x64`. Sources sauvegardées :
`backups/trackmania2020-re-source-0.7.0.zip` et son SHA256. Les assets du jeu,
outils tiers et preuves locales ne sont pas inclus dans l’archive de sources.
Les preuves et modèles de cette qualification sont sauvegardés séparément
dans `backups/trackmania2020-re-evidence-0.7.0.zip`, avec leurs chemins locaux
et les modules SDK nécessaires à la vérification de leurs hashes.
L’exécutable du jeu conserve son SHA256 original
`3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda`.

La physique Stadium fidèle, le propriétaire physique autoritaire, un
`step/reset/rewind` exact et la généralisation compétitive restent des travaux
non réalisés. Le SDK livré sait piloter et entraîner réellement dans cette
course Solo ; il ne constitue pas encore un simulateur Trackmania autonome.
