# Recherche Yosh / TMNF — sources vérifiées le 30 octobre 2026

Cette note distingue les explications publiques de Yosh, les capacités de ses
outils et les pistes que nous pouvons en déduire. Elle ne prétend pas reproduire
son entraînement actuel. Aucun réglage du training n'a été changé pour cette
recherche.

## Faits confirmés par les sources du créateur

| Point | Source primaire | Portée de la vérification |
|---|---|---|
| Deep-Q-Learning dans la version de 2022 | [AI Learns to Drive From Scratch](https://www.youtube.com/watch?v=SX08NT55YhA) | Explicitement annoncé dans la description du créateur ; ne prouve pas l'algorithme actuel |
| Utilisation de TMInterface | Descriptions des vidéos 2022, [2023](https://www.youtube.com/watch?v=Dw3BZ6O_8LY), [A01](https://www.youtube.com/watch?v=zFLQU70QstY) | Remerciements explicites à Donadigo pour cet outil |
| Code Python, commandes et informations numériques du jeu | [How to Make an AI Play a Video Game](https://www.patreon.com/Yoshtm/posts/how-to-make-ai-148186585) | Introduction publique uniquement ; la suite est réservée aux membres |
| Travail spécifique sur A01 | [Publication du 3 septembre 2025](https://www.patreon.com/Yoshtm/posts/new-video-to-138037843) | Yosh explique avoir commencé ce projet plus d'un an auparavant |
| Travail spécifique sur A06 | [Publication du 11 mars 2026](https://www.patreon.com/Yoshtm/posts/new-video-152759635) | Début mi-novembre 2025, environ quatre mois jusqu'à la vidéo ; ce délai inclut le projet et la production, pas un compteur d'heures GPU |
| Apprentissage d'une mécanique ciblée | [Noseboost](https://www.youtube.com/watch?v=NUl6QikjR04) | Description : RL et préparation des cartes pour mettre la voiture sur le nez |
| Comparaison et combinaison d'idées IA/TAS | [Annonce du 30 janvier 2025](https://www.patreon.com/Yoshtm/posts/new-video-to-121034673) | Intention et résultats préliminaires annoncés ; ne décrit pas toute l'implémentation finale |
| Évolution de l'algorithme | [Bonus PPO vs DQN, 14 février 2025](https://www.patreon.com/Yoshtm/posts/bonus-video-3-vs-122202969) | Titre et introduction publics ; contenu détaillé verrouillé |

Les descriptions YouTube ont été lues directement dans les métadonnées
publiques des pages vidéo. Les copies de métadonnées sont sous
`local/research/yosh-20261030/`. L'accès aux pistes de sous-titres a retourné un
contenu vide : aucune transcription intégrale ni analyse complète de la vidéo
n'est revendiquée. Les résumés générés par des sites tiers ne sont pas utilisés
comme preuve de ses détails techniques.

## Ce que TMInterface permet réellement

La [documentation officielle](https://donadigo.com/tminterface/) confirme la
modification de la vitesse de course, la lecture déterministe des commandes,
les sauvegardes natives complètes, le bruteforce et les callbacks de simulation.
Cela fournit des outils pour répéter des situations et comparer des commandes.
Ces capacités ne prouvent pas que Yosh emploie chaque fonction dans chaque
expérience. TMInterface vise Nations/United Forever ; son fonctionnement ne
constitue pas une preuve de parité de notre backend Trackmania 2020.

## Informations qui restent inconnues

- L'algorithme exact et les hyperparamètres actuels de Yosh.
- La formule précise de son reward actuel, ses pondérations et ses règles de
  terminaison ; nous ne pouvons pas lui attribuer notre `100 - temps`.
- Les distributions exactes de resets, fréquences de décision, architectures,
  tailles de replay buffers et budgets d'échantillons de ses différentes vidéos.
- La part exacte d'une policy, d'éventuels assistants et d'outils TAS dans chaque
  performance, sans accès à l'explication complète correspondante.
- Une qualification publique d'un même checkpoint fort sur toutes les cartes
  inconnues. Les projets ciblés A01/A06 ne la démontrent pas.

Le dépôt [Linesight](https://github.com/Linesight-RL/linesight) documente un autre
projet. Yosh le présente aussi parmi les autres projets RL dans la description
du Noseboost ; son code ne doit pas être attribué à Yosh.

## Déductions pour notre projet — pas une description vérifiée de son code

L'outillage de sauvegarde de l'état complet rend pertinent un test de curriculum
avec départs avant les passages qui causent nos pertes de vitesse. Ce test serait
différent du replay de courses entières lentes testé en 0.48. Il faudrait conserver
vitesse, rotation, roues, contacts, timers et historique cohérents, puis vérifier
les courses complètes ; téléporter seulement position/vitesse serait insuffisant.

Les expériences mécaniques ciblées sont une autre piste : trajectoires de virage,
sorties, atterrissages et glisse, avec un objectif de temps et une mesure à la fin
du passage. La valeur finale doit inclure l'état de sortie, pour ne pas optimiser
un segment qui ruine le suivant. Ces pistes demandent des comparatifs mesurés.

Enfin, l'objectif utilisateur d'une seule policy sur des cartes inconnues exige
un corpus varié et des séparations par carte/famille. Une spécialisation réussie
sur une piste, même avec beaucoup de seeds, n'est pas une telle qualification.
La comparaison PPO/DQN doit être faite à observations, actions, budgets et cartes
identiques ; une mention de DQN dans une vidéo de 2022 ne tranche pas ce choix.
