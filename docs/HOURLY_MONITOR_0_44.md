# Surveillance horaire et progression — 0.44

Le timer utilisateur **`tm2020-training-monitor.timer`** déclenche
`tm2020-training-monitor.service` chaque heure. C'est un programme local de
supervision et d'essais PPO encadrés, indépendant de cette conversation.
Il ne réveille pas un agent conversationnel pour réécrire librement le code.
Le PC doit être allumé ; `Persistent=true` rattrape un contrôle manqué lorsque
le gestionnaire utilisateur redémarre. Le linger utilisateur est activé.

Le timer utilise l'heure du PC, Europe/Paris, avec un décalage de quelques
secondes. Une exécution de test a réellement été déclenchée par ce timer à
**03:53:51 CET le 30 octobre 2026**, avec `Result=success` et `ExecMainStatus=0`.
La modification temporaire servant à ce test a été retirée. La configuration
permanente reste `OnCalendar=hourly`.
Le passage horaire réel de **04:00:06 CET** a ensuite été observé avec un
nouveau rapport et un retour sans erreur. Le timer demeure actif entre deux
contrôles ; le service ponctuel, de type `oneshot`, s'arrête normalement
après chaque contrôle.

## À chaque passage

1. Contrôler le service d'entraînement et son dernier checkpoint. Un service
   activé mais arrêté, ou sans progression depuis dix minutes, est relancé.
   Un marqueur `STOP` ou un service désactivé est respecté.
2. Copier un ensemble cohérent modèle/checkpoint/métadonnées du champion.
   La copie vérifie le hash et l'égalité des paramètres du modèle avec ceux
   du checkpoint, même si une promotion intervient pendant la lecture.
3. Lire les arrivées, chronos, transitions et l'espace disque disponible.
4. Actualiser le seuil du top 10 mondial de la map depuis l'API publique
   Trackmania.io. Si la récupération échoue, le seuil est signalé indisponible
   et aucune progression de map n'est autorisée.
5. Après une heure sans amélioration, tester un réglage PPO pendant 40 updates.
   La recherche tourne parmi six couples de taux d'apprentissage/bruit de
   direction. La physique, le reward et les observations restent identiques.
6. Garder une variante seulement si elle bat la sélection habituelle de
   20 départs et ne régresse pas sur une seconde série de 20 perturbations.
   Les critiques récents et la continuité des RNG sont préservés ; l'état
   Adam du candidat est réinitialisé pour son nouvel historique.
7. Écrire le compte rendu et reprendre l'entraînement continu après l'essai.

Les essais sont limités, séparés des cycles principaux et enregistrés avec
leurs propres nombres de transitions. Ils ne sont pas ajoutés au compteur
principal. Leur exécution suspend brièvement le service principal pour
éviter deux entraînements concurrents. Un `finally` le relance après un
échec d'essai ou une interruption gérée.

La recherche de réglages n'est pas une garantie de niveau top 10. Elle ne
modifie pas automatiquement l'architecture ni le moteur. Elle conserve le
meilleur modèle lorsqu'aucun candidat n'améliore les résultats mesurés.

## Condition pour passer à la map suivante

Le plan suit les **25 maps de Fall 2026**, dans l'ordre de la
[campagne publiée](https://trackmania.io/#/campaigns/seasonal/157584).
La map 02 a été téléchargée, son UID a été vérifié et son chargement/stepping
dans le backend a été testé. Les suivantes sont téléchargées au besoin.

Pour la map 01, UID `ypPmohQofd72MyTsIsijKfrJH98`, le dixième du classement
public relevé le 30 octobre 2026 est à **20 006 ms**. La requête utilisée est
`https://trackmania.io/api/leaderboard/map/ypPmohQofd72MyTsIsijKfrJH98?length=10&offset=0`.
Il s'agit du classement mondial des records personnels de la map, et non du
classement Ranked ou d'un classement national. Trackmania.io peut mettre en
cache les données de Nadeo ; le seuil est relu à chaque contrôle.

Un bon chrono en simulation déclenche une vérification :

- le modèle est figé et identifié par son SHA-256 ;
- un ghost de la bonne map fournit le cadre de course et le seed de
  validation ; ses commandes ne sont pas les décisions du bot ;
- les commandes produites par la policy sont rejouées dans le serveur
  officiel épinglé du projet ;
- les dix floats rigides observés sont comparés bit par bit à chaque tick,
  puis le temps et le nombre de checkpoints calculés par ce moteur sont
  vérifiés ;
- seul un temps officiel **strictement inférieur** au seuil du dixième,
  avec le bon UID, le même modèle et un seuil récupéré depuis moins de deux
  heures, peut autoriser la progression.

La stricte inégalité évite d'affirmer une position sur une égalité de chrono.
Il s'agit d'une qualification de **niveau chronométrique** sur le moteur
officiel. Le programme ne publie aucun record dans le classement en ligne.
Le ghost conserve des déclarations de son fichier source ; cette procédure
ne constitue pas une soumission de replay homologué au classement.

Quand la condition est satisfaite, le modèle qualifié et ses preuves sont
archivés. La map suivante est chargée et évaluée avant de remplacer l'unité
d'entraînement. La même architecture et l'acteur qualifié servent de départ,
avec un critique/Adam réinitialisés pour la nouvelle spécialisation. Les
champions antérieurs restent disponibles. Cela ne garantit pas l'absence
d'oubli entre maps ni une maîtrise générale des mécaniques.

Le service suivant doit réellement produire des transitions avant que la
bascule soit considérée réussie. En cas d'échec de démarrage, l'ancienne
unité est restaurée et le service précédent est relancé. Les noms des
services restent stables, même quand la map change.

## Lire le suivi

```sh
systemctl --user list-timers tm2020-training-monitor.timer
journalctl --user -u tm2020-training-monitor.service -n 30 --no-pager
cat local/monitoring/fall2026/status.md
cat local/monitoring/fall2026/latest.json
cat local/monitoring/fall2026/active.json
```

`active.json` indique la map et le dossier d'entraînement courants.
`history.jsonl` conserve les comptes rendus successifs. Les 48 derniers
contrôles complets ordinaires sont conservés, ainsi que les qualifications
de maps et les essais ayant promu un champion. Les traces de travail des
essais sont réduites au premier et au dernier update ; les meilleurs
modèles et les rapports restent accessibles.

Un contrôle peut aussi être lancé immédiatement :

```sh
systemctl --user start tm2020-training-monitor.service
```

Un état `CHECK_FAILED` entraîne un code de sortie non nul visible dans
systemd. Les erreurs restent dans le rapport. Le prochain passage horaire
reste programmé. Un verrou empêche deux contrôles de se superposer.

Pour arrêter le monitoring et le training :

```sh
touch local/monitoring/fall2026/STOP
systemctl --user disable --now tm2020-training-monitor.timer
systemctl --user stop tm2020-training-monitor.service
systemctl --user stop tm2020-fall01-ppo.service
```

Retirer le marqueur, activer le timer et démarrer les services pour reprendre.

## Sources, configuration et preuves

- `config/training-monitor/fall2026.json` : plan des maps et politique de suivi.
- `scripts/training_monitor.py` : contrôle, snapshots, essais, promotion,
  progression et restauration de l'unité en cas d'erreur.
- `scripts/validate_generalist_policy.py` : vérification sur le moteur officiel.
- `integrations/training-metadata/` : parsing du GBX par le codec déjà utilisé
  par le projet ; UID et seed lus du fichier, sans valeur inventée.
- `config/systemd/tm2020-training-monitor.{service,timer}` : unités installées.
- `local/recon/monitor-0.44/timer-verification.json` : déclenchement automatique
  réel, rapport résultant et retour à la cadence horaire normale.
- `local/monitoring/fall2026/runs/20261030T024955379158Z/` : essai réel de quatre
  updates, candidat refusé (19/20 arrivées), champion préservé et reprise de
  l'entraînement vérifiée.

Les tests vérifient notamment le refus des validations simulées, d'un mauvais
UID/modèle, d'un seuil périmé ou national, d'une égalité au dixième, des données
de classement incomplètes, et d'une copie mélangeant deux champions. La relance
d'un service figé est testée, le marqueur `STOP` est respecté et un échec de
chargement de la map suivante ne remplace pas le service courant.
