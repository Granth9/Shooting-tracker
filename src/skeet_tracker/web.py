"""FastAPI web UI for Skeet Tracker."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from skeet_tracker.api_data import (
    build_drill_payload,
    competitions_payload,
    compose_drill_payload,
    dashboard_payload,
    doubles_payload,
    drills_payload,
    readiness_payload,
    sequence_payload,
    stations_payload,
)
from skeet_tracker.ballistics import BallisticParams, summarize_engagement
from skeet_tracker.competitions import delete_meet, save_meet
from skeet_tracker.db import DEFAULT_DB_PATH, get_connection, init_db
from skeet_tracker.drills import delete_template, get_template, save_template
from skeet_tracker.ingest import IngestError, insert_round, insert_training_load
from skeet_tracker.models import RoundInput, ShotInput, TrainingLoad

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ShotBody(BaseModel):
    sequence_order: int = Field(ge=1, le=100)
    is_hit: bool
    miss_direction: Optional[
        Literal["behind", "above", "below", "ahead", "unknown"]
    ] = None
    station: Optional[int] = Field(default=None, ge=1, le=8)
    target_house: Optional[Literal["high", "low"]] = None
    is_double: Optional[bool] = None
    pair_position: Optional[int] = Field(default=None, ge=0, le=2)


class RoundBody(BaseModel):
    event_type: Literal["practice", "qualification", "final", "drill"] = "practice"
    format: Literal["issf_25", "issf_final_36", "drill"] = "issf_25"
    drill_name: Optional[str] = None
    round_id: Optional[str] = None
    location: Optional[str] = None
    round_number: Optional[int] = Field(default=None, ge=1, le=5)
    wind_speed_mph: Optional[int] = Field(default=None, ge=0)
    weather_condition: Optional[str] = None
    choke_used: Optional[str] = None
    notes: Optional[str] = None
    shots: list[ShotBody]


class DrillBlockBody(BaseModel):
    station: int = Field(ge=1, le=8)
    kind: Literal["high_single", "low_single", "high_pair", "low_pair"]
    reps: int = Field(ge=1, le=40)


class ComposeDrillBody(BaseModel):
    name: Optional[str] = None
    blocks: list[DrillBlockBody]


class SaveTemplateBody(BaseModel):
    name: str
    description: Optional[str] = None
    blocks: list[DrillBlockBody]
    template_id: Optional[str] = None


class MeetBody(BaseModel):
    meet_id: Optional[str] = None
    name: str
    year: int = Field(ge=1990, le=2100)
    event_date: Optional[str] = None
    date_precision: Literal["day", "year"] = "year"
    category: Optional[str] = None
    level: Literal["domestic", "international"] = "domestic"
    qualification_score: Optional[int] = None
    final_score: Optional[int] = None
    selection_aggregate: Optional[int] = None
    rounds: Optional[list[int]] = None
    rounds_text: Optional[str] = None
    placing: Optional[int] = None
    medal: Optional[Literal["gold", "silver", "bronze"]] = None
    source_url: Optional[str] = None
    source_label: Optional[str] = None
    notes: Optional[str] = None


class LoadBody(BaseModel):
    load_date: str
    workload: float = Field(ge=0)
    notes: Optional[str] = None


class BallisticsBody(BaseModel):
    r: float = Field(gt=0, description="Slant range meters")
    theta: float = Field(description="Crossing angle degrees")
    t: float = Field(ge=0, description="Engagement time seconds")
    v0: float = 25.0
    k_drag: float = 0.05
    v_shot: float = 350.0


def _db_path() -> Path:
    return Path(os.environ.get("SKEET_DB", str(DEFAULT_DB_PATH)))


def create_app(db_path: Path | None = None) -> FastAPI:
    path = db_path or _db_path()
    init_db(path)

    app = FastAPI(title="Skeet Tracker", version="0.2.0")
    app.state.db_path = path

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/sequence")
    def api_sequence(
        format: str = Query("issf_25", pattern="^(issf_25|issf_final_36)$"),
    ) -> dict[str, Any]:
        try:
            return sequence_payload(format)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/drills")
    def api_drills() -> dict[str, Any]:
        with get_connection(app.state.db_path) as conn:
            return drills_payload(conn)

    @app.get("/api/drills/build")
    def api_drills_build(
        station: int = Query(ge=1, le=8),
        targets: int = Query(10, ge=1, le=100),
        pattern: str = Query("double_hl"),
    ) -> dict[str, Any]:
        try:
            return build_drill_payload(station, targets, pattern)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/drills/compose")
    def api_drills_compose(payload: ComposeDrillBody) -> dict[str, Any]:
        try:
            return compose_drill_payload(
                [b.model_dump() for b in payload.blocks],
                name=payload.name,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/drill-templates")
    def api_list_templates() -> dict[str, Any]:
        with get_connection(app.state.db_path) as conn:
            return {"templates": drills_payload(conn)["templates"]}

    @app.get("/api/drill-templates/{template_id}")
    def api_get_template(template_id: str) -> dict[str, Any]:
        try:
            with get_connection(app.state.db_path) as conn:
                return get_template(conn, template_id)
        except KeyError as exc:
            raise HTTPException(404, "Template not found") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/drill-templates")
    def api_save_template(payload: SaveTemplateBody) -> dict[str, Any]:
        try:
            with get_connection(app.state.db_path) as conn:
                return save_template(
                    conn,
                    name=payload.name,
                    blocks=[b.model_dump() for b in payload.blocks],
                    description=payload.description,
                    template_id=payload.template_id,
                )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete("/api/drill-templates/{template_id}")
    def api_delete_template(template_id: str) -> dict[str, Any]:
        try:
            with get_connection(app.state.db_path) as conn:
                delete_template(conn, template_id)
        except KeyError as exc:
            raise HTTPException(404, "Template not found") from exc
        return {"ok": True, "template_id": template_id}

    @app.get("/api/dashboard")
    def api_dashboard() -> dict[str, Any]:
        with get_connection(app.state.db_path) as conn:
            return dashboard_payload(conn)

    @app.get("/api/competitions")
    def api_competitions() -> dict[str, Any]:
        with get_connection(app.state.db_path) as conn:
            return competitions_payload(conn)

    @app.post("/api/competitions")
    def api_save_competition(payload: MeetBody) -> dict[str, Any]:
        try:
            with get_connection(app.state.db_path) as conn:
                return save_meet(conn, payload.model_dump())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete("/api/competitions/{meet_id}")
    def api_delete_competition(meet_id: str) -> dict[str, Any]:
        try:
            with get_connection(app.state.db_path) as conn:
                delete_meet(conn, meet_id)
        except KeyError as exc:
            raise HTTPException(404, "Meet not found") from exc
        return {"ok": True, "meet_id": meet_id}

    @app.get("/api/stations")
    def api_stations() -> dict[str, Any]:
        with get_connection(app.state.db_path) as conn:
            return stations_payload(conn)

    @app.get("/api/doubles")
    def api_doubles() -> dict[str, Any]:
        with get_connection(app.state.db_path) as conn:
            return doubles_payload(conn)

    @app.get("/api/readiness")
    def api_readiness() -> dict[str, Any]:
        with get_connection(app.state.db_path) as conn:
            return readiness_payload(conn)

    @app.post("/api/rounds")
    def api_add_round(payload: RoundBody) -> dict[str, Any]:
        round_input = RoundInput(
            round_id=payload.round_id or str(uuid.uuid4()),
            event_type=payload.event_type,
            format=payload.format,
            drill_name=payload.drill_name,
            location=payload.location,
            round_number=payload.round_number,
            wind_speed_mph=payload.wind_speed_mph,
            weather_condition=payload.weather_condition,
            choke_used=payload.choke_used,
            notes=payload.notes,
            shots=[
                ShotInput(
                    sequence_order=s.sequence_order,
                    is_hit=s.is_hit,
                    miss_direction=s.miss_direction,
                    station=s.station,
                    target_house=s.target_house,
                    is_double=s.is_double,
                    pair_position=s.pair_position,
                )
                for s in payload.shots
            ],
        )
        try:
            with get_connection(app.state.db_path) as conn:
                rid = insert_round(conn, round_input)
        except IngestError as exc:
            raise HTTPException(400, str(exc)) from exc
        hits = sum(1 for s in payload.shots if s.is_hit)
        return {
            "round_id": rid,
            "hits": hits,
            "shots": len(payload.shots),
            "format": round_input.format,
            "event_type": round_input.event_type,
        }

    @app.post("/api/loads")
    def api_add_load(payload: LoadBody) -> dict[str, Any]:
        try:
            with get_connection(app.state.db_path) as conn:
                insert_training_load(
                    conn,
                    TrainingLoad(
                        load_date=payload.load_date,
                        workload=payload.workload,
                        notes=payload.notes,
                    ),
                )
        except IngestError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True, "load_date": payload.load_date}

    @app.post("/api/ballistics")
    def api_ballistics(payload: BallisticsBody) -> dict[str, float]:
        params = BallisticParams(
            v0=payload.v0, k_drag=payload.k_drag, v_shot_avg=payload.v_shot
        )
        return summarize_engagement(
            t=payload.t,
            r=payload.r,
            theta_crossing_deg=payload.theta,
            params=params,
        )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


app = create_app()
