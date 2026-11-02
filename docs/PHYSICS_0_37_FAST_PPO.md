# Recherche 0.37 — simulateur Linux headless et PPO vectorisé

Le client Steam installé a été trouvé dans la bibliothèque Flatpak :
`~/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/Trackmania`.
Son exécutable correspond au SHA-256 client déjà identifié par le projet.
Les fichiers installés restent inchangés. Aucun client graphique, Openplanet,
Gymnasium, PyTorch ni GPU n'est nécessaire au simulateur et au trainer natif.

La physique rapide provient de **Gearbox**, par Bagautdin Omarov et ses
contributeurs, révision `e0583ee55168e950a65a645778e591bd26b6a0f2`, GPL-3.0-or-later.
Ce travail ajoute le port Linux hors ligne, l'environnement causal, les
mondes parallèles, les resets complets, la collecte PPO native, l'anticipation,
les audits et l'évaluation. Il ne revendique pas d'avoir nouvellement reversé
tout le moteur. Voir [la licence et les attributions](../integrations/fast-training/NOTICE.md).

## Exécution

Depuis la racine du transfert extrait, compiler une fois :

```sh
python3 scripts/run_fast_ppo.py build
python3 scripts/run_fast_ppo.py checks --output local/mes-controles
```

Le build utilise Cargo hors ligne avec lockfile, Rust 1.98, CMake et C++20.
La bibliothèque système `liblzo2.so.2` doit être présente. Les sources et
dépendances en cache du transfert sont nécessaires. Le script détecte Steam
classique et Flatpak, ainsi que les bibliothèques `libraryfolders.vdf`.
`--packs`, `--map` et `--route` permettent de fournir explicitement les chemins.

Entraîner le bot avec anticipation physique et correction PPO :

```sh
python3 scripts/run_fast_ppo.py train --updates 8 --output local/mon-ppo
python3 scripts/run_fast_ppo.py eval --trials 10 \
  --model local/mon-ppo/best.tmppo --output local/mon-evaluation
```

Le modèle sélectionné pendant cette recherche est
`local/recon/fast-0.37/release-candidate/policy.tmppo`.
Les dossiers de sortie doivent être nouveaux. Pour arrêter proprement entre
deux mises à jour, créer un fichier `STOP` dans le dossier d'entraînement.
`--resume .../training.checkpoint` reprend Adam, la configuration PPO et les
RNG ; les environnements physiques repartent de nouveaux resets. Cela ne
reproduit pas une interruption au milieu d'une course.

Pour entraîner un réseau sans recherche physique à l'inférence :

```sh
python3 scripts/run_fast_ppo.py train --controller geometric --updates 600 \
  --output local/mon-ppo-reseau
python3 scripts/run_fast_ppo.py bench --output local/mon-benchmark
```

Les deux modes utilisent des schémas de politique différents et refusent de
charger un modèle incompatible. Un réseau initialisé à zéro corrige une
commande de référence, puis PPO apprend son résidu. Le mode `geometric`
utilise une poursuite géométrique. Le mode `anticipation` compare 17 braquages
constants sur 600 ms de **physique réelle du simulateur**, puis utilise le
réseau PPO comme correcteur borné à ±0,05 de braquage. Il est beaucoup plus
coûteux : le débit brut du simulateur ne doit pas être présenté comme le débit
PPO de cette recherche arborescente.

## Environnement

La bibliothèque Rust `libtm2020_fast.so` expose une ABI C version 4. Un état
fait 544 octets, dont 48 observations et les 22 mots du corps rigide.
`fast_training.h` documente le contrat. Chaque environnement possède son
véhicule, son état dynamique, son historique d'entrées et ses RNG ; le monde
initial et les configurations peuvent être partagés par Arc avec copie à
l'écriture. Les actions n'écrivent jamais la position ou les checkpoints.

Une décision couvre cinq ticks de 10 ms. Les pédales sont binaires et le
braquage est quantifié en entier signé/127, comme dans le ghost original.
L'arrivée et les checkpoints viennent des vrais événements de course du moteur.
La fin d'horizon respecte les actions partielles. L'environnement tronque les
voitures bloquées ou très éloignées de la route et refuse d'avancer après
terminaison, troncature ou erreur physique partielle.

Les observations contiennent vitesse locale, vitesse angulaire, verticale,
points de route devant le véhicule, erreur latérale, dernière commande,
progression, temps restant, commande de référence et état actuel de la
direction, des roues, du moteur et des contacts. La route vient des positions
du replay ; **les futures commandes, vitesses cibles et temps du replay
n'entrent pas dans les observations**. Le bot connaît donc une route de
référence : il n'explore pas une carte inconnue à partir d'images.

Les resets de curriculum restaurent des `Savestate` complets obtenus par le
rejeu exact d'une démonstration. La collecte enregistre l'indice du snapshot.
La récompense et la meilleure progression sont réinitialisées à cet état,
sans attribuer les checkpoints antérieurs. La proportion de tels resets
décroît ; toutes les évaluations commencent à zéro.

La récompense brute par action est :

```text
0,05 × nouveau progrès (plafonné à 30 m par action)
+ 10 × nouveaux checkpoints + 100 × arrivée − 20 × échec
− 0,01 × ticks − 0,000005 × min(distance_route, 30 m)² × ticks
```

PPO utilise cette récompense multipliée par 0,01, un acteur et un critique
tanh de largeur 64, gamma 0,999, lambda 0,97, quatre époques, des minibatches
de 256 et une collecte dans l'ordre temporel de 16 environnements.
Le SDK C++ vérifie les probabilités et valeurs du comportement avant update.
Les checkpoints conservent Adam et les RNG. Chaque mise à jour conserve le
modèle de comportement, les observations/actions et les états avant/après.

## Contrôles et mesures

Les cinq replays de contrôle retrouvent exactement les arrivées déclarées :
19 967, 20 158, 19 994, 11 212 et 8 008 ms. Le maximum d'écart avec les
positions visuelles quantifiées est inférieur à 0,9 mm avec la convention
post-step +10 ms explicitée par le rapport. Cette comparaison visuelle ne
constitue pas une preuve bit pour bit de tout l'état interne.

Les resets répétés, quatre clones concurrents, les commandes invalides, la
troncature partielle et le refus de continuer après fin passent. Les prévisions
ne modifient pas la voiture réelle. L'optimisation de la copie du monde conserve
exactement actions, observations et mots physiques sur les essais comparés.
Elle réutilise une copie privée seulement lorsque tous les modèles disponibles
ont une échelle de collision unitaire ; les autres cas gardent les clones
indépendants. Les 121 sources physiques amont restent inchangées.

L'audit rejoue chaque transition avec des commandes physiques de 10 ms et
recalcule indépendamment quantification, récompense, durée et bootstrap.
4 096 transitions du curriculum et 1 024 transitions avec anticipation passent,
sans différence de mots physiques, d'observations, de probabilités ou de valeurs.
Les 30 CTests portables du SDK passent également.

Les mesures sur ce Ryzen 9 8940HX atteignent environ **142 450 ticks physiques/s**
pour 16 mondes sans anticipation, et 40 572 ticks/s sur un cœur pour le moteur
seul. Le premier PPO de course a collecté 1 638 400 transitions en 423 s,
écritures de preuve, optimisation et évaluations incluses. Un autre essai a
collecté 2 457 600 transitions en 574 s. Ces résultats n'établissent pas à eux
seuls la qualité d'une politique. La recherche avec anticipation avance plus
de 1 000 ticks prévisionnels par décision : son essai optimisé de huit updates,
8 192 transitions, a pris 140 s sous charge concurrente.

## Résultats de conduite et périmètre

Autumn 2026-01 sert de carte de développement. La démonstration de référence
fait 19,967 s. Le PPO simple et plusieurs initialisations par imitation ont
échoué ou régressé ; leurs fichiers sont conservés. Le curriculum seul n'a
pas résolu ces défauts. La collecte DAgger corrige la distribution des états
de l'imitation et améliore le réseau, mais sa robustesse reste inférieure au
contrôleur avec anticipation.

Le candidat avec anticipation et PPO réussit les dix premiers essais
perturbés, moyenne **22,185 s**, contre **22,608 s** pour le même planificateur
sans correcteur appris. Ces dix essais utilisent la même intensité de
perturbation physique pour les deux méthodes, indépendamment de l'amplitude
de résidu PPO. Le réseau seul issu d'une autre branche réussit 26/30 courses,
moyenne des arrivées 24,411 s. Les DNF sont comptés séparément.

Le lot final, avec une nouvelle graine de génération des perturbations
(`--seed 99926`), donne **30 arrivées sur 30**, moyenne **21,954 s**, contre
**22,132 s** pour le même planificateur sans réseau. Le modèle a été figé avant
ce lot ; aucune sélection de poids ne s'appuie sur ses résultats.
Rapport : `candidate-planner-update0/final-unseen-30/report.json`.

Le candidat PPO est rejoué dans le serveur officiel depuis la frontière zéro,
avec la graine de validation du ghost. Résultat calculé : **22,273 s et quatre
checkpoints**. Quaternion, position et vitesse linéaire sont identiques bit
pour bit sur **2 228 frontières successives**, sans décalage ajusté. Les
commandes sont d'abord écrites dans un nouveau ghost puis relues par le codec.
Le helper `patch-active` prolonge explicitement le mode véhicule dans la queue
inactive existante du ghost ; le helper normal refuse de prétendre avoir
écrit des commandes dans des paquets qui ne portent pas ces champs.

`IsValid` reste faux : le ghost conserve le temps déclaré 19,967 s et le
validateur rapporte aussi `unexcepted walltime (5s)`. Le temps **calculé**,
les checkpoints et les états comparés sont les éléments validés ici. Ce n'est
pas une homologation du ghost comme record accepté.

Reproduire cette comparaison du candidat conservé :

```sh
python3 scripts/validate_fast_policy.py \
  --run local/recon/fast-0.37/release-candidate \
  --model local/recon/fast-0.37/release-candidate/policy.tmppo \
  --seed 29120025 --output local/mon-controle-original
```

Changer la graine sans modifier celle du ghost peut produire des trajectoires
différentes : le moteur applique des ajustements déterministes liés aux entrées
et à cette graine. Le script refuse toute divergence plutôt que de tolérer un
écart de trajectoire. L'horizon doit tenir dans la capacité du ghost source.

Le simulateur lit effectivement les assets installés et permet d'entraîner
PPO rapidement en headless. La qualification de conduite porte sur cette
route, cette carte et les perturbations mesurées. Elle ne démontre ni un bot
fort sur toutes les cartes, ni le reverse complet de toutes les branches,
surfaces, voitures et effets du jeu.

Les résultats détaillés sont dans `local/recon/fast-0.37/`, notamment
`release-candidate`, `candidate-planner-update0`, `ppo-planner-v4`,
`ppo-planner-optimized-v4`, `ppo-dagger-v2`, `replay-corpus-v1` et
`environment-checks-optimized-final`. Les cohortes `frozen-v1` à `frozen-v4`
conservent les anciennes bibliothèques nécessaires à leurs anciens schémas.

Le paquet figé est dans `dist/fast-training-linux-0.37.1/` ; son fichier
`LANCER.md` donne les commandes et `manifest.json` retient les SHA-256 de
chaque fichier. Le correctif final rejette les snapshots situés au-delà de
l'horizon d'épisode avant toute mutation. Le candidat et la physique de course
sont inchangés et le contrôle officiel est répété avec la bibliothèque finale.
La sauvegarde `backups/trackmania2020-re-source-0.37-final.zip` contient les sources
du projet ; `backups/gearbox-fast-training-corresponding-sources-0.37.zip`
contient aussi les sources amont et préparées. Aucun Pack du jeu n'y est inclus.
