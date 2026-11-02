# Entraînement continu de Fall 2026-01

> La session active utilise désormais le reward chrono 0.42 et le dossier
> `fall01-ppo-speed-continuous`. Voir [la configuration actuelle](MINIMUM_TIME_PPO_0_42.md).
> Les paramètres et résultats ci-dessous décrivent la session historique 0.41.


L'entraînement est géré par le service utilisateur
`tm2020-fall01-ppo.service`. Il utilise CUDA pour PPO et garde les simulations
sur CPU. Le service est activé au démarrage du gestionnaire utilisateur ; il
continue après fermeture du terminal et redémarre automatiquement en cas
d'échec du superviseur.

Il n'y a aucune limite au nombre de cycles. Chaque cycle réalise 500 mises à
jour, puis reprend le checkpoint final du cycle précédent avec poids, Adam et
générateurs aléatoires. Les voitures simulées repartent du départ à chaque
changement de cycle. La reprise commence après les 1 000 mises à jour du cycle
CPU/CUDA précédent, sans modifier ces anciens résultats.

## Voir et arrêter

```sh
systemctl --user status tm2020-fall01-ppo.service
cat local/training/fall01-ppo-continuous/state.json
tail -f local/training/fall01-ppo-continuous/training.log
```

Le meilleur modèle est toujours accessible à :

```
local/training/fall01-ppo-continuous/best.tmppo
```

`best.checkpoint` contient son état d'optimisation et `latest.checkpoint` pointe
vers le dernier état complet de l'apprentissage. `best.json` indique les
résultats de validation du meilleur modèle ; `state.json` donne la progression
cumulée et le cycle actif. Ces modèles utilisent toujours la même interface
que le SDK de conduite. Une arrivée en simulation ne valide pas une arrivée
dans le client.

Pour arrêter proprement et empêcher la reprise tant que le marqueur existe :

```sh
touch local/training/fall01-ppo-continuous/STOP
```

Pour une interruption via systemd :

```sh
systemctl --user stop tm2020-fall01-ppo.service
```

Le service est activé au démarrage. Pour le désactiver également :

```sh
systemctl --user disable --now tm2020-fall01-ppo.service
```

Pour reprendre après un arrêt par marqueur, supprimer le marqueur puis démarrer
le service. Le superviseur reprend son dernier checkpoint enregistré.

## Espace disque et vérifications

Le superviseur n'efface aucun des anciens jobs CPU/GPU. Dans **sa propre session**,
il conserve le premier rollout et les cinq mises à jour complètes les plus
récentes de chaque cycle, les trois derniers cycles, deux snapshots récents et
le meilleur modèle global. Les traces de travail plus anciennes de cette
session sont supprimées automatiquement. Les compteurs et résultats restent
dans les fichiers de progression. Cette rétention évite l'accumulation de
plusieurs gigaoctets de traces par cycle.

Les checkpoints sont copiés puis publiés par remplacement atomique. Le service
reprend après un échec depuis le dernier checkpoint enregistré et attend entre
les tentatives répétées. Un verrou empêche deux superviseurs de gérer la même
session.

La validation périodique réalise cinq essais : un départ nominal et quatre
essais avec de petites perturbations physiques de direction. Les contrôles
restent ceux de la policy pendant la préparation des perturbations. Le
meilleur modèle est choisi d'abord par le nombre d'arrivées, puis par le temps
moyen. Le modèle de départ conservé termine les cinq essais de cette validation
en **28,982 s de moyenne**, avec un meilleur essai de **28,218 s**. Le temps
nominal annoncé précédemment était **28,588 s**, selon l'ancien essai unique.

Ces nouvelles évaluations utilisent le protocole
`policy_relative_physical_i8_steering_v2` ; les anciens rapports n'ont pas été
réécrits. Le reward physique est inchangé. Les métadonnées des nouveaux jobs
indiquent correctement sa pénalité de `0.002` par pas de 10 ms et l'absence de
pénalité explicite de distance latérale.

Vérifications effectuées :

- quatre tests de rétention, conservation des modèles et refus des liens
  symboliques susceptibles de viser un dossier extérieur ;
- deux cycles CUDA complets de test, avec checkpoint identique octet par octet
  entre la fin du premier et le début du second ;
- demande d'arrêt pendant un entraînement de test, avec checkpoint conservé ;
- démarrage du vrai service et contrôle de l'activité CUDA et des mises à jour.

Les résultats de test sont conservés dans
`local/recon/gpu-0.40/continuous-two-cycles-test/`. Les sources du superviseur sont
`scripts/train_continuous.py`. Une copie de la configuration systemd de ce PC
se trouve dans `config/systemd/`.
