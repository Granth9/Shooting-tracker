# ISSF Skeet Analytics Engine

Python CLI + SQLite library for granular ISSF 25-target International Skeet tracking:
ballistic lead helpers, Markov doubles analysis, station difficulty (SDI), diagnostic
deltas, and Banister / ACWR / Peak Readiness Score periodization.

## Install

```bash
cd Shooting-tracker
python -m pip install -e ".[dev]"
```

## Quick start

```bash
# Create database
skeet init-db --db skeet.db

# Seed demo data (12 rounds + 30 training-load days)
skeet demo-seed --db skeet.db

# Reports
skeet report summary --db skeet.db
skeet report station --db skeet.db
skeet report doubles --db skeet.db
skeet report readiness --db skeet.db

# Ballistics helper (range m, crossing angle deg, engagement time s)
skeet ballistics --R 35 --theta 90 --t 0.4
```

## Ingest a round

JSON (station / house / pair filled from the official ISSF sequence):

```json
{
  "round_id": "2026-03-01-r1",
  "event_type": "practice",
  "round_number": 1,
  "location": "Home Club",
  "wind_speed_mph": 4,
  "shots": [
    {"sequence_order": 1, "is_hit": true},
    {"sequence_order": 2, "is_hit": true},
    "... 25 shots total ..."
  ]
}
```

```bash
skeet add-round --json round.json --db skeet.db
```

Or a quick H/M pattern (length 25):

```bash
skeet add-round --hits HHHHHHHHHHHHHHHHHHHHHHHHH --event-type practice --round-number 1
```

Training load (for Banister / ACWR):

```bash
skeet add-load --date 2026-03-01 --workload 75 --notes "two rounds + drills"
```

## Schema

See [`relational_skeet_schema.sql`](relational_skeet_schema.sql):

- `rounds` — event type, round number (1–5), wind, choke, notes
- `shots` — sequence 1–25 with station, house, double/pair, hit, miss direction
- `training_loads` — daily workload for periodization

## Analytics formulas (implemented)

| Module | Metrics |
|--------|---------|
| `ballistics` | \(v_{clay}(t)\), \(d_{clay}(t)\), lead \(L\), \(\omega_{gun}\) |
| `analytics.markov` | \(P_{double}\), \(E_t\), \(D_f\), \(OR_{double}\) |
| `analytics.stations` | \(SDI_s\) (weights 0.4 / 0.3 / 0.3) |
| `analytics.diagnostics` | \(\Delta_p\), \(\Delta_{Fatigue}\), \(\Delta_{Wind}\) |
| `analytics.periodization` | Banister \(p(t)\), ACWR EWMA, PRS |

Defaults: \(\tau_1=45\), \(\tau_2=15\); \(\lambda_{acute}=0.25\), \(\lambda_{chronic}=0.069\).

## Library usage

```python
from skeet_tracker.db import init_db, get_connection
from skeet_tracker.ingest import insert_round, round_from_dict
from skeet_tracker.reports import report_summary

init_db("skeet.db")
with get_connection("skeet.db") as conn:
    print(report_summary(conn))
```

## Tests

```bash
pytest
```
