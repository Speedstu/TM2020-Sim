# Comparaison de projets ML Trackmania et audit du pipeline local

Recherche effectuée le 30 octobre 2026. Les sources primaires ont été lues,
puis comparées au code réellement exécuté et à un audit natif sans mise à jour
des poids. Le training principal continue. Aucun nouveau modèle n'est injecté
dans le jeu dans le cadre de cette recherche.

## Projets examinés

| Projet | Éléments vérifiés dans le code/documentation | Limite de comparaison |
|---|---|---|
| [Linesight](https://github.com/Linesight-RL/linesight) | IQN, replay, mini-courses de 7 s, commandes discrètes parmi 12 combinaisons, décision toutes les 50 ms. Entrées : état physique, historique de commandes, image et points de trajectoire devant la voiture. | TMNF, autre véhicule/jeu et protocole. Les auteurs présentent leurs courses comme tool-assisted. |
| [TMRL](https://github.com/trackmania-rl/tmrl) | TM2020, SAC/REDQ et mémoire de replay. Son reward de progression compare la position à une trajectoire de référence. | Son interface de contrôle externe n'est pas à reprendre pour notre runtime interne. Ce projet ne démontre pas qu'un changement d'algorithme suffirait ici. |
| [TrackmaniaRL](https://github.com/TrackmaniaRL/TrackmaniaRL) | Documentation d'imitation avec contrats de données, validation en boucle fermée, DAgger et transfert de poids compatibles vers RL. | Le film mis en avant emploie un filtre d'actions spécifique à la map ; ce n'est pas une preuve de policy autonome universelle. |

Sources détaillées :

- Linesight : [configuration](https://github.com/Linesight-RL/linesight/blob/f6e7822fcb91d10bafd9b8db070a1dee78046558/config_files/config.py), [actions](https://github.com/Linesight-RL/linesight/blob/f6e7822fcb91d10bafd9b8db070a1dee78046558/config_files/inputs_list.py), [état fourni au réseau](https://github.com/Linesight-RL/linesight/blob/f6e7822fcb91d10bafd9b8db070a1dee78046558/trackmania_rl/tmi_interaction/game_instance_manager.py), [mini-courses et replay](https://linesight-rl.github.io/linesight/build/html/main_objects.html).
- Linesight : [trajectoire de référence](https://linesight-rl.github.io/linesight/build/html/second_training.html). Elle peut suivre le milieu de la piste sans être une trajectoire rapide ; elle sert à mesurer la progression. Cela diffère d'une obligation d'imiter le ghost WR.
- TMRL : [algorithmes](https://github.com/trackmania-rl/tmrl), [calcul de progression](https://github.com/trackmania-rl/tmrl/blob/10266a7d2351e727f51ab302b3dd6592895d1763/tmrl/custom/tm/utils/compute_reward.py).
- TrackmaniaRL : [imitation/DAgger](https://github.com/TrackmaniaRL/TrackmaniaRL/blob/eb803a2153d472ebb16cd7150201c82058dd804a/readme/imitation-learning.md), [provenance et limites du film](https://github.com/TrackmaniaRL/TrackmaniaRL/blob/eb803a2153d472ebb16cd7150201c82058dd804a/docs/neural-flow-media.md).

Les 15 fichiers retenus sont archivés sous
`local/research/ml-projects-20261030/`, avec commits, URL et SHA256 dans
`sources.json`. Aucun code de ces dépôts n'a été exécuté.

## Constats locaux confirmés

### 1. Le curriculum ne progresse pas

Le service exécute sa copie figée de `train_top10.py` et `top10_core.py`.
Le premier exercice utilise les banques 30 à 39, soit environ 15 à 19,5 s
du ghost de 19,988 s. La fraction de ces départs est de .8 initialement,
puis .6 et .35 selon les phases de plateau.

La condition de passage à une banque plus précoce demande au moins 32
résultats récents, 85 % de réussites et un chrono absolu inférieur ou égal
à 21 s. Ce seuil n'est pas le reward, mais c'est un seuil dur du curriculum.
À l'update 212 : banque minimum toujours 30, phase 3, réussite récente
d'environ 36 %. Les changements de phase reviennent aux meilleurs poids
et parcourent les mêmes trois combinaisons de paramètres. Rien ne garantit
qu'ils permettront de sortir de ce blocage.

Conséquence : une grosse part de l'effort vise à récupérer des états très rapides
d'un expert en fin de course, tandis que l'agent doit aussi apprendre une
trajectoire cohérente depuis son propre début de course. Le décalage des
distributions est confirmé par la construction des resets ; son effet causal
sur les chronos doit être mesuré dans une expérience séparée.

### 2. L'agent reçoit un état et une anticipation incomplets

`environment.rs::observation` produit 48 valeurs : vitesse locale, verticale
locale, vecteur du prochain checkpoint, commandes précédentes, rapport, deux
canaux contact/turbo et 33 rayons statiques. Les deux derniers canaux physiques
sont volontairement masqués, car leur lecture dans le client n'est pas qualifiée.
Les rayons horizontaux ont une portée de 80 m ; les sondes verticales vont
jusqu'à 65 m devant la voiture. Ils ne fournissent pas les types de surface.

Il n'y a pas de suite explicite des virages à venir, de largeur de piste,
de vitesse angulaire, de régime moteur, ni d'état des roues dans les entrées.
La DLL lit déjà un état rigide qui contient une vitesse angulaire, mais son
encodeur `raw[21]` ne la transmet pas au réseau. L'historique permet d'inférer
une partie de la dynamique ; il ne remplace pas toute cette information.

Dans les quatre courses auditées, 45 % des rayons horizontaux sont à leur portée
maximale. Ce chiffre seul ne prouve pas qu'ils sont inutiles, mais les rayons ne
constituent pas une description complète de la route. Pour généraliser, une
anticipation extraite de la géométrie de chaque map est à privilégier ; le
ghost WR d'une seule map ne fournit pas cette capacité.

### 3. L'exploration des pédales reste indépendante du bruit de direction

`Policy.action` tire gaz et frein avec deux Bernoulli. `logstd` ne règle que
le bruit gaussien de direction. Diminuer sigma à .015 ou .008 n'arrête donc
pas les changements de pédales pendant l'entraînement.

Audit du checkpoint figé SHA256
`afe6ac8c949667eef0134b5eea19dd5c106afb4de5eb4b1463b9d5a2b5b7c2f4` :

- 1 928 décisions sur quatre nouvelles courses nominales ;
- sigma de direction : .015 ;
- probabilité moyenne de conserver exactement le même bin de direction après
  bruit : 36,9 % ;
- somme des probabilités de différer de la commande déterministe : 6,69 pour
  le gaz, 7,60 pour le frein, sur ces quatre parcours ;
- 3,58 % des états ont une direction déterministe d'amplitude supérieure à .99.

Ce sont des probabilités sur les états de courses déterministes, pas le comptage
de fautes de courses stochastiques, ni des actions observées dans le jeu.
Elles motivent un test de l'exploration, sans conclure qu'il faut la supprimer.

### 4. Le reward récompense bien chaque gain de temps, mais privilégie fortement la réussite

Le retour d'une course complète réussie vaut `100 - temps_secondes`, contre
`-140` en échec. Le facteur .01 d'entraînement ne change pas leur rapport.
Exemple : finir en 24 s rapporte 76, finir en 23 s rapporte 77. Si le deuxième
comportement échoue avec probabilité p, son espérance vaut `77 - 217*p`.
Un risque d'échec de seulement `1/217`, soit environ .46 %, annule le gain.
24 s n'est qu'un exemple de calcul, aucun objectif du code.

Ce choix est cohérent avec une forte exigence de fiabilité, mais peut rendre
l'exploration d'une trajectoire plus rapide coûteuse. Ce n'est ni un bug de
signe ni une preuve que le reward cause à lui seul le plateau.

Avec lambda .995 à 20 Hz, le terme terminal direct de l'estimateur GAE à
20 s de distance est multiplié par .1347. Le critic peut transmettre du crédit
par ses estimations : ce facteur ne signifie donc pas que le début n'apprend rien.
L'ablation 0.48 de lambda 1 et du potentiel de distance au checkpoint n'a pas
amélioré l'incumbent. La répéter sans hypothèse nouvelle ne serait pas un progrès.

### 5. Nos comparaisons ne permettent pas de choisir le meilleur algorithme

Le PPO actuel est on-policy : après ses quatre epochs, les transitions ne
sont pas conservées dans une mémoire de replay d'apprentissage. C'est normal
pour cet algorithme. Coller un replay SAC dans PPO sans correction serait erroné.
Les essais PPO continu/17/33 ne comparent pas PPO à IQN ou SAC, et leurs
résultats ne prouvent donc pas qu'une famille entière d'algorithmes est inférieure.
Les différences de cadence et d'historique du pilote 100 Hz empêchent aussi
d'attribuer son échec à la seule fréquence.

La BC précédente utilisait deux traces expertes nominales, sans collecte
de corrections sur les états réellement visités par la policy, et sans séparation
des démonstrations par course. Son échec en boucle fermée est compatible avec
un manque de couverture des erreurs ; la perte supervisée ne suffit pas à valider
la conduite. DAgger exige un expert capable de répondre sur les états déviés :
rejouer simplement les commandes d'un ghost à l'horloge ne le remplace pas.

### 6. Les 41 départs ne constituent pas une validation générale

Ces départs servent à sélectionner les checkpoints. Ils ne sont donc pas un
holdout. Ils perturbent surtout le début, sur une seule map, et ne testent pas
toutes les sorties de virage, réceptions, surfaces ou maps inconnues.
Les mécanismes internes du client restent testés séparément. Une arrivée
ancienne de l'export 0.46 n'est pas une arrivée du nouveau checkpoint.

## Priorités proposées et expériences nécessaires

1. Tester le curriculum sur des états issus des propres courses de l'agent,
   répartis sur tout le parcours, contre les banques WR actuelles. Définir
   la progression par section et un budget de plateau, plutôt que dépendre
   uniquement d'une arrivée sous 21 s. Même source, seeds et budget physique.
2. Donner un aperçu de route à plusieurs distances et la vitesse angulaire,
   avec un nouveau schéma d'observations explicite. Qualifier la parité
   simulateur/DLL avant tout entraînement long. Ne pas réactiver des offsets
   contact/turbo supposés ; les nouveaux champs doivent être validés.
3. Tester séparément une exploration des pédales plus cohérente et des actions
   maintenues, en conservant l'agent actuel comme témoin. Mesurer l'entropie
   après quantification et les résultats de courses stochastiques et déterministes.
4. Une fois l'information et les resets corrigés, comparer PPO à une branche
   off-policy adaptée (IQN discret ou SAC avec pédales adaptées), avec les mêmes
   observations, seeds, durée physique générée et temps de calcul rapporté.
   Les démonstrations et leur utilisation doivent être identiques ou déclarées
   comme un facteur expérimental distinct.
5. Garder un jeu de départs de développement fixe, puis une qualification
   indépendante fraîche et la vérification de la véritable arrivée locale.
   L'entraînement sur plusieurs maps et un split par maps seront nécessaires
   pour évaluer l'objectif ultérieur de généralisation.

La priorité est de corriger les informations et les distributions d'entraînement,
puis de mesurer les algorithmes. Rien ici ne démontre que 100 Hz, plus de SPS,
un énorme malus ou un changement isolé de reward donnera le top 10.

## État et reproductibilité

À l'update 212, le meilleur modèle est celui de l'update 192 : 41/41 arrivées
de développement, moyenne 23,707 s, médiane 23,408 s, meilleur temps 23,304 s.
Le précédent update 32 avait un meilleur temps isolé de 23,268 s, mais une
moyenne moins bonne de 23,770 s. La sélection optimise la fiabilité puis la
moyenne ; ces deux valeurs ne doivent pas être confondues.
Le meilleur chrono réellement vérifié dans le client reste 23,366 s.

Preuves locales : `local/research/ml-projects-20261030/training-snapshot.json`,
`local-audit/report.json` et poids figés `local-audit/audited.pt`.
L'audit se reproduit avec :

```sh
tools/venv-gpu/bin/python scripts/audit_ml_pipeline.py --output local/research/ml-audit-NOUVEAU
```

Le script conserve une copie du checkpoint, ne fait aucun pas d'optimiseur,
n'accède pas au jeu et ne change pas le service actif. Ses quatre nouvelles
seeds sont un diagnostic ponctuel ; toute utilisation ultérieure pour choisir
un candidat les transformerait en données de développement.
