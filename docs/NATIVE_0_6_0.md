# SDK natif 0.6.0 — résultats et limites

Le bot de référence a terminé **Automne 2026 - 01** dans le vrai jeu.
L’écran de résultats et le replay automatiquement sauvegardé par Trackmania
confirment **1:06.049**. Ce temps contient environ 34 secondes d’attente au
départ pendant la recherche mémoire ; il ne faut pas annoncer un chrono
officiel de 32 secondes. Le pilote utilise une trajectoire de démonstration
connue et de la rétroaction, pas un réseau entraîné à gagner la course.

Les anciennes tentatives et les échecs restent dans `local/recon`.
Le rapport `live-driving-qualification.json` recense les traces et les
démarrages refusés, dont une arrivée confirmée. Ces expériences ont des réglages et durées différents :
ce nombre n’est pas un taux de réussite. La reproductibilité des arrivées
reste à améliorer.

## Preuves de l’arrivée

- `local/recon/codex-follower-tracking-v4.csv` : parcours jusqu’à la fin,
  erreur maximale par rapport à la référence 9,424 m.
- `local/recon/finish-tracking-v4.jpg` : écran de résultats.
- `local/recon/bot-tracking-v4.Replay.Gbx` : replay produit par le jeu.
- `local/recon/bot-tracking-v4-replay.json` : extraction GBX.NET, temps
  `1:06.049`, 1 424 changements d’entrée.
- `local/recon/finish-tracking-v4.json` : liens et SHA-256 des preuves.

Le pilote redémarre maintenant normalement la course **après** le scan ou la
validation du cache. L’ancien critère « le lookahead touche le dernier point »
relâchait l’accélérateur avant la rampe finale ; le nouveau critère attend le
franchissement géométrique du dernier point. Cela ne remplace toujours pas un
compteur d’arrivée récupéré dans le moteur.

## Travail de reverse et calibration

La base reste l’exécutable SHA-256
`3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda` :
386 inscriptions de classes et 1 705 propriétés, dont la structure visuelle
`CSceneVehicleVisState` de 0x360 octets. Les preuves d’instructions et les
offsets sont détaillés dans [le rapport précédent](NATIVE_0_5_0.md).

Un balayage bidirectionnel de direction, voiture immobile et sans accélérer,
a identifié une zone morte proche de **10 %**, suivie d’une quantification
signée à **127 niveaux par sens**. Sur cet essai, l’intervalle compatible de
zone morte est `[0.092857, 0.100417]`. Il s’agit des réglages de cette session,
pas d’une constante garantie pour tous les joueurs.

```powershell
native/build/tm2020_local_probe.exe --confirm-local-solo `
  local/recon/live-cpp-12172-v3.txt local/recon/calibration.csv calibrate `
  tools/vigem/ViGEmClient.dll 25
python scripts/analyze_input_calibration.py `
  local/recon/calibration.csv local/recon/actuator-calibration.json
```

L’inverse calibré est dans `tm2020/actuator.hpp`. L’erreur de reconstruction
est bornée à un demi-pas de 1/127 par le test natif. Le client ViGEm est copié
sur H: dans `tools/vigem`, SHA-256
`2bf0cb1d809039573c922737d298a1653d4dbc61408060ff45a9bcfde82e97d2`.
Le runtime utilise cette DLL native et le pilote ViGEmBus déjà installé ;
il n’exécute pas Python.

Les entrées réelles et les valeurs compressées du replay sont distinguées :
`live_steer_from_raw(0)` vaut zéro, tandis que l’ancienne conversion
`analog_steer_from_raw` conserve le centrage des labels GBX compressés.
`scripts/compare_live_input_encoding.py` compare 585 observations stabilisées
au replay du bot, avec un décalage fixé à zéro : MAE 0,000781 pour `raw/127`,
contre 0,004668 pour le centrage GBX. Le mode de rejeu d’entrées utilise
désormais la conversion réelle.

La sélection des états visuels vérifie le tag, sépare les générations de
course, traite les horloges circulaires et empêche un ancien tampon avec
accélération de masquer indéfiniment un état de freinage ou de roue libre.
Le quorum ne compte plus les copies d’une autre génération. Un cache
temporaire est lié au PID, à la création du processus et au SHA du jeu ; sa
restauration exige des états cohérents et une horloge qui avance. Il peut
être rejeté et rescanné. Ce n’est pas un pointeur propriétaire permanent.

## Pilotage et PPO natifs

`propose_tracking_controls` expose le contrôleur dans le SDK : commandes
lissées de la démonstration, correction de cap et de déport, adaptation à
la vitesse réelle, garde de survitesse. Le host dispose de quatre tentatives
limitées de dégagement en marche arrière. Les traces enregistrent commandes
voulues, envoyées et reçues, horloge, génération, PID du host et dégagements.

```powershell
native/build/tm2020_live_drive.exe --confirm-local-solo `
  local/recon/live-cpp-12172-v3.txt `
  local/campaign-2026-autumn/native-replays/4634.tmreplay `
  local/recon/codex-follower-local.csv gamepad `
  tools/vigem/ViGEmClient.dll 55 24 -3 --tracking --deadzone 0.1
```

Le nouvel adaptateur PPO ajoute un résidu de direction limité à ±0,2 au
contrôleur, avec huit observations de route et une décision nominale toutes
les 100 ms d’horloge visuelle. Il conserve observations, actions latentes,
log-probabilités et valeurs de la politique qui a collecté les données.
Le modèle reste inchangé pendant la collecte. PPO vérifie cette identité
avant la mise à jour.

Le GAE tient compte de la durée mesurée : `gamma^duration` et
`lambda^duration`. Les préfixes complets sont tronqués avec bootstrap sur
leur vraie dernière observation ; l’action finale sans observation suivante
est écartée. Une arrivée géométrique n’est pas étiquetée comme terminal du
moteur. La récompense concerne la progression sur la référence, le déport et
le temps, pas un score compétitif récupéré dans le jeu.

```powershell
scripts/run-local-ppo.ps1 -ConfirmLocalSolo -Episodes 3 -Seconds 40
```

Chaque session garde `.behavior.tmppo`, `.rollout.csv`, `.ppo.csv` et le
modèle résultant. Les poids sont remplacés atomiquement après neutralisation
des commandes. Les moments Adam ne sont pas restaurés entre les processus ;
ce n’est pas encore un checkpoint complet d’entraînement. Le seed fixe ne
rend pas le jeu temps réel déterministe.

**Collecte PPO dans le vrai jeu et amélioration de performance : non
qualifiées.** Les tests du collecteur vérifient chronologie, durée, maintien
des actions, identité on-policy et bootstrap ; ils n’établissent pas la
force du bot. Le warmstart BC historique reste inférieur au contrôleur
de poursuite sur ses labels hors entraînement.

## DLL injectée : implémentation, échec et réparation

`libtm2020_runtime.dll` expose l’ABI Windows `tm2020/runtime.h` : un probe
et une entrée de worker explicite. Charger la DLL ne démarre aucun bot.
L’entrée lit un fichier d’arguments versionné, vérifie son processus,
sérialise les workers par mutex et utilise la même boucle que le host.
Les contrôles passent par les entrées normales du jeu ; aucun hook physique
ou patch du code du jeu n’est installé.

```powershell
scripts/run-injected-bot.ps1 -ConfirmLocalSolo -Seconds 55
# Ajout du résidu PPO expérimental :
scripts/run-injected-bot.ps1 -ConfirmLocalSolo `
  -PpoModel H:/Projects/Trackmania2020-RE/local/native-datasets/residual.tmppo
```

Le script conserve une copie de DLL nommée par son hash, sa configuration,
le statut du worker et les PID des observations. Une DLL déjà chargée
n’est jamais remplacée. Une attente expirée ne provoque pas de terminaison
forcée du thread ni de libération de paramètres encore en cours d’utilisation.

Le premier worker a fait fermer le jeu. L’analyse statique de l’ancienne
DLL retrouve, à RVA **0x98f0**, `mov eax, 0x1002a8`, un appel de vérification
de pile puis `sub rsp, rax` : **1 049 256 octets**, davantage que la réserve
de pile de **1 048 576 octets** du PE du jeu. Le tampon SHA de 1 Mio est
maintenant alloué sur le tas ; le loader réserve explicitement 8 Mio pour
le worker. Le test SHA traite plus de 2 Mio dans un thread de 256 Kio et
vérifie le digest attendu.

Windows a enregistré une instruction `ud2` à RVA **0x11da01** du jeu,
dans le chemin associé à `CFastLinearAllocator::Alloc overflow`. Le
dépassement de réserve dans le SDK est prouvé statiquement. Le lien entre
l’exception initiale et ce diagnostic fatal reste une inférence, faute de
dump de pile d’origine. Reproduction : `scripts/analyze_runtime_stack.py`.

Après réparation, le worker est entré dans le processus 12172, a écrit son
statut et est revenu proprement en échec de précondition ou de télémétrie.
**Un pilotage injecté terminé n’est pas qualifié.** Les erreurs et les traces
restent dans `local/recon/injected-v*-*.json`, `injected-v*.json` et les
sidecars `.error.txt`. La demande Windows « Steam Client Service » est
restée ouverte lors de cette phase ; le jeu a été relancé directement,
sans accorder cette élévation.

## Vérification et état réel

```powershell
scripts/run-release-checks.ps1
scripts/status.ps1
```

Les 16 groupes historiques et les sept tests CTest passent. L’installation
CMake et la liaison Rust/MSVC vers la DLL C/MinGW sont vérifiées. Le paquet
est dans `dist/sdk-windows-x64`, les sources dans
`backups/trackmania2020-re-source-0.6.0.zip`. Les ABI policy 1 et bridge 3
sont conservées.

Il manque toujours un propriétaire joueur/physique stable entre processus,
un callback de simulation et un compteur d’arrivée fiables, les collisions
Stadium complètes, une physique différentiellement fidèle et une validation
compétitive indépendante du PPO. Le simulateur expérimental existant ne
reproduit pas Trackmania. Cette version constitue une progression vérifiée
du projet de recherche ; elle ne justifie pas le titre de « meilleur bot »
ou de framework d’entraînement exact et terminé.
