# PPO CUDA sur Fall 2026-01 — 0.40

Le PPO dispose maintenant d'un optimiseur CUDA, utilisé sur la RTX 5060 Laptop
8 Go du PC. Les mondes physiques et la collecte native restent sur CPU. Le
réseau d'entraînement est mis à jour sur GPU puis rechargé dans le collecteur.
Les policies `.tmppo` restent compatibles avec le SDK injecté existant.

## Entraînement en cours et reprise

Le cycle mono-map lancé sur CPU avait effectué **492 mises à jour**, soit
**2 015 232 transitions**, lors du transfert. Il a été arrêté entre deux mises
à jour complètes. Les **508 mises à jour restantes** ont été lancées sur CUDA
pour conserver l'objectif initial de 1 000 mises à jour / 4 096 000 transitions.

- CPU initial : `local/training/fall01-ppo-20261030-01`.
- Suite CUDA : `local/training/fall01-ppo-gpu-20261030-01`.
- Progression : `training.log` et `run/updates.csv` dans le dossier du job.
- Modèle et état d'entraînement retenus : `run/best.tmppo` et
  `run/best.checkpoint`. Le meilleur modèle CPU reste conservé dans son job.
- Arrêt propre : créer `run/STOP` dans le dossier du job CUDA. Le superviseur
  arrête ensuite le service GPU.

Le fichier `migration-verified.json` prouve que le checkpoint initial CUDA est
identique octet par octet au dernier checkpoint CPU transféré. Les poids, les
moments et le compteur Adam, ainsi que les deux générateurs aléatoires natifs,
sont conservés. Les courses physiques repartent du départ, comme lors des autres
reprises du trainer : il ne s'agit pas d'une continuation exacte des positions
des voitures.

Pour reprendre ultérieurement un checkpoint complet :

```sh
python3 scripts/run_gpu_training.py \
  --resume local/training/fall01-ppo-gpu-20261030-01/run/best.checkpoint \
  --directory local/training/fall01-ppo-gpu-suite \
  --updates 500
```

Le dossier doit être nouveau. La map par défaut est Fall 2026-01. Les options
`--map`, `--environments`, `--threads`, `--rollout`, `--horizon` et `--seed`
permettent de choisir les conditions de cette reprise. Le service exige CUDA :
il ne revient pas silencieusement au CPU.

## Gain mesuré

Sur un rollout réel de 4 096 transitions, avec 64 minibatches et quatre epochs :

| Mesure | PPO natif CPU | PPO CUDA |
|---|---:|---:|
| Optimisation du rollout de référence | 1,266 s | 0,309 s après chauffe |
| Collecte et optimisation, moyennes du test complet | 1,733 s | 0,755 s |

Cela représente environ **×4,1 sur l'optimisation** et **×2,3 sur collecte +
optimisation** dans ces essais. Le deuxième chiffre compare des moyennes de
mises à jour de même taille à des moments d'apprentissage différents ; ce n'est
pas un benchmark de trajectoires identiques. Les temps du service GPU incluent
la lecture du rollout et les transferts nécessaires. La première mise à jour
CUDA comprend aussi une initialisation plus lente. L'écriture des traces et les
évaluations ajoutent du temps au cycle complet.

Rapports :

- `local/recon/gpu-0.40/reference-update-v2/report.json` ;
- `local/recon/gpu-0.40/live-pipeline-v2/speed-comparison.json` ;
- `local/recon/gpu-0.40/pipeline-physics-audit/report.json`.

## Vérifications de compatibilité

L'optimiseur travaille actuellement en **float64**. Sur le même rollout et le
même état initial que le PPO natif, les différences maximales mesurées sont :

- poids : `2,22e-16` ;
- premier moment Adam : `7,44e-17` ;
- second moment Adam : `3,52e-19`.

Le nombre de pas Adam et les états des générateurs aléatoires correspondent.
Le mélange des minibatches passe par le même `std::shuffle` / `mt19937_64` que
le SDK. Le service contrôle l'identité des probabilités et des valeurs avant
l'optimisation, puis le collecteur contrôle l'intégrité du checkpoint reçu.

Un test de cinq mises à jour CUDA a collecté et appris **20 480 transitions**.
L'audit indépendant a rejoué **768 transitions / 3 840 pas physiques**, avec
états, observations, commandes et récompenses identiques. Les 4 096 valeurs du
modèle de comportement du premier rollout ont également été contrôlées.
Cela vérifie le backend d'apprentissage, pas une arrivée de ce modèle dans le
client Trackmania.

Les deux premiers essais de service, conservés dans les traces, incluent un
échec de lancement dû au chemin résolu du Python du venv. Le lanceur utilise
maintenant le chemin du venv sans déréférencer son exécutable.

## Dépendances et architecture

L'installation est isolée dans `tools/venv-gpu`, avec PyTorch
`2.10.0+cu128` / CUDA 12.8. Elle ne remplace pas le Python système.

```sh
python3 -m venv --system-site-packages tools/venv-gpu
tools/venv-gpu/bin/python -m pip install \
  'torch==2.10.0+cu128' --index-url https://download.pytorch.org/whl/cu128
cmake --build native/build-linux \
  --target tm2020_generalist_train tm2020_gpu_helpers -j 8
```

PyTorch documente la prise en charge de Blackwell avec les builds CUDA 12.8 et
les plateformes de ses versions dans ses [notes de version 2.7](https://pytorch.org/blog/pytorch-2-7/)
et sa [matrice de versions](https://github.com/pytorch/pytorch/blob/main/RELEASE.md).
Ici, la disponibilité de CUDA et une multiplication de matrices ont aussi été
vérifiées sur le GPU réel.

Le collecteur transmet un checkpoint natif et un rollout au service local
`scripts/gpu_ppo_service.py`. `scripts/gpu_ppo.py` applique les mêmes équations
GAE, PPO et Adam que le SDK. `gpu_helpers.cpp` conserve le format de checksum et
le mélange natif. Chaque réponse produit un nouveau checkpoint complet ; les
échecs interrompent la collecte et conservent les checkpoints précédents.

Aucun contrôleur de trajectoire HC ou MPC n'a été ajouté à cet entraînement.
La policy issue des entraînements précédents est spécialisée sur cette seule
map. L'accélération matérielle n'est pas une preuve supplémentaire de qualité
de conduite : les arrivées en simulation et les essais dans le jeu restent des
mesures séparées.
