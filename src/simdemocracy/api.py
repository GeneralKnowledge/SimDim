"""Read-only observation plus controlled run commands.

The process that serves this API is the simulation. The browser displays the
record it returns.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from simdemocracy.config import Config
from simdemocracy.engine import Simulation
from simdemocracy.history import export_history

OBSERVER = Path(__file__).resolve().parent / "observer" / "index.html"


class RunRequest(BaseModel):
    seed: int = Field(default=3, ge=1, le=99999)
    ticks: int = Field(default=120, ge=12, le=160)
    population: int = Field(default=300, ge=40, le=400)
    parliament_seats: int = Field(default=61, ge=11, le=121)
    electoral_system: str = "dhondt"
    electoral_threshold: float = Field(default=0.0, ge=0.0, le=0.2)
    party_formation_cost: float = Field(default=0.58, ge=0.0, le=1.5)
    relationship_influence: float = Field(default=1.0, ge=0.0, le=2.0)
    ambition_scale: float = Field(default=1.0, ge=0.0, le=2.0)
    preference_adaptation: float = Field(default=1.0, ge=0.0, le=2.0)


def create_app() -> FastAPI:
    app = FastAPI(title="SimDemocracy")
    cache: dict[str, dict[str, object]] = {}

    @app.get("/")
    def index() -> FileResponse:
        if not OBSERVER.exists():
            raise HTTPException(status_code=404, detail="Observer file is missing")
        return FileResponse(OBSERVER)

    @app.post("/api/run")
    def run(request: RunRequest) -> dict[str, object]:
        if request.electoral_system not in {"dhondt", "sainte_lague"}:
            raise HTTPException(status_code=422, detail="Unknown electoral system")
        key = request.model_dump_json()
        cached = cache.get(key)
        if cached is not None:
            return cached
        try:
            config = Config(
                population=request.population,
                ticks=request.ticks,
                parliament_seats=request.parliament_seats,
                electoral_system=request.electoral_system,
                electoral_threshold=request.electoral_threshold,
                party_formation_cost=request.party_formation_cost,
                relationship_influence=request.relationship_influence,
                ambition_scale=request.ambition_scale,
                preference_adaptation=request.preference_adaptation,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        simulation = Simulation(config, seed=request.seed)
        simulation.run()
        history = export_history(simulation.sim)
        cache[key] = history
        return history

    return app
