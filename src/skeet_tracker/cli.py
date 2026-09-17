"""Typer CLI for the ISSF Skeet analytics engine."""

from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import typer

from skeet_tracker.ballistics import BallisticParams, summarize_engagement
from skeet_tracker.db import DEFAULT_DB_PATH, get_connection, init_db
from skeet_tracker.ingest import (
    IngestError,
    insert_round,
    insert_training_load,
    load_round_json,
)
from skeet_tracker.models import RoundInput, ShotInput, TrainingLoad
from skeet_tracker.reports import (
    report_doubles,
    report_readiness,
    report_station,
    report_summary,
)
from skeet_tracker.sequence import ISSF_SEQUENCE

app = typer.Typer(
    name="skeet",
    help="ISSF International Skeet performance tracking & analytics",
    no_args_is_help=True,
)
report_app = typer.Typer(help="Generate analytics reports")
app.add_typer(report_app, name="report")


def _db_option() -> Path:
    return DEFAULT_DB_PATH


@app.command("init-db")
def cmd_init_db(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db", help="SQLite database path"),
) -> None:
    """Create SQLite tables from the relational schema."""
    path = init_db(db)
    typer.echo(f"Initialized database at {path.resolve()}")


@app.command("add-round")
def cmd_add_round(
    json_file: Optional[Path] = typer.Option(
        None, "--json", help="Path to round JSON file"
    ),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db"),
    event_type: str = typer.Option("practice", "--event-type"),
    round_id: Optional[str] = typer.Option(None, "--round-id"),
    location: Optional[str] = typer.Option(None, "--location"),
    round_number: Optional[int] = typer.Option(None, "--round-number"),
    wind_speed_mph: Optional[int] = typer.Option(None, "--wind"),
    hits_pattern: Optional[str] = typer.Option(
        None,
        "--hits",
        help="25-char pattern of H/M for quick entry (e.g. HHHHH...)",
    ),
) -> None:
    """Ingest a 25-target round from JSON or a hits pattern."""
    init_db(db)
    try:
        if json_file is not None:
            round_input = load_round_json(json_file)
        elif hits_pattern is not None:
            pattern = hits_pattern.strip().upper()
            if len(pattern) != 25 or any(c not in "HM" for c in pattern):
                raise IngestError("--hits must be exactly 25 characters of H or M")
            shots = [
                ShotInput(sequence_order=i, is_hit=(c == "H"))
                for i, c in enumerate(pattern, start=1)
            ]
            round_input = RoundInput(
                round_id=round_id or str(uuid.uuid4()),
                event_type=event_type,  # type: ignore[arg-type]
                shots=shots,
                location=location,
                round_number=round_number,
                wind_speed_mph=wind_speed_mph,
            )
        else:
            typer.echo("Provide --json FILE or --hits PATTERN", err=True)
            raise typer.Exit(code=1)

        with get_connection(db) as conn:
            rid = insert_round(conn, round_input)
        hits = sum(1 for s in round_input.shots if s.is_hit)
        typer.echo(f"Inserted round {rid} ({hits}/25)")
    except IngestError as exc:
        typer.echo(f"Ingest error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("add-load")
def cmd_add_load(
    load_date: str = typer.Option(..., "--date", help="YYYY-MM-DD"),
    workload: float = typer.Option(..., "--workload", help="Shot count / training load"),
    notes: Optional[str] = typer.Option(None, "--notes"),
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db"),
) -> None:
    """Record or update a daily training workload."""
    init_db(db)
    # Validate date format
    date.fromisoformat(load_date)
    with get_connection(db) as conn:
        insert_training_load(
            conn, TrainingLoad(load_date=load_date, workload=workload, notes=notes)
        )
    typer.echo(f"Upserted training load {load_date}: workload={workload}")


@report_app.command("summary")
def cmd_report_summary(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db"),
) -> None:
    """Overall hit rates and diagnostic deltas."""
    init_db(db)
    with get_connection(db) as conn:
        typer.echo(report_summary(conn))


@report_app.command("station")
def cmd_report_station(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db"),
) -> None:
    """Station hit rates and SDI ranking."""
    init_db(db)
    with get_connection(db) as conn:
        typer.echo(report_station(conn))


@report_app.command("doubles")
def cmd_report_doubles(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db"),
) -> None:
    """Markov transition matrix for doubles."""
    init_db(db)
    with get_connection(db) as conn:
        typer.echo(report_doubles(conn))


@report_app.command("readiness")
def cmd_report_readiness(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db"),
) -> None:
    """Banister p(t), ACWR, and Peak Readiness Score."""
    init_db(db)
    with get_connection(db) as conn:
        typer.echo(report_readiness(conn))


@app.command("ballistics")
def cmd_ballistics(
    r: float = typer.Option(..., "--R", help="Slant range to interception (m)"),
    theta: float = typer.Option(
        ..., "--theta", help="Crossing angle in degrees"
    ),
    t: float = typer.Option(..., "--t", help="Target flight time at engagement (s)"),
    v0: float = typer.Option(25.0, "--v0", help="Clay launch speed (m/s)"),
    k_drag: float = typer.Option(0.05, "--k-drag", help="Drag coefficient (1/s)"),
    v_shot: float = typer.Option(350.0, "--v-shot", help="Avg pellet speed (m/s)"),
) -> None:
    """Compute lead distance and angular swing speed for an engagement."""
    params = BallisticParams(v0=v0, k_drag=k_drag, v_shot_avg=v_shot)
    summary = summarize_engagement(t=t, r=r, theta_crossing_deg=theta, params=params)
    typer.echo("=== Ballistics ===")
    typer.echo(f"  v_clay:     {summary['v_clay_mps']:.3f} m/s")
    typer.echo(f"  d_clay:     {summary['d_clay_m']:.3f} m")
    typer.echo(f"  t_flight:   {summary['t_flight_s']:.4f} s")
    typer.echo(f"  lead L:     {summary['lead_m']:.3f} m")
    typer.echo(f"  ω_gun:      {summary['omega_gun_deg_s']:.2f} deg/s")


@app.command("demo-seed")
def cmd_demo_seed(
    db: Path = typer.Option(DEFAULT_DB_PATH, "--db"),
    seed: int = typer.Option(42, "--seed"),
) -> None:
    """Populate a synthetic dataset for smoke-testing reports."""
    init_db(db)
    rng = random.Random(seed)
    base = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)

    # Station-ish miss bias: stations 4 and 8 slightly harder
    hard_stations = {4, 8}

    with get_connection(db) as conn:
        for day_offset in range(30):
            load_day = (date.today() - timedelta(days=29 - day_offset)).isoformat()
            # Taper-ish workload: higher mid-block, lower near end
            wl = 40 + 30 * (1 - abs(day_offset - 15) / 15) + rng.uniform(-5, 5)
            insert_training_load(
                conn,
                TrainingLoad(load_date=load_day, workload=round(wl, 1), notes="demo"),
            )

        for i in range(12):
            event = "practice" if i < 8 else "qualification"
            rn = (i % 5) + 1
            wind = rng.choice([2, 4, 6, 8, 14, 16])
            shots: list[ShotInput] = []
            for slot in ISSF_SEQUENCE:
                base_p = 0.88
                if slot.station in hard_stations:
                    base_p -= 0.08
                if slot.pair_position == 2:
                    base_p -= 0.05
                if event == "qualification":
                    base_p -= 0.04
                if wind > 12:
                    base_p -= 0.03
                hit = rng.random() < base_p
                shots.append(
                    ShotInput(
                        sequence_order=slot.sequence_order,
                        is_hit=hit,
                        miss_direction=None if hit else "behind",
                    )
                )
            rid = f"demo-{i + 1:02d}"
            # Replace if re-seeding
            conn.execute("DELETE FROM rounds WHERE round_id = ?", (rid,))
            insert_round(
                conn,
                RoundInput(
                    round_id=rid,
                    event_type=event,  # type: ignore[arg-type]
                    shots=shots,
                    location="Demo Range",
                    round_number=rn,
                    wind_speed_mph=wind,
                    weather_condition="demo",
                    timestamp=base - timedelta(days=11 - i),
                    notes="demo-seed",
                ),
            )

    typer.echo(f"Seeded demo data into {db.resolve()} (12 rounds, 30 load days)")


# Expose for setuptools entry point: skeet = skeet_tracker.cli:app
# Typer apps are callable via typer.run when needed; entry point uses the app object.
