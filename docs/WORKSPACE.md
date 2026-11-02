# Carte du projet — 2 novembre 2026

Ce guide décrit les chemins conservés. Pour les processus effectivement actifs,
utiliser `python3 scripts/project_status.py` ; un ancien JSON `running: true`
ne prouve pas qu’un processus existe encore. La consigne actuelle est la pause.

## Pipeline actuel

```text
Packs installés + map GBX
    -> Gearbox / bibliothèque native Rust, physique CPU à 100 Hz
    -> vector_physics.cpp / vector_physics.py
    -> contrôleur trajectory_hybrid + gouverneur d’actions humaines
    -> optimisation des trajectoires, gains et rythmes gaz/frein
    -> audit 64 seeds normales + 64 perturbées
    -> candidat figé, essai client local séparé, replay original décodé
```

L’optimisation actuelle porte sur le hardcode ; les branches PPO/BC sont de la
recherche conservée et ne remplacent pas les champions. Le profil d’une map
utilise son propre corpus Top 100. Les inputs humains sont des références et
des données d’initialisation, pas une séquence obligatoire copiée tick par tick.

## Sources à lire

| Fonction | Fichier |
|---|---|
| Optimisation hardcodée | [train_hardcode_recorded_inputs.py](../scripts/train_hardcode_recorded_inputs.py) |
| Ordonnancement et qualification de campagne | [run_hardcode_human_campaign.py](../scripts/run_hardcode_human_campaign.py) |
| Initialisation dans la physique normale | [bootstrap_normal_hardcode.py](../scripts/bootstrap_normal_hardcode.py) |
| Profils de rythme par map | [build_human_rhythm_profiles.py](../scripts/build_human_rhythm_profiles.py) |
| Contrôleur partagé sim/client | [trajectory_hybrid.cpp](../native/src/trajectory_hybrid.cpp) |
| Physique parallèle | [vector_physics.cpp](../integrations/generalist-training/vector_physics.cpp), [vector_physics.py](../scripts/vector_physics.py) |
| Runtime interne et protections | [runtime.cpp](../integrations/generalist-training/runtime.cpp) |
| Chargeur et staging immuable | [local_dll_loader.cpp](../native/src/local_dll_loader.cpp), [proton_sdk.py](../scripts/proton_sdk.py) |
| Essai client borné | [run_internal_trial.py](../scripts/run_internal_trial.py) |
| Décodage et comparaison des inputs | [analyze_human_replays.py](../scripts/analyze_human_replays.py), [compare_human_sim_inputs.py](../scripts/compare_human_sim_inputs.py) |

Les versions gelées de compilation et de physique sont référencées dans
[config/project.json](../config/project.json). Ce fichier est un index de travail,
pas une autorisation de déploiement automatique.

## Données conservées

- `local/training/hardcode-human-0.75/` : recherche humaine principale, pause.
- `local/training/hardcode-human-0.76-prep/` : préparation des autres maps, pause.
- `local/training/hardcode-human-0.74/sim-candidates/01/human-top10.tmhyb` : modèle 01 conservé.
- `local/recon/human02-20261101/candidate.tmhyb` : candidat 02 figé pour l’essai client.
- `local/training/human-rework-0.70/top100-cohort/` : ghosts originaux, décodages et métriques.
- `local/recon/offline-human01-20261101/` et `local/recon/human02-20261101/` : preuves clients.
- `local/cleanup/project-*/` : inventaire et empreintes du nettoyage.

La 02 était expérimentale avant l’essai : 88/128 runs réunissant le seuil Top 100
et les critères humains sur son lot de sélection. Son arrivée client ne remplace
pas une qualification complète 64 + 64. Ne pas confondre seuil de classement
sauvegardé et rang en ligne actuel.

## Nettoyage et dépendances

`cache/` contient aussi des **sources nécessaires**, notamment
`gearbox-linux-0.37/` et `rust-cross-0.46/`. `tools/` contient l’environnement
Python et les compilateurs. Les bibliothèques sous `native/build-*` peuvent être
référencées par des expériences figées. Ces répertoires ne sont pas purgés en bloc.

`scripts/clean_workspace.py` propose uniquement les caches Python des sources et
les préfixes `local/recon/*/owned-wine-prefix` recréables d’essais terminés. Il
refuse les préfixes actifs ou contenant des modèles/replays et garde les rapports
voisins. Le jeu réel et son préfixe sont hors de cette sélection.

Les sources restent à leur emplacement pour conserver imports, builds et chemins
des checkpoints. Les sorties CMake versionnées par date sont exclues de Git.
L’historique est accessible depuis [l’index documentaire](README.md).
