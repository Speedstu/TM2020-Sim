# PPO : objectif chrono et entraînement robuste — 0.42

> Le pipeline actif a été accéléré en 0.43, sans changer le reward ni les lots PPO.
> Voir [les débits et vérifications](THROUGHPUT_0_43.md).


La session active est `local/training/fall01-ppo-speed-continuous`, sur
**Fall 2026-01 uniquement**. Le service utilisateur conserve son nom :
`tm2020-fall01-ppo.service`. CUDA réalise l'optimisation PPO ; la physique,
les observations et la collecte restent natives sur CPU. L'entraînement
continue sans limite de cycles et redémarre après une erreur du superviseur.

## Reward retenu

Le reward brut coûte **un point par seconde**, donne **+100 à l'arrivée** et
pénalise un échec de **−100 moins le temps restant jusqu'à l'horizon**.
L'horizon est de 40 secondes. Pour un épisode complet :

- arrivée : `100 − chrono_en_secondes` ;
- échec : `−140`, quel que soit le moment de l'échec.

Finir une seconde plus tôt rapporte exactement un point supplémentaire.
Échouer plus tôt ne permet pas d'éviter le coût du temps restant. Les vrais
checkpoints et l'arrivée sont ceux de la physique ; aucun bonus de vitesse,
de trajectoire ou de distance à un objectif n'est ajouté. L'optimiseur
multiplie ces rewards par `0.01` pour conserver une échelle numérique modérée.

`gamma=1` correspond à cet objectif épisodique fini ; `lambda=1` et des
rollouts de 1 024 décisions réduisent la dépendance au bootstrap du critique.
Le temps exact fractionnaire de l'arrivée sert au calcul. L'échec est une
terminaison absorbante, sans bootstrap vers un état inexistant.

Une variante avec shaping par potentiel a aussi été testée. Les différences
de potentiel s'annulent en fin d'épisode ; le principe vient de
[Ng, Harada et Russell, 1999](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf).
Cette variante n'a pas été retenue : elle n'a pas amélioré les essais mesurés.
La version active n'utilise aucun potentiel.

## Apprentissage et sélection

La policy reste un réseau 48 → 128 → 1. Elle choisit la direction ;
l'accélérateur reste à fond et le frein relâché sur cette spécialisation.
L'extraction de la tête de direction conserve exactement les prédictions
de la policy précédente. Cette simplification ne convient pas forcément
aux autres maps qui demandent des freinages.

PPO démarre avec un taux d'apprentissage `3e-5`, un clip `0.1`, un KL cible
`0.01` et un écart type latent de direction `0.03`. Le critique conserve ses
features, mais sa sortie et Adam sont réinitialisés pour le nouvel objectif.

Dans la moitié des épisodes, une courte perturbation de direction survient
au début de la course. Elle varie selon l'épisode et l'environnement.
La perturbation agit sur la physique : le latent échantillonné et sa
log-probabilité PPO restent ceux de la policy. Les observations suivantes
contiennent les vraies commandes appliquées. Ce procédé entraîne les
récupérations de trajectoire sans ajouter de bonus au reward.

Chaque cycle comporte 40 mises à jour de 16 environnements × 1 024 décisions,
soit 655 360 transitions. Tous les cinq updates, 20 départs fixes sont évalués,
dont 19 avec une perturbation physique. Le classement privilégie le nombre
d'arrivées, puis le chrono moyen. Le meilleur modèle est conservé séparément.

Le cycle suivant reprend l'acteur du meilleur modèle, y compris son bruit
d'exploration, et le critique du dernier entraînement. Le critique continue
ainsi à apprendre même si aucun nouveau pilote n'a été retenu. Les moments
d'Adam sont remis à zéro pour cette combinaison de réseaux issus de deux
historiques différents. Les générateurs aléatoires les plus récents sont
conservés : le cycle explore de nouveaux échantillons. Cela
limite la dérive observée dans les longues séquences précédentes ; cela
ne garantit pas que chaque cycle améliore le modèle.

La sélection réutilise ses cas de validation. Il faut un benchmark distinct
pour mesurer les progrès hors de ces cas, et un essai dans le client pour
valider le transfert au jeu.

## Comparaisons réalisées avant la relance

Tous les chiffres ci-dessous concernent **la simulation**. Même map,
départ à zéro, commandes directes, aucune route ni contrôleur MPC.

| Variante | Budget de transitions | Validation sur 5 départs |
| --- | ---: | --- |
| Référence conservée | entraînements précédents | 5/5, moyenne 27,941 s |
| Potentiel, trois commandes | 819 200 | meilleur entraîné 5/5, 28,569 s |
| Potentiel, direction seule | 819 200 | meilleur entraîné 5/5, 28,711 s |
| Chrono seul, direction, rollouts longs | 983 040 | meilleur entraîné 5/5, 27,771 s |

Le petit gain du dernier essai ne se confirme pas en fiabilité sur les
**20 perturbations distinctes** du benchmark gelé, seed `871042` :

| Modèle | Arrivées | Moyenne des arrivées | Meilleur temps |
| --- | ---: | ---: | ---: |
| Référence | 16/20 | 28,994 s | 27,742 s |
| Chrono seul, update 25 | 15/20 | 28,894 s | 27,441 s |

La nouvelle session robuste repart donc de l'acteur de référence. Sur ses
20 cas de sélection, celui-ci termine 20/20 en 28,895 s. Ce chiffre utilise
un autre ensemble de perturbations ; il ne remplace pas le résultat 16/20.

Une initialisation par imitation d'un replay de 19,967 s, avec validation
sur un autre replay de la même map, a aussi été évaluée : **0/5 arrivées**.
Elle est écartée. La correction des poids associés aux commandes précédentes
masquées reste dans l'outil BC, mais aucun acteur issu de cet essai ne sert
à la session active.

Un essai de réglage fin (taux `2e-6`, minibatches de 1 024, bruit latent
`0.015`, rollouts de 2 048) a aussi été lancé pour 60 updates. Son meilleur
résultat sur les 20 cas de sélection ne dépasse pas la référence. Cette
variante reste séparée de la session active ; ses résultats complets sont
dans `study-fine-speed/`.

Les preuves figurent dans `local/recon/reward-0.42/`, notamment
`frozen-comparison.json`, `physics-reward-check.json`, `disturbance-check.json`
et les dossiers complets des expériences.

## État, modèle et arrêt

```sh
systemctl --user status tm2020-fall01-ppo.service
cat local/training/fall01-ppo-speed-continuous/state.json
cat local/training/fall01-ppo-speed-continuous/best.json
tail -f local/training/fall01-ppo-speed-continuous/training.log
```

Le modèle sélectionné est :
`local/training/fall01-ppo-speed-continuous/best.tmppo`.
Le checkpoint complet est `best.checkpoint` ; `latest.checkpoint` indique le
dernier état complet collecté. Les anciens modèles et l'ancienne session
`fall01-ppo-continuous` restent conservés.

Pour arrêter proprement :

```sh
systemctl --user stop tm2020-fall01-ppo.service
```

Pour bloquer également une relance tant que le marqueur existe :

```sh
touch local/training/fall01-ppo-speed-continuous/STOP
```

Supprimer ce marqueur puis démarrer le service pour reprendre. Les limites
de rétention et les protections de fichiers du superviseur 0.41 restent
actives. Le service est activé au démarrage du gestionnaire utilisateur.

Le format de policy est déjà reconnu par le SDK. **Ce modèle spécialisé
n'a pas encore terminé une course vérifiée dans le client officiel**.
La conduite en jeu garde les prérequis décrits dans
[le guide de déploiement](TRAIN_AND_PLAY_0_39.md).

La commande générale détecte maintenant les policies à une ou trois sorties.
Pour évaluer le modèle actif avec le reward actuel, dans un dossier nouveau :

```sh
python3 scripts/run_generalist_ppo.py eval \
  --library cache/reward-study-target/release/libtm2020_speed.so \
  --model local/training/fall01-ppo-speed-continuous/best.tmppo \
  --trials 20 --output local/mon-evaluation
```

## Vérifications

- Cinq tests Rust : chrono exact, annulation du potentiel, absence de farming,
  absence d'avantage à l'échec précoce, priorité d'une arrivée sur un échec.
- Comparaison de 503 ticks : physique, observations et contrôles identiques
  à la bibliothèque précédente ; seule la récompense/terminaison change.
- Test de conversion : prédictions de direction conservées à `1e-14`,
  paramètres du nouvel objectif et remise à zéro d'Adam vérifiés.
- Quatre tests de publication, rétention et protection des fichiers.
- Deux cycles CUDA complets du nouveau superviseur : 65 536 transitions,
  reprise de l'acteur du meilleur modèle, du critique récent et des états RNG.
- Trace physique du premier rollout : 60 transitions réellement perturbées
  sur 16 384, latent PPO d'origine conservé.
- Les 30 tests C++ du projet passent.
- Contrôles de la bibliothèque pure : clones isolés, encodeur partagé exact,
  entrées invalides rejetées, durée du dernier pas et reset exact. La CLI
  détecte la tête unique et termine son essai nominal en simulation.

La bibliothèque active isolée est
`cache/reward-study-target/release/libtm2020_speed.so` (reward ABI 3).
La variante potentielle utilise le même environnement via
`integrations/time-training/` (reward ABI 2). Les bibliothèques figées des
anciennes évaluations et les sources du moteur physique restent inchangées.
