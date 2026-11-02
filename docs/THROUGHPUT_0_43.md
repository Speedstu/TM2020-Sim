# Débit PPO — optimisations 0.43

La session continue `fall01-ppo-speed-continuous` reprend ses checkpoints
existants avec un pipeline accéléré. Le service conserve son nom
`tm2020-fall01-ppo.service`. Le reward, la physique, les 48 observations,
les 16 environnements et les hyperparamètres PPO restent ceux de la session
0.42. Chaque décision avance toujours de cinq ticks de 10 ms.

## Débits mesurés

Un SPS désigne ici **une transition de décision**, pas un tick physique.
Les essais portent sur Fall 2026-01 et le réseau 48 → 128 → 1.

| Mesure | Décisions/s |
| --- | ---: |
| Avant : collecte + optimisation, 20 updates récents | 6 082 |
| Avant : collecte seule | 9 171 |
| Pipeline accéléré, 16 environnements / 16 workers | 14 491 |
| Essai à 32 environnements / 32 workers | 17 290 |
| Essai à 64 environnements / 32 workers | 19 679 |
| Service relancé, 30 updates incluant les validations périodiques | 13 896 |

Les trois premiers essais accélérés excluent la première mise à jour de
chauffe et incluent les autres coûts par update : collecte, écriture,
optimisation, checkpoints et validation quand elle a lieu. Ils utilisent un
seul essai de validation pour comparer les débits ; **le service conserve
ses 20 essais de validation**. L'ouverture des Packs, le démarrage de Torch
et les redémarrages entre cycles ne sont pas inclus dans ces débits par
update. Les timings complets de chaque job restent dans `job.json`.

La configuration active garde 16 environnements pour conserver la taille
des lots et le nombre de mises à jour Adam. Les essais à 32/64 environnements
servent à mesurer la montée en charge ; ils n'ont pas démontré une meilleure
policy.

100 000 décisions/s nécessiteraient au moins **500 000 ticks physiques/s**,
auxquels s'ajoutent les perceptions et PPO. Les benchmarks de physique à
accélérateur constant mesurent environ 150 000–190 000 ticks/s selon le
nombre de mondes/workers ; ce n'est pas le débit d'un entraînement complet.
Les résultats actuels ne valident donc pas 100 000 décisions/s. Il faudrait
des gains supplémentaires importants sur le moteur/perception et leur
vectorisation, éventuellement un backend GPU. Une hausse du débit ne
constitue pas une preuve d'amélioration du pilote.

## Changements

- Le PC était sur le profil `power-saver`, CPU plafonné à 2,4 GHz. Sur secteur,
  passage au profil `performance`, limite annoncée à 5,386 GHz et préférence
  énergétique `performance`. La fréquence réellement soutenue dépend de la
  charge ; aucun gain isolé n'est attribué à ce changement.
- Le sampler ne recalcule plus une seconde fois la moyenne de l'acteur pour
  sa log-probabilité. Le calcul d'une valeur scalaire évite une allocation.
- Quatre neurones sont calculés en parallèle dans la première couche CPU,
  en conservant pour chaque neurone l'ordre des additions.
- Les workers calculent maintenant acteur, critique, physique et valeur
  suivante en parallèle. Les normales sont tirées sur le thread principal
  dans l'ordre d'origine : le parallélisme ne change pas le RNG du sampler.
- 16 workers remplacent les 12 précédents, ce qui évite une répartition
  inégale des 16 mondes.
- Les rollouts utilisent un tableau binaire float64 au lieu d'un CSV.
  L'écriture mesurée passe d'environ 0,305 s à 0,002 s pour 16 384 transitions.
  Les traces physiques complètes restent enregistrées et la rétention du
  superviseur reste active.
- Les minibatches PPO sont capturés avec
  [les CUDA Graphs de PyTorch](https://docs.pytorch.org/docs/stable/notes/cuda).
  Les données, poids et états Adam sont mis à jour dans des buffers stables.
  Le shuffle natif, la GAE, le clipping, les corrections Adam et le contrôle
  du KL restent ceux de l'optimiseur précédent. Les corrections Adam sont
  précalculées avec les mêmes opérations CPU que précédemment.
- L'optimisation seule passe d'environ 0,9 s à 0,16 s par update de la session
  active, après capture. Les temps varient avec la charge et la chauffe.
- `profile.jsonl` détaille les coûts réels par update, y compris la
  sérialisation et les validations, qui étaient exclus de l'ancien ratio
  `collect_seconds + train_seconds`.

## Vérifications

Les preuves se trouvent dans `local/recon/throughput-0.43/`.

- Référence native conservée avant modification : exécutable, scripts,
  checkpoint et rollout de 16 384 transitions.
- Après parallélisation et calcul des quatre neurones : traces physiques,
  poids, Adam et RNG **identiques octet par octet** à la référence sur une
  mise à jour native complète. Comparaisons dans `native-parallel/` et
  `native-simd/` face à `native-reference/`.
- Les tableaux binaires et CSV sont exactement égaux. Deux tests vérifient
  aussi la GAE pour les deux schémas d'actions et le rejet des fichiers
  tronqués ou de dimensions incorrectes.
- CUDA Graphs contre PPO C++ : erreur maximale des paramètres de
  `2,22e-16` sur le cas à une action et `4,44e-16` sur celui à trois actions.
  Moments Adam, nombre de pas et états RNG vérifiés. Le graphe est rejoué
  plusieurs fois depuis le même checkpoint pour vérifier sa réutilisation.
- Les 30 tests C++ passent après reconstruction des tests concernés par RL.
  Les sept tests Python de transport, conversion et rétention passent.
- La session réelle a repris son checkpoint et a achevé un cycle avec CUDA
  Graphs, puis démarré le suivant. Le meilleur modèle demeure protégé.

## Contrôler ou comparer

```sh
systemctl --user status tm2020-fall01-ppo.service
tail -f local/training/fall01-ppo-speed-continuous/training.log
cat local/training/fall01-ppo-speed-continuous/current/cuda-service/device.json
tail local/training/fall01-ppo-speed-continuous/current/run/profile.jsonl
```

Pour un essai séparé dans un dossier nouveau :

```sh
python3 scripts/run_gpu_training.py \
  --directory local/mon-benchmark \
  --resume local/training/fall01-ppo-speed-continuous/best.checkpoint \
  --library cache/reward-study-target/release/libtm2020_speed.so \
  --updates 10 --environments 16 --threads 16 --rollout 1024 \
  --eval-every 5 --eval-trials 20 --disturbance-probability 0.5
```

`--gpu-optimizer eager` conserve le chemin PyTorch précédent pour comparaison.
`--rollout-format csv` conserve le transport texte. Les rollouts binaires
dont la taille n'est pas un multiple du minibatch utilisent automatiquement
l'optimiseur eager pour conserver le traitement exact du dernier minibatch.
Les anciens rollouts CSV restent lisibles par le worker.

Le profil énergétique original est enregistré dans `power-profile.json`.
Pour revenir à ce profil sur ce PC :

```sh
busctl --system set-property org.freedesktop.UPower.PowerProfiles \
  /org/freedesktop/UPower/PowerProfiles \
  org.freedesktop.UPower.PowerProfiles ActiveProfile s power-saver
```

Le modèle et son format SDK restent compatibles. Ces optimisations de débit
ne valident ni un nouveau record dans le jeu, ni une policy généraliste.
