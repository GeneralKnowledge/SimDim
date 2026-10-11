"""Command line for headless runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from simdemocracy.config import Config
from simdemocracy.engine import Simulation
from simdemocracy.events import Event
from simdemocracy.explain import chronicle, explain
from simdemocracy.history import export_history, write_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simdemocracy")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run one Commonwealth and write its history")
    _add_config_args(run)
    run.add_argument("--out", default="runs/latest")

    batch = sub.add_parser("batch", help="Run several seeds and summarise metrics")
    _add_config_args(batch)
    batch.add_argument("--seeds", type=int, default=8)
    batch.add_argument("--out", default="runs/batch")

    shown = sub.add_parser("explain", help="Print the causal chain for one event")
    shown.add_argument("history")
    shown.add_argument("--event", type=int, required=True)

    serve = sub.add_parser("serve", help="Serve the observer")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "batch":
        return _batch(args)
    if args.command == "explain":
        return _explain(args)
    if args.command == "serve":
        return _serve(args)
    return 2


def _add_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument("--population", type=int, default=300)
    parser.add_argument("--seats", type=int, default=61)
    parser.add_argument("--system", choices=["dhondt", "sainte_lague"], default="dhondt")
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--formation-cost", type=float, default=None)
    parser.add_argument("--relationship-influence", type=float, default=None)
    parser.add_argument("--ambition-scale", type=float, default=None)
    parser.add_argument("--preference-adaptation", type=float, default=None)
    parser.add_argument("--election-interval", type=int, default=12)


def config_from_args(args: argparse.Namespace) -> Config:
    config = Config(
        population=args.population,
        ticks=args.ticks,
        parliament_seats=args.seats,
        electoral_system=args.system,
        electoral_threshold=args.threshold,
        election_interval=args.election_interval,
    )
    if args.formation_cost is not None:
        config.party_formation_cost = args.formation_cost
    if args.relationship_influence is not None:
        config.relationship_influence = args.relationship_influence
    if args.ambition_scale is not None:
        config.ambition_scale = args.ambition_scale
    if args.preference_adaptation is not None:
        config.preference_adaptation = args.preference_adaptation
    return config


def _run(args: argparse.Namespace) -> int:
    config = config_from_args(args)
    simulation = Simulation(config, seed=args.seed)
    simulation.run()
    history = write_run(simulation.sim, args.out)
    _print_summary(history)
    print(f"Wrote {args.out}/history.json")
    return 0


def _batch(args: argparse.Namespace) -> int:
    path = Path(args.out)
    path.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in range(1, args.seeds + 1):
        config = config_from_args(args)
        simulation = Simulation(config, seed=seed)
        simulation.run()
        history = export_history(simulation.sim)
        metrics = history["metrics"]
        assert isinstance(metrics, dict)
        diversity = metrics["party_diversity"]
        coalition = metrics["coalition_diversity"]
        assert isinstance(diversity, dict)
        assert isinstance(coalition, dict)
        rows.append(
            {
                "seed": seed,
                "active_parties": diversity["active_at_end"],
                "founded": diversity["founded"],
                "dissolved": diversity["dissolved"],
                "splits": diversity["split"],
                "mergers": diversity["merged"],
                "governments": coalition["governments"],
                "distant_alliances": coalition["distant_alliances"],
                "broken_commitments": metrics["alliance_stability"]["broken_commitments"],  # type: ignore[index]
                "defections": metrics["political_mobility"]["defections"],  # type: ignore[index]
                "effective_parties": diversity["effective_number_last_election"],
                "preference_shift": metrics["preference_change"]["mean_absolute_shift"],  # type: ignore[index]
            }
        )
        print(
            f"seed {seed}: parties {diversity['active_at_end']} "
            f"founded {diversity['founded']} governments {coalition['governments']}"
        )
    (path / "comparison.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {path / 'comparison.json'}")
    return 0


def _explain(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.history).read_text(encoding="utf-8"))
    events = [_event(item) for item in payload["events"]]
    print(json.dumps(explain(events, args.event), indent=2))
    return 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from simdemocracy.api import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


def _print_summary(history: dict[str, object]) -> None:
    metrics = history["metrics"]
    assert isinstance(metrics, dict)
    diversity = metrics["party_diversity"]
    coalition = metrics["coalition_diversity"]
    alliance = metrics["alliance_stability"]
    assert isinstance(diversity, dict)
    assert isinstance(coalition, dict)
    assert isinstance(alliance, dict)
    print(
        f"seed {history['seed']}: {history['ticks_run']} weeks, "
        f"{diversity['active_at_end']} parties still active, "
        f"{diversity['founded']} organisations founded, "
        f"{coalition['governments']} governments, "
        f"{alliance['broken_commitments']} broken commitments."
    )


def _event(data: dict[str, object]) -> Event:
    return Event(
        id=int(data["id"]),
        tick=int(data["tick"]),
        type=str(data["type"]),
        significance=str(data["significance"]),
        summary=str(data["summary"]),
        actors=dict(data.get("actors") or {}),  # type: ignore[arg-type]
        factors=dict(data.get("factors") or {}),  # type: ignore[arg-type]
        details=dict(data.get("details") or {}),  # type: ignore[arg-type]
        causes=list(data.get("causes") or []),  # type: ignore[arg-type]
    )


if __name__ == "__main__":
    sys.exit(main())
