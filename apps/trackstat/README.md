# TrackStat — read-only Trackmania training monitor

TrackStat is a terminal dashboard for PPO and hybrid campaign training runs. It is independent of the removed graphical spectator viewer.

From the repository root:

```sh
python3 apps/trackstat/stats.py
python3 apps/trackstat/stats.py --list
python3 apps/trackstat/stats.py --once
python3 apps/trackstat/stats.py --json
python3 apps/trackstat/stats.py --select
```

Use `S` to select a run, arrows and Enter to navigate, `Tab` to cycle sessions, `A` to resume automatic selection, and `Q` or Ctrl+C to exit.

The monitor only reads training status and process metadata. It does not stop the training workers.
