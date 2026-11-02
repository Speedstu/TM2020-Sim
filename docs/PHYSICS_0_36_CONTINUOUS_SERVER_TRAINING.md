# Recherche 0.36 — moteur officiel continu et entraînement causal

Reprise de l'archive privée du 29 octobre 2026 dans
`/home/uwucode/Projects/Trackmania2020-RE`. Le SDK reste en version 0.26.0.

Le nouveau backend fait avancer **le moteur officiel**, depuis le départ de
la course, et accepte une commande avant chaque lecture d'entrée de 10 ms.
Il fonctionne sous Linux x86-64, sans client graphique, compte connecté,
Openplanet, fork de checkpoint ou snapshot Windows. C'est un simulateur
utilisant le code original ; le simulateur indépendant complet reste inachevé.

## Reverse et fonctionnement

Le serveur est le même binaire SHA-256 que dans la recherche 0.35 :
`3b6107824feea402bd32c888e994dcd6df4a10afc8676a2647ac9560ccf0d779`.
L'analyse du projet TAS à la révision
`036a65ba6aaef87b4579b8ee5a770729341dc572` fournit le graphe de propriété du
validateur et le lecteur des entrées. La nouvelle instrumentation C++ utilise
trois sites dont elle vérifie les instructions :

| Site du serveur | Travail de l'adaptateur |
| --- | --- |
| `0x118c18a` | Retenir le contrôleur et la simulation, reproduire le stockage d'origine. |
| `0x1219f89` | Retenir les arguments du décodeur, reproduire son appel. |
| `0x1219f8e` | Observer le véhicule contrôlé, recevoir l'action puis poursuivre. |

Les INT3 ne modifient que les pages privées du processus lancé pour cet essai.
Les fichiers du serveur et ses Packs restent inchangés. Les trois instructions
interceptées sont émulées ; le décodeur et la simulation physique s'exécutent
dans le moteur original. Aucune estimation du nombre d'appels à `lroundf`
n'étiquette les états. Aucune reprise par fork n'est utilisée.

À chaque observation, l'adaptateur vérifie la relation contrôleur → simulation
→ playground → unique participant → `CGameVehiclePhy`. Le participant trouvé
dans le callback doit être celui du validateur. Il lit le quaternion WXYZ,
la position XYZ et la vitesse linéaire XYZ à partir de `vehicle+0x12e0`.
Ces dix flottants ne constituent **pas l'ensemble de l'état physique interne**.

Le reverse du décodeur `0x119f0f0` donne directement :

```text
raceMs = engineMs - originMs
inputIndex = floor((raceMs - startOffsetMs) / 10)
```

L'index est `-1` avant le début des entrées. Le record de 32 octets commence
par des flags ; les axes steer/gas/brake commencent à `participant+0x18c`,
quatre octets après le début du record. Les autres canaux du fichier sont
conservés. Modifier le mauvais début de record aurait écrasé les flags :
les essais différentiels portent sur les offsets corrigés.

`OfficialEngine.step((steer, gas, brake))` applique la commande à la frontière
courante et attend la suivante. `None` conserve la commande du fichier.
Une commande invalide est rejetée avant toute progression. Les changements
de course, trous d'horloge, états non finis et quaternions invalides provoquent
un échec explicite. `reset()` relance le serveur ; il n'existe pas de restauration
arbitraire d'état. Les observations sont des états avant consommation d'entrée,
sans supposer une équivalence avec la phase visuelle des replays.

## Domaine des comparaisons

Les essais rejouent identité, freinage, gauche, droite et roue libre. Le codec
Rust écrit les mêmes commandes dans un nouveau GBX, relit le fichier pour
vérifier les entrées, puis le serveur repart de zéro. Les dix flottants sont
comparés bit pour bit à chaque frontière **à partir de `raceMs=0`**, sans
décalage temporel ajusté. Le résultat final est également comparé à une
validation complète sans instrumentation. Un DNF reste un DNF.

Le contrôle final couvre **12 210 frontières de course** sur les cinq essais.
Les références humaines conservent leurs temps 22 730 ms et 23 013 ms.

Les buffers de construction du véhicule avant le départ ont présenté un écart
sur une répétition. Leur déterminisme n'est pas qualifié. Les traces du compte
à rebours sont conservées et les rapports comptent explicitement leurs écarts ;
aucune divergence après le départ n'est tolérée. L'environnement d'entraînement
commence exactement à la frontière zéro et ne présente pas ces buffers initiaux
à la politique.

Autumn 01 / replay 4634 donne aussi 19 967 ms et quatre checkpoints. Le champ
`IsValid` est cependant faux avec `unexcepted walltime (5s)`, **avec et sans
instrumentation**. Cet essai confirme une concordance des résultats calculés,
pas une acceptation complète du fichier par le validateur. Les champs déclarés,
calculés, `IsValid` et les descriptions doivent rester distincts.

## Entraînement réellement exécuté

Le PPO, l'inférence et Adam viennent du SDK C++ existant. Le nouvel exécutable
`tm2020_official_train` lance le serveur, échange les observations/actions et
entraîne le réseau **entièrement en C++**, sans processus Python. OpenSSL sert
uniquement aux SHA-256. L'adaptateur Python sert aux audits indépendants et à
une seconde implémentation de l'orchestration, sans bibliothèque de machine
learning ni implémentation des forces.

L'observation contient treize nombres : position relative/100, quaternion,
vitesse/100 et dernière commande appliquée. Elle ne contient aucune commande
future du replay, aucune trajectoire de référence ni position d'oracle.
Les actions PPO sont quantifiées en steer signé/127 et pédales binaires,
afin de pouvoir écrire les commandes exactes dans un ghost. L'API de bas niveau
accepte aussi les pédales continues, hors qualification différentielle présente.

La tâche actuelle dure **503 ticks, soit 5,03 secondes**. Une décision couvre
cinq ticks, sauf la dernière qui en couvre trois. La récompense est le déplacement
selon la direction initiale de la voiture, en mètres. Elle ne représente pas un
objectif général de course. Deux mises à jour de trois épisodes produisent
606 transitions ; une reprise de deux épisodes en ajoute 202. Chaque transition
est rejouée depuis un nouveau processus officiel : états intermédiaires,
observations, commandes, récompenses, durées et valeur du successeur sont
contrôlés. L'auditeur natif recalcule aussi les probabilités et valeurs du
comportement avant la mise à jour.

Le trainer C++ autonome reproduit les 303 transitions de la première mise à
jour : chaque empreinte physique, le CSV complet, le modèle et le checkpoint
avec Adam/RNG sont identiques octet pour octet à la collecte auditée. Les
reprises d'un même checkpoint sont également identiques. Ce sont des contrôles
de reproductibilité et d'intégrité, pas une preuve de force du bot.

L'évaluation déterministe du premier essai mesuré donne 105,191 m pour la
politique initiale configurée / plein gaz, 104,466 m après deux mises à jour,
puis 101,239 m après reprise. **La politique régresse** sur cette tâche. Les
modèles sont conservés comme résultats expérimentaux ; aucun meilleur bot de
course n'est établi ni déployé.

## Reproduire

Depuis la racine extraite, avec Python 3.11+, CMake, g++, les en-têtes OpenSSL,
Cargo et les dépendances Rust déjà en cache dans ce transfert :

```sh
python3 scripts/run_official_checks.py --train \
  --output local/recon/mon-nouvel-essai-officiel
```

La sortie doit être nouvelle. La commande compile le SDK Linux et le shim,
exécute les CTests portables, compile le helper Rust avec son lockfile hors
ligne, fige les binaires de l'essai, compare les commandes au serveur, puis
entraîne et audite le PPO. Elle vérifie aussi que deux reprises du même
checkpoint reproduisent exactement le rollout, les poids, Adam et les RNG.
Les journaux d'échec restent dans le dossier de sortie. Si les en-têtes OpenSSL
sont disponibles, la commande exécute aussi le trainer C++ autonome et compare
son CSV, ses poids et son checkpoint complet à l'implémentation orchestrée en
Python. Les empreintes de chaque état intermédiaire doivent aussi concorder.

Pour construire puis entraîner sans Python, depuis cette même racine :

```sh
cmake -S native -B native/build-linux -DCMAKE_BUILD_TYPE=Release
cmake --build native/build-linux -j 8
native/build-linux/tm2020_init_headless_policy \
  13 3 32 2026 \
  'tm2020_official_preinput13_v1|actions=ghost_binary_pedals_i8_steer_v1' \
  local/mon-initial.checkpoint
native/build-linux/tm2020_official_train \
  cache/TrackmaniaServer-official-2026-05-15 \
  cache/trackmania-tas-upstream-036a65b/tools/testdata/map2.Map.Gbx \
  cache/trackmania-tas-upstream-036a65b/tools/testdata/human_22730.Ghost.Gbx \
  native/build-linux/libtm2020_official_step.so \
  local/mon-initial.checkpoint local/mon-training-natif 3 503 5
```

Ce dernier exécutable effectue une mise à jour et écrit `training.checkpoint`,
`updated.tmppo`, `rollout.csv`, les empreintes physiques et les journaux du
serveur. Fournir son checkpoint à la place du checkpoint initial reprend
l'optimiseur et les générateurs aléatoires. Les chemins de sortie doivent être
nouveaux. La durée doit rester couverte par le fichier d'entrées fourni.

Résultats de la reprise : `local/recon/official-native-continuous-0.36/`.
Les explorations et résultats négatifs antérieurs sont conservés dans
`local/recon/linux-0.36/`.

Le build Linux exclut maintenant les outils Win32 de lecture/injection et
évite le conflit de nom `finite` de la libc. Les outils Windows restent
disponibles dans leur build d'origine. La bibliothèque statique est construite
en PIC pour les bibliothèques partagées Linux du SDK. Les 30 CTests portables
et un consommateur externe du SDK installé sous Linux passent.

## Ce qui reste à terminer

Le backend dépend du serveur de mai 2026, de ses Packs et d'un GBX qui fournit
la configuration de course et une durée d'entrées suffisante. Il ne démontre
pas l'équivalence générale avec le client d'octobre. Les resets par relance
sont plus coûteux que des savestates. Les identités de joueurs multiples,
commandes de respawn, canaux spéciaux et états arbitraires ne sont pas qualifiés.
La couverture de toutes les voitures, surfaces, cartes et mécaniques reste à
étendre. La fidélité des ports physiques indépendants et une politique capable
de gagner des courses restent des travaux séparés.
