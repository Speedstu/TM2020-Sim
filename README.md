# Trackmania2020-RE

Simulateur Trackmania sans rendu, SDK natif C++20/Rust, contrôleur hardcodé avec
retour physique et outils d’optimisation et d’analyse des inputs.

**La physique du simulateur vient de [Gearbox](https://github.com/Mergemat/gearbox)**,
par Bagautdin Omarov et ses contributeurs, révision
`e0583ee55168e950a65a645778e591bd26b6a0f2`. Ce projet ajoute le port Linux,
l’environnement vectorisé, le SDK, les contrôleurs, la recherche et les audits.
Il ne revendique pas une rétro-ingénierie complète et indépendante du jeu.

## Contenu

| Dossier | Rôle |
|---|---|
| `third_party/gearbox/` | Sources GPL du moteur et du chargeur d’assets, port Linux figé |
| `integrations/fast-training/` | Simulateur headless et première collecte PPO native |
| `integrations/generalist-training/` | Adaptateur physique, états, vectorisation et runtime client |
| `integrations/speed-training/` | Bibliothèque physique utilisée pour les expériences de vitesse |
| `native/include/`, `native/src/`, `native/tests/` | SDK C++, contrôleur, interfaces et tests |
| `sdk/`, `rust/`, `src/` | Interfaces supplémentaires, binding Rust et outils GBX |
| `scripts/` | Training, recherche hardcodée, décodage et audits |
| `docs/` | Architecture, méthodes et notes historiques |
| `config/` | Configurations d’expériences et exemples de services |

Ce dépôt est un **instantané des sources**. Il ne contient pas les Packs ou
exécutables propriétaires du jeu, maps, replays personnels, champions,
checkpoints, compilateurs ou environnements Python installés. Les sources
Gearbox nécessaires au simulateur principal sont incluses avec leur licence.

## Compiler sur Linux x86-64

Prérequis : Python 3.10+, CMake 3.21+, compilateur C++20, Rust/Cargo 1.98+,
et `liblzo2.so.2`. Les premières compilations Cargo téléchargent les dépendances
des lockfiles. Aucun compte, jeu ouvert ou entraînement n’est nécessaire pour
compiler et exécuter les tests autonomes.

```sh
# Exemple Debian/Ubuntu : outils système
sudo apt install build-essential cmake pkg-config liblzo2-dev

# Compiler SDK, physique, contrôleur et outils de décodage, puis tests autonomes
python3 scripts/build_source_checkout.py --jobs 4
```

La commande produit les bibliothèques sous `build/` et `cache/`, sans modifier
une installation Trackmania. Ajouter `--offline` si les dépendances Cargo sont
déjà téléchargées, ou `--native-only` pour compiler uniquement la partie C++.

## Faire tourner la physique

Fournir ses propres fichiers Trackmania : une map et le dossier `Packs`
contenant notamment `Stadium.pak`. Exemple de test de chargement et de pas physiques :

```sh
cache/source-fast-target/release/tm2020-fast-probe \
  /chemin/vers/map.Map.Gbx /chemin/vers/Trackmania/Packs
```

Le probe accélère tout droit pour mesurer le moteur ; ce n’est pas une run du
contrôleur entraîné. Le moteur avance à 100 Hz ; les arrivées et checkpoints
proviennent des événements simulés. La physique est exécutée sur CPU. Les
anciennes branches PPO peuvent employer CUDA pour l’optimisation du réseau.

## Contrôleur et entraînement humain

La branche la plus récente conserve le hardcode comme moteur principal. Elle
optimise trajectoire de référence, gains de correction et rythmes gaz/frein.
Les ghosts servent de données d’initialisation et de comparaison. Les commandes
sont soumises à un gouverneur avant leur application physique, avec pédales
binaires et direction quantifiée à 100 Hz.

Sources principales :

- [Contrôleur partagé](native/src/trajectory_hybrid.cpp)
- [Recherche hardcodée](scripts/train_hardcode_recorded_inputs.py)
- [Ordonnancement de campagne](scripts/run_hardcode_human_campaign.py)
- [Audit des départs normaux et perturbés](scripts/audit_hardcode_execution.py)
- [Méthode et limites](docs/HUMAN_HARDCODE_0_75.md)

Les expériences historiques de campagne attendent des données locales sous
`local/` : elles ne peuvent pas reprendre un champion à partir de ce seul dépôt.
Le script de build reconstruit les bibliothèques ; il ne reconstruit pas les
checkpoints ni le corpus de ghosts. Aucun training ne démarre automatiquement.
Les fichiers systemd sont des exemples historiques, pas des services à activer
en bloc.

## Validation et limites

Des essais locaux du projet ont produit 19,995 s sur Fall 2026-01 et 21,328 s sur
Fall 2026-02, avec inputs clients décodés à 100 Hz et temps reproduits dans le
simulateur. Ces artefacts locaux ne sont pas inclus dans ce dépôt. Ces résultats
ne prouvent ni une équivalence physique universelle, ni une IA forte sur les maps
inconnues, ni la qualification humaine/Top 10 des 25 maps.

Le runtime client et son chargeur sont des outils de recherche pour essais
locaux/hors ligne. Un défaut connu de détachement après l’arrivée impose encore
un redémarrage du client avant une nouvelle injection. La compilation et les
tests autonomes ne constituent pas une validation client.

Les notes de `docs/` sont datées. Leurs mentions de services actifs et chemins
de preuves décrivent le poste de recherche d’origine, pas l’état de ce clone.

## Licences et attribution

Distribution sous **GPL-3.0-or-later**, avec les attributions et licences tierces
conservées. Voir [LICENSE](LICENSE), [THIRD_PARTY.md](THIRD_PARTY.md) et
[l’attribution de l’adaptateur](integrations/fast-training/NOTICE.md).
Le code du décompresseur Rust vendored conserve sa licence MIT. Le code du jeu
et les assets propriétaires ne sont pas distribués.
