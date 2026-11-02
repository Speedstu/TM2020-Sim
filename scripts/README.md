# Points d’entrée

Exécuter depuis la racine du projet. La plupart des scripts de recherche
nécessitent `tools/venv-gpu/bin/python`. Les deux outils de consultation/nettoyage
ci-dessous utilisent uniquement la bibliothèque standard Python.

| Besoin | Script | Effet |
|---|---|---|
| État réel, chemins, empreintes des modèles figés | `project_status.py` | Lecture seule ; `--json` pour exporter |
| Plan de nettoyage | `clean_workspace.py` | Lecture seule par défaut ; `--apply` journalise puis supprime les seuls éléments admissibles |
| Optimisation hardcodée humaine | `train_hardcode_recorded_inputs.py` | Entraîne et écrit des checkpoints ; actuellement en pause |
| Campagne ordonnée | `run_hardcode_human_campaign.py` | Lance les recherches et audits ; actuellement en pause |
| Audit 64 seeds normales et 64 perturbées | `audit_hardcode_execution.py` | Exécute la physique locale, sans injection |
| Profils des ghosts Top 100 | `build_human_rhythm_profiles.py` | Produit les profils de rythme |
| Décodage des replays originaux | `analyze_human_replays.py` | Produit timelines et métriques |
| Comparaison sim/humains | `compare_human_sim_inputs.py` | Produit un rapport statistique |
| Essai interne client | `run_internal_trial.py` | Attache le runtime ; lire les limites avant utilisation |

Les fichiers `test_*.py` sont les régressions et audits. Les scripts de PPO,
recherche RE et PowerShell sont conservés pour reproduire les anciennes étapes ;
leur présence ne signifie pas qu’ils font partie du training actif.

Consulter [la carte des sources et données](../docs/WORKSPACE.md) et
[les consignes à la racine](../README.md) avant une reprise. Un `--help` n’est pas
une commande de lancement de training ; aucun lanceur automatique n’a été ajouté.
