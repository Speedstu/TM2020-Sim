# Session Trackmania réelle : 21 octobre 2026

## Vérifications directement sur le PC Windows

- Ubisoft Connect installé sur D:\Ubisoft\Ubisoft Game Launcher, version 174.2.13389, signature Ubisoft valide.
- L'utilisateur a confirmé sa connexion. Le lancement via Steam appid 2225070 réussit.
- Trackmania.exe s'est lancé et a accédé au menu principal après l'assistant de première utilisation.
- Paramètres de confidentialité au premier lancement : préférences ouvertes, case de partage de données pour publicités personnalisées décochée puis confirmée.
- Menu observé : **Jouer > Solo > Campagne Automne 2026 > Automne 2026 - 01**.
- L'option **Conduire seul** a été sélectionnée; le chargement de la carte et la cinématique de départ ont été observés. L'écran persiste sur **« Appuyer sur une touche »** malgré des entrées clavier synthétiques envoyées par Windows.
- Il faut que l'utilisateur clique sur le jeu et appuie sur une touche physique pour permettre une session de conduite et vérifier les états du véhicule. Nous n'essayons pas de contourner les restrictions d'entrée.
- L'analyseur Win32 natif de processus `tm2020_game_probe.exe --probe` a pu lire l'en-tête PE et les chaînes déjà identifiées, sur le processus réel démarré via Steam.
- Aucun état de véhicule réel à 100 Hz n'a été décodé. Aucune DLL n'a été injectée dans Trackmania.
- Le bridge C++ et l'outil de replay fonctionnent en hôte de test indépendant, pas en jeu. Les tests de géométrie native Stadium et de physique headless restent en échec ou non implémentés.

## Étape suivante

1. Démarrer effectivement la course solo avec un clavier physique.
2. Identifier en lecture seule, sur ce build exact et avec checksum, les pointeurs d'état physique véhicule et leurs conversions d'unités. Interdire toute valeur supposée comme un offset vérifié.
3. Capturer suffisamment de données temporelles pour valider les ticks à 100 Hz, les commandes et le mouvement en comparant à un scénario reproductible.
4. Vérifier les collisions et une implémentation native causale `step(action)`, puis seulement mesurer la qualité d'une conduite autonome.

## Commandes utiles

Lecture du module de jeu pendant son exécution :
```powershell
& 'H:\Projects\Trackmania2020-RE\native\build\tm2020_game_probe.exe' --probe
```

Régression complète du framework :
```powershell
& 'H:\Projects\Trackmania2020-RE\scripts\run-framework-tests.ps1'
```

L'utilisateur a déjà retiré toute automatisation de surveillance; elle reste désactivée.
