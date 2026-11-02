# Entraîner une policy et la charger dans Trackmania — 0.39.1

La chaîne fonctionne sur ce PC Linux avec Steam Flatpak / Proton : simulation
sans fenêtre, PPO C++ vectorisé, checkpoint `.tmppo`, puis inférence de ce même
format de policy dans une DLL chargée explicitement dans Trackmania.

**Le modèle généraliste reste faible.** Pouvoir lire une nouvelle map ne signifie
pas savoir la terminer. Cette version livre les outils d'entraînement et de
conduite, pas une maîtrise de toutes les maps ou de toutes les mécaniques.
La révision 0.39.1 détecte automatiquement la largeur du réseau lors de la
reprise d’un checkpoint et indique la largeur réelle dans la configuration.
Les résultats 30/30 de la version 0.37 utilisent une route connue et un contrôleur
physique ; ils ne décrivent pas cette nouvelle policy.

## Commandes

Depuis la racine du projet, les Packs installés par Steam sont détectés seuls.
Aucun Torch, Gym ou service payant n'est nécessaire.

```sh
# Reconstruire le simulateur, le PPO et le SDK Windows avec Zig.
python3 scripts/run_generalist_ppo.py build --windows

# Contrôles de l'environnement ; le fichier de sortie doit être nouveau.
python3 scripts/run_generalist_ppo.py checks --output local/mes-controles.json

# Entraîner une seule policy sur plusieurs maps, depuis le checkpoint livré.
python3 scripts/run_generalist_ppo.py train \
  --model dist/generalist-linux-proton-0.39.1/policy.tmppo \
  --map-list dist/generalist-linux-proton-0.39.1/training-maps.txt \
  --updates 1000 --environments 28 --threads 12 \
  --output local/mon-bot

# Reprendre poids, Adam et générateurs aléatoires. Les courses sont réinitialisées.
python3 scripts/run_generalist_ppo.py train \
  --map-list dist/generalist-linux-proton-0.39.1/training-maps.txt \
  --resume local/mon-bot/best.checkpoint \
  --updates 1000 --environments 28 --output local/mon-bot-suite

# Dans Trackmania : ouvrir Fall 2026 - 01, choisir Drive alone, rester au départ.
# La fenêtre du jeu doit être active pendant toute la conduite.
python3 scripts/run_generalist_ppo.py live \
  --model local/mon-bot/best.tmppo \
  --seconds 20 --output local/essai-dans-le-jeu
```

Pour une autre map, fournir son fichier GBX à `--map /chemin/Piste.Map.Gbx` pour
l'entraînement, l'évaluation et la conduite. Le chemin de la map courante n'est
pas détecté automatiquement dans la mémoire du client. Aucun replay n'est
nécessaire à l'inférence. Le nombre d'environnements doit couvrir les maps de la
liste. Une liste contient un chemin de map par ligne ; le dossier de sortie est
toujours nouveau. Sans liste, seule la map passée à `--map` est entraînée.

Le binaire livré a mesuré environ **97 874 pas physiques/s** avec 16 mondes et
12 threads, resets compris. Le débit de PPO inclut aussi l’optimisation.

L'ouverture initiale des Packs et des mondes peut prendre quelques minutes pour
quinze maps. Ensuite les mondes persistent et les resets restaurent un état
complet. `updates.csv` mesure séparément collecte et optimisation.

Pour arrêter l'entraînement proprement, créer `local/mon-bot/STOP` : le processus
termine la mise à jour courante et conserve les checkpoints. En jeu, Échap, la
perte du focus, une rupture de télémétrie ou du compagnon de perception relâchent
les touches. Le rapport indique aussi le chemin exact d'un fichier `.STOP` de
la session injectée, utilisable depuis un terminal ou un autre programme.

## Ce qui a été vérifié

- Chargement ordinaire par `LoadLibraryW` et appel du SDK dans le vrai processus
  Trackmania, PID Windows 2320 / PID Linux 123649 lors des essais.
- 75 inférences du checkpoint livré dans le jeu en quatre secondes et 103,800 m de déplacement.
  L'accélérateur mesuré a répondu aux commandes. Arrêt et retour normaux.
- Recalcul indépendant sous Linux des 75 décisions du même checkpoint : pédales
  identiques et direction quantifiée identique, à la représentation float près.
- Arrêt demandé pendant une conduite : le worker a détecté le fichier STOP ;
  accélérateur et frein ont ensuite été observés relâchés.
- Encodeur externe et encodeur d'entraînement exactement égaux pour les mêmes
  21 nombres d'entrée sur 100 transitions / 500 pas physiques. Absence de
  mutation physique par les requêtes de perception, clones isolés, reset exact,
  entrées invalides rejetées, horizon partiel de trois pas correctement compté.
- 30 tests C++ et 7 tests de séparation du corpus passent.

Le dernier entraînement complet réalise **716 800 transitions et 3 581 034 pas
physiques en 337,27 s**, après le chargement des mondes. Le checkpoint retenu
termine **1/15** courses dans l'évaluation de développement, en 7,966 s sur la
piste qu'il termine. Sur les trois maps entières réservées, il termine **0/9**
essais, avec trois essais par map. Les trois maps ont été chargées et exécutées
sans route de replay ; ce résultat ne valide pas la force sur l'inconnu.

Les rapports chiffrés de l'entraînement et de l'évaluation finale sont copiés
avec le checkpoint dans `dist/generalist-linux-proton-0.39.1/evidence/`.

## Architecture et contrat

`integrations/generalist-training/environment.rs` utilise la même physique
Gearbox préparée en 0.37, sans modifier ses fichiers de moteur. Les bibliothèques
et les résultats figés 0.37 restent séparés. La carte fournit les collisions
statiques et les volumes de checkpoints. La policy reçoit 48 nombres : vitesse
et verticale dans le repère de la voiture, prochain objectif géométrique,
commandes précédentes, rapport de boîte, contact global, turbo et 33 rayons.
Elle ne reçoit ni UID, ni nom, ni numéro de map, ni trajectoire experte, ni
horloge de replay. Elle commande accélérateur, frein et direction.

Les objectifs utilisent l'ordre des checkpoints et une approximation par
intersection d'un segment avec leurs boîtes. Ce suivi n'est pas une lecture
autoritaire des checkpoints du client. Le planificateur de trajectoire globale,
les routes qui se superposent, les détours, les sauts et les maps multilaps ne
sont pas tous résolus. Les maps multilaps sont refusées explicitement.

Le compagnon Linux utilise le code de perception d'entraînement pour les rayons
de la map chargée. Une connexion locale avec jeton aléatoire et numéros de
séquence échange la télémétrie et les 48 observations. **L'inférence de la policy
est exécutée dans la DLL du jeu**, pas dans Python. Ce compagnon ne modifie pas
la pose du simulateur et n'avance aucun de ses pas physiques.

Le SDK lit des copies réfléchies de l'état visuel du client : position, matrice,
vitesse, boîte, contact et turbo. Ces copies peuvent être interpolées ; elles
ne constituent pas une propriété physique vérifiée à 100 Hz. L'égalité de
l'encodeur pour les mêmes entrées n'est pas une preuve d'identité entre la
physique simulée et la télémétrie du client. La matrice est validée et le SDK
exige plusieurs copies cohérentes, un départ proche de celui du GBX, un compteur
qui avance et le SHA-256 exact de l'exécutable pris en charge. L'UID de la map
chargée dans le client n'est pas encore vérifié directement.

Sous Proton, les touches sont émises par scancodes. La direction analogique est
approchée par des impulsions de touches ; ce transport n'est pas identique aux
commandes analogiques du simulateur. L'essai court démontre la conduite et
l'inférence, pas une arrivée complète ni une équivalence des trajectoires.
Le compte observé était Starter et le menu refusait les pistes personnalisées ;
les essais ont utilisé la première piste gratuite de la campagne en Drive alone.
Aucun achat n'a été effectué.

Les corps retirés par le moteur produisent une vraie fin absorbante sans
arrivée si aucun temps d'arrivée n'existe. `reserved=1` indique l'absence de
corps : les mots de rigidité et l'observation terminale sont nuls et ne sont
pas présentés comme un état physique courant. PPO annule le bootstrap sur cette
fin. Les autres erreurs/panics interrompent la collecte ; aucun état inventé
n'est accepté. Les traces des essais interrompus sont conservées.

## Refaire les évaluations

```sh
# Contrôle indépendant d'un rollout sur trois mondes distincts.
python3 scripts/audit_generalist_rollout.py \
  --run local/recon/generalist-0.39/multimap-ppo-v3 \
  --environments 0,12,14 --output local/mon-audit

# Évaluation sur les maps entières réservées, sans réentraîner sur leurs résultats.
python3 scripts/evaluate_generalist_corpus.py \
  --corpus local/recon/generalist-0.39/corpus-split-v2.json \
  --split test --model dist/generalist-linux-proton-0.39.1/policy.tmppo \
  --output local/mon-test-inconnu
```

Les démonstrations peuvent initialiser l'acteur, puis PPO optimise les courses
avec la vraie physique du backend. Les 15 maps d'entraînement disposant d'une
démonstration valide restent séparées de la validation et des trois maps de
test. Des exemples dont l'arrivée n'a pas été reproduite sont conservés en
échec et exclus du CSV d'apprentissage. Les fichiers du corpus sont contrôlés
par empreinte lors des nouvelles préparations. Le corpus actuel contient
beaucoup de pistes TAS atypiques et ne couvre pas correctement toutes les
mécaniques recensées en 0.38.

Les sources GPL correspondantes et leurs notices sont conservées avec la
livraison. Les assets du jeu restent dans l'installation personnelle.
