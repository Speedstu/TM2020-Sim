# Reprise après la version 0.6.0

**Historique remplacé par `NATIVE_0_7_0.md`.** La session suivante a relancé
le jeu normalement, validé une arrivée injectée en 24,114 s (or), deux
mises à jour PPO réelles et une évaluation séparée. Le blocage décrit ici
n’est plus le dernier état du projet.

La version et les limitations actuelles sont dans `NATIVE_0_6_0.md`.
Le handoff original n’a pas été modifié. Le jeu est resté lancé sous le
PID 12172 pendant les derniers essais ; ce PID et les adresses sont
éphémères. Toujours vérifier le processus actuel.

## Priorité : rétablir une course qui avance

La demande Windows « Steam Client Service » reste ouverte. Les tentatives
de clic « Non » et d’Échap par l’outil n’ont pas fermé ce dialogue.
Ne pas accorder une élévation pour qualifier le SDK. Le jeu a été relancé
normalement depuis son exécutable installé, sans élévation, et son menu
Solo a été rejoint. La présentation du circuit ne s’est toutefois pas
transformée en course active lors des derniers essais. Un clic humain
sur « Non » est la prochaine action utile pour lever cette ambiguïté.

Le worker refuse maintenant un `RaceStartTime == -1` avant d’envoyer des
actions de pilotage. Ne pas désactiver ce contrôle ou celui de l’horloge
pour faire passer une qualification. Les snapshots actuels peuvent être
décodables tout en étant gelés.

Après retour dans le Solo actif et voiture au départ :

```powershell
scripts/run-native-live-bootstrap.ps1 -ConfirmLocalSolo -Samples 30
scripts/run-injected-bot.ps1 -ConfirmLocalSolo -Seconds 55
```

Lire le statut du worker, le PID du host dans la trace, les commandes
effectivement reçues, la progression et l’écran de résultats. Le script
conserve les échecs ; il n’affirme pas une arrivée à partir de la seule
progression sur la référence. Le contrôleur externe possède une arrivée
historique confirmée ; le pilotage injecté n’en possède pas encore.

## PPO : prouver la collecte, puis évaluer séparément

L’adaptateur et ses tests natifs sont présents. Le modèle résiduel reste
inchangé pendant chaque collecte et la mise à jour vérifie les anciennes
log-probabilités et valeurs. Les derniers essais n’ont pas produit de
mise à jour PPO en jeu : un `.behavior.tmppo` seul n’est pas une preuve
d’entraînement. Il faut aussi un `.rollout.csv`, un `.ppo.csv` valide et
une trace de pilotage réelle cohérente.

Comparer ensuite plusieurs arrivées sans exploration, à réglages identiques,
sur des essais distincts de ceux utilisés pour les mises à jour. Ne pas
transformer une baisse de loss, une modification des poids ou un benchmark
synthétique en affirmation de gain de chrono. Ajouter une sauvegarde
transactionnelle des moments Adam et du RNG avant les entraînements longs.

## Propriétaire physique : piste encore non prouvée

La réflexion expose `CSceneVehicleVis::AsyncState` à 0x130 et une étendue
enregistrée de 0x10a8. Les factories observées sont 0x73f730 et 0x73f840,
avec initialisation à 0x73f760. Cela ne prouve pas qu’une copie visuelle
trouvée en mémoire est un sous-objet du propriétaire joueur.

```powershell
python scripts/probe_visual_parents.py `
  local/recon/live-cpp-12172-v3.txt.visual-cache `
  local/recon/visual-parent-hypotheses-12172.json
```

Le dernier relevé comporte 16 états visuels décodables et **zéro horloge
qui avance** en 200 ms. Un candidat donne un premier mot parent 6 après
soustraction de 0x130 ; la majorité donne des zéros. Les types des slots,
la relation d’objet et la propriété du joueur restent inconnus. Ne pas
publier cette soustraction comme pointeur physique stable. Exiger une
corrélation temporelle avec les entrées, des relations de type corroborées
par le désassemblage et une nouvelle validation après redémarrage.

## Incident à préserver

L’ancien module `tm2020-runtime-d14b38a0aba5b071.dll` contient une allocation
de pile SHA supérieure à la réserve par défaut du jeu. Il sert à l’analyse
statique de régression et ne doit plus être injecté. Le SDK actuel utilise
un tampon sur le tas ; sept tests CTest, dont un worker de 256 Kio,
vérifient la réparation. Les modules chargés ne sont pas remplacés ; les
nouvelles versions portent leur hash dans leur nom.
