"""Walk causal links that were stored when events were recorded."""

from __future__ import annotations

from simdemocracy.events import Event


def explain(events: list[Event], event_id: int, depth: int = 6) -> dict[str, object]:
    by_id = {event.id: event for event in events}
    if event_id not in by_id:
        raise KeyError(f"No event {event_id}")
    children: dict[int, list[int]] = {}
    for event in events:
        for cause in event.causes:
            children.setdefault(cause, []).append(event.id)

    def chain(current: int, remaining: int, seen: set[int]) -> dict[str, object]:
        event = by_id[current]
        node = _brief(event)
        if remaining <= 0 or current in seen:
            return node
        seen.add(current)
        node["because"] = [
            chain(cause, remaining - 1, set(seen))
            for cause in event.causes
            if cause in by_id
        ]
        return node

    focus = by_id[event_id]
    return {
        "event": focus.to_dict(),
        "because": [chain(cause, depth - 1, {event_id}) for cause in focus.causes if cause in by_id],
        "led_to": [_brief(by_id[child]) for child in children.get(event_id, []) if child in by_id],
    }


def chronicle(events: list[Event]) -> str:
    lines = ["# Commonwealth chronicle", ""]
    for event in events:
        if event.significance != "major":
            continue
        lines.append(f"## Week {event.tick} — {event.type.replace('_', ' ').capitalize()}")
        lines.append("")
        lines.append(event.summary)
        lines.append("")
        rendered = ", ".join(
            f"{key}={value}"
            for key, value in event.factors.items()
            if not isinstance(value, (dict, list))
        )
        if rendered:
            lines.append(f"Recorded drivers: {rendered}.")
            lines.append("")
        if event.causes:
            lines.append("Causes: " + ", ".join(f"event {cause}" for cause in event.causes) + ".")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _brief(event: Event) -> dict[str, object]:
    return {
        "id": event.id,
        "tick": event.tick,
        "type": event.type,
        "summary": event.summary,
        "factors": event.factors,
    }
