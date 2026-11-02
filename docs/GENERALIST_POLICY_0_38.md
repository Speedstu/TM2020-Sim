# Une politique pour les cartes inconnues — recherche 0.38

Objectif utilisateur : entraîner une politique générale, la charger dans le
SDK, lui faire lire une carte inconnue et conduire sans replay de référence.
La même politique doit pouvoir être améliorée sur des cartes particulières
en préservant ses compétences générales. La bonne mesure est une course
complète sur des cartes jamais utilisées pour entraîner ou sélectionner les
poids, avec le même contrat de perception et d'action dans le simulateur et
dans le jeu.

Les résultats 0.37 sur Autumn 01 sont une référence de physique, de débit et
de conduite sur route connue. Ils ne démontrent pas cet objectif : la route
venait d'un replay, le correcteur fort disposait d'une anticipation physique,
et les derniers tests changeaient les perturbations, pas la carte.

## Ce que la recherche apporte

Recherche effectuée le 29 octobre 2026 sur YouTube, Reddit, les annonces Nadeo,
les dépôts des auteurs de projets RL et des publications primaires. Pour les
vidéos, les descriptions et index de chapitres accessibles ont été consultés ;
plusieurs lectures directes YouTube ont échoué. Il ne s'agit pas d'une analyse
image par image de toutes ces vidéos. Les noms de techniques servent à
construire un programme d'exercices ; aucune lecture de tutoriel ne constitue
un apprentissage ou une qualification des poids du bot.

Le [guide général de Jnic](https://www.youtube.com/watch?v=1tkVQ2uL7Iw)
indexe le contrôle aérien et les trajectoires, la glace, le braquage progressif,
les réacteurs, le drift routier, les speedslides, neoslides, rapports et
bugslides. Son [guide des rapports](https://www.youtube.com/watch?v=Sv_yP0z4ioM)
approfondit les passages de vitesse. Ces ressources donnent une bonne taxonomie,
pas des constantes physiques universelles. Le guide général date de 2021.

Le [tutoriel de Mudda](https://www.youtube.com/watch?v=4nka1MZiudI), identifié
dans les discussions de joueurs, est une piste centrale pour le fullspeed.
Le [fil de Swordie sur son guide fullspeed](https://www.reddit.com/r/TrackMania/comments/14ih3fb/)
et les [discussions sur les speedslides](https://www.reddit.com/r/TrackMania/comments/1hvoxv5/)
montrent notamment l'importance des entrées de virage et des transitions.
Les seuils de vitesse et explications causales avancés dans les commentaires
ne sont pas repris comme vérités mesurées. Le modèle doit découvrir les
domaines utiles dans la physique de la version installée.

Le [tutoriel glace de Birdie](https://www.youtube.com/watch?v=GMoW80FWjhc)
répertorie ice slides, bobsleigh, wallrides et rotations. Il date d'août 2021.
Nadeo a annoncé des [changements glace/eau pour octobre 2022](https://www.trackmania.com/news/7126),
qui retirent notamment les gains des anciens wiggles. Le
[changelog de juillet 2023](https://www.trackmania.com/news/7590?lang=en)
mentionne d'autres corrections sur glace. Récompenser aveuglément le wiggle
d'un ancien tuto serait donc un mauvais objectif. Le water bounce reste une
famille de situations à étudier ; ce n'est pas la même affirmation que
l'existence actuelle d'un gain par braquage précis pendant le rebond.

Les [changements Desert de mai 2024](https://www.trackmania.com/news/8097)
confirment également qu'une règle Stadium ne doit pas être étendue sans mesure
à toutes les voitures et transitions. Le [changelog de janvier 2026](https://www.trackmania.com/news/8952)
ajoute notamment les clones avec collision : une perception purement statique
ne suffit pas pour revendiquer toutes les cartes et tous les modes actuels.

## Mécaniques à transformer en exercices mesurables

Le fichier `config/generalist/curriculum-v1.json` décrit 34 groupes, leurs
signaux nécessaires, leurs métriques et les sources disponibles. Tous sont
explicitement marqués non appris/non qualifiés par la future politique.
Les familles moins documentées restent dans la recherche à faire.

| Famille | Compétence recherchée | Ce que le bot doit observer ou commander |
| --- | --- | --- |
| Trajectoires | Entrée, apex, sortie ; rayon et vitesse compatibles | Géométrie devant et autour, obstacles, objectif de checkpoint |
| Gaz, relâchement, frein | Choisir entre conserver et réduire la vitesse | Trois commandes indépendantes ; coût total jusqu'à la sortie |
| Rapports | Préserver l'accélération et réussir les changements | Régime, rapport, état de changement, surface et glisse |
| Smoothsteer / noslide | Doser la direction selon le contexte | Braquage analogique, adhérence, modèle de voiture |
| Drift routier | Amorcer, tenir, sortir d'un virage serré | Frein, vitesse latérale, direction et contacts |
| Neoslide | Gérer les virages serrés à plus basse vitesse | Historique court des entrées et de la glisse |
| Speedslide / S4D / autoslide | Gagner du temps par la glisse utile | Vitesse, angle de dérive, surface, pente et sortie |
| Dirt, grass, plastic | Adapter trajectoire et glisse aux transitions | Matériau par roue, contact et état des pneus |
| Airbrake / contrôle aérien | Préparer l'atterrissage | Vitesse angulaire, attitude, frein et direction ; conditionnement par voiture |
| Réduction d'airtime / ride | Choisir le décollage et retrouver le sol utile | Rampe, normale de surface et zone d'atterrissage |
| Atterrissages / sausage | Conserver vitesse et stabilité | Contacts par roue, suspension, pente et courbure latérale |
| Ice slide / slideout | Contrôler angle et récupération | Orientation versus vitesse, glisse, état des pneus, historique |
| Bobsleigh | Choisir hauteur, ligne et entrée de courbe | Section du canal, normales, vitesse et orientation |
| Eau / pneus mouillés ou glacés | Anticiper les réactions après transition | Niveau d'eau et effets temporaires par roue |
| Réacteurs et boosts | Gérer l'effet présent et sa fin | Type, direction, durée et géométrie atteignable |
| Engine-off / no-brake / cruise | Adapter l'action à la règle locale | Flags gameplay et commandes effectivement disponibles |
| Loops / wallrides | Conduire sur une route orientée en 3D | Normales, gravité et obstacles en trois dimensions |
| Snow / Rally / Desert | Apprendre les différences de comportement | Identité du modèle physique, direction, roues, transitions |
| Navigation / checkpoints / tours | Trouver une route valide | Graphe de carte, checkpoints requis/visités et mémoire |
| Récupération | Choisir de continuer ou respawn | Validité de course et temps total avec récupération |
| Clones / objets mobiles | Éviter des collisions dépendant du temps | Positions et vitesses relatives des entités |
| Bugslide / backwards / wallbang / uber | Exploits utiles dans certains passages | Contacts et dynamique, confirmation par le moteur officiel |
| Cuts / Kacky / techniques rares | Explorer des routes et contacts particuliers | Atteignabilité et règles de checkpoint ; qualification distincte |

Minimiser systématiquement le slip empêcherait d'apprendre les speedslides et
drifts utiles. Maximiser la vitesse brute peut encourager une mauvaise route,
un tour sur place ou une trajectoire incapable d'atteindre le checkpoint.
La métrique commune doit rester la progression valide, le taux d'arrivée et
le temps total. Les métriques de glisse, régime et contacts servent au
diagnostic et éventuellement à des objectifs auxiliaires bornés.

Les comparaisons de mécanique doivent partir d'états complets identiques,
inclure entrée et sortie de section, et être regroupées par voiture, surface,
état des pneus et build. Les quelques seuils d'un guide humain ne remplacent
pas ces mesures. Les bugs rares ne sont pas des prérequis pour savoir finir
les cartes ordinaires.

## Une seule politique et une lecture automatique de la carte

Architecture proposée, encore à entraîner et à valider :

1. Charger le GBX et ses assets ; identifier géométrie, surfaces, triggers,
   règles de checkpoint et obstacles dynamiques. La géométrie doit être celle
   du jeu, pas une ligne extraite du replay d'un joueur.
2. Construire un graphe de connectivité praticable, en tenant compte des voies
   superposées, passages sautés, sauts, sens de checkpoint et embranchements.
   Les centres des checkpoints seuls ne sont pas un itinéraire conduisible.
3. Encoder localement route, obstacles et objectifs, avec la télémétrie de la
   voiture et une mémoire récurrente. Les entrées sont dans un repère relatif
   à la voiture, sans nom ni UID de carte, temps cible ou commande future.
4. Utiliser un acteur-critique partagé : le même checkpoint prend les décisions
   de braquage, gaz et frein sur toutes les cartes prises en charge. Une tête
   de récupération ou un protocole mesuré doit aussi gérer les respawns.
5. Faire varier cartes, courbes, surfaces, entrées, voitures et états physiques
   au cours de l'entraînement. Les symétries doivent être vérifiées : inverser
   une trajectoire dans un monde asymétrique ne crée pas un exemple valide.

Cette architecture est une hypothèse de conception, pas une garantie de niveau
sur une carte arbitraire. Les limites physiques, les passages qui demandent de
l'exploration et les cartes Kacky peuvent exiger plusieurs essais. Un seul
modèle peut être conditionné par le modèle de voiture, les effets et un objectif
de risque sans devenir un fichier de poids différent pour chaque carte.

Une spécialisation qui conserve un seul modèle doit continuer à échantillonner
les anciennes cartes et familles de compétences pendant l'amélioration sur
les nouvelles. On compare la nouvelle version à la précédente sur les styles
déjà acquis. Un fine-tuning sur une seule carte sans ces contrôles peut dégrader
les autres compétences. Le jeu final de test reste figé et n'entre pas dans
la sélection ; une fois utilisé pour décider des changements, il devient un
jeu de développement et doit être remplacé pour la mesure finale.

Les sources RL consultées confortent surtout la nécessité de mesurer :
[TMRL](https://github.com/trackmania-rl/tmrl) fournit des interfaces vision et
télémétrie ; [TrackmaniaRL](https://github.com/TrackmaniaRL/TrackmaniaRL) décrit
des encodeurs de géométrie et précise que son film assisté n'est pas une preuve
de généralisation. [Linesight](https://github.com/Linesight-RL/linesight) vise
TMNF et ses records ne qualifient pas notre futur agent TM2020. Les résultats
publiés sur [la généralisation en RL](https://proceedings.mlr.press/v97/cobbe19a.html)
expliquent pourquoi des niveaux de test distincts sont nécessaires. Aucun de
ces projets ne justifie une promesse « fort sur absolument toute carte ».

## Travail de code exécuté dans cette reprise

`integrations/generalist-perception` est un nouveau prototype GPL, utilisant
les sources physiques amont inchangées. Il accepte seulement **MAP, PACKS,
OUTPUT**, sans argument replay. Il produit 40 sondes de sol, 26 sondes
d'obstacles, normales, matériaux, télémétrie locale et triggers de checkpoint.
Le nom et l'UID ne figurent que dans les métadonnées de diagnostic. Les sondes
sont répétées après restauration complète et doivent être identiques.

```sh
cargo build --release --offline --locked \
  --manifest-path integrations/generalist-perception/Cargo.toml \
  --target-dir cache/generalist-perception-target
cache/generalist-perception-target/release/tm2020-map-perception \
  local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx \
  /chemin/Trackmania/Packs local/ma-perception.json
```

Trois cartes ont été chargées avec cette interface : Autumn 01, Great wtf of
what #165 et Adventure Land. Les 66 sondes ont le format attendu ; les points
renvoyés correspondent aux segments locaux à moins de 0,1 mm dans ces essais.
Cela vérifie le repère et l'accès à la géométrie, **pas la navigation**. Une
sonde peut toucher le terrain sous la piste : matériaux et connectivité sont
encore nécessaires pour distinguer ce qui est conduisible. Les convexes,
effets temporaires et objets mobiles réclament aussi leur qualification.

`scripts/build_generalist_corpus.py` regroupe les replays d'une même carte,
les copies de géométrie identique et les familles déclarées avant séparation.
Le corpus local exploratoire contient 21 cartes, divisées ici en **16 train,
2 validation, 3 test**, avec 18 groupes indépendants. Autumn 01 reste dans
l'entraînement puisqu'elle a déjà servi à apprendre. Les variantes déclarées
`100x` restent ensemble. Ce petit corpus de TAS et de cartes atypiques n'est
pas représentatif des compétences générales recherchées : il faut le compléter
par de nombreuses cartes normales et des exercices ciblés.

```sh
python3 scripts/build_generalist_corpus.py \
  --families config/generalist/map-families.json \
  --extra-map local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx \
  --known-training-uid ypPmohQofd72MyTsIsijKfrJH98 \
  --output local/mon-decoupage-generaliste.json
python3 scripts/test_generalist_corpus.py
```

Les fichiers et métadonnées sont vérifiés par hash et UID. La détection de
copies exactes ne découvre pas chaque remix tourné, déplacé ou modifié : des
familles doivent aussi être déclarées. Toute initialisation depuis d'anciens
poids exige de connaître toutes leurs cartes d'entraînement ; sinon il faut
repartir de poids neufs pour prétendre à ce test de généralisation.

## Ce qui manque avant de livrer la politique demandée

Le PPO rapide 0.37 peut produire trois commandes, mais son meilleur essai était
plein gaz/sans frein et dépendait d'une ligne connue. Le nouveau curriculum est
un contrat de recherche, pas un trainer multi-cartes déjà connecté. Il reste
à intégrer la navigation, le schéma d'observation partagé, l'échantillonnage
multi-cartes, la mémoire et les tests de mécaniques.

Le runtime `native/include/tm2020/runtime.h` est actuellement Windows ; le
chemin `read_only_live.hpp` décrit des observations visuelles dont l'appartenance
physique et l'horloge ne sont pas toutes qualifiées. `drive_session.cpp`
charge encore un résidu associé à une carte/replay. **On ne peut donc pas
charger les nouveaux poids généralistes dans ce runtime en prétendant que
le transfert est déjà résolu.** La parité perception/action et la gestion
de carte courante doivent être ajoutées et mesurées, notamment sous Proton
sur ce PC Linux. Les intégrations Openplanet d'autres projets ne sont pas
utilisées comme substitut silencieux au SDK demandé.

La sortie attendue de cette évolution est un modèle partagé figé, une version
du SDK qui fournit exactement ses observations, une prise en charge explicite
des cartes/effets, et des rapports par famille sur des cartes nouvelles :
arrivées, DNF, respawns, temps de première arrivée, puis temps après nombre
fixe d'essais. La maîtrise d'une mécanique n'est cochée qu'après des exercices
physiques réussis et une confirmation dans le jeu original.
