"""Explicitly synthetic state scenarios, kept outside real market reports/state."""
import json
from pathlib import Path
from src import signals, state


def run():
    results = []
    previous = None
    cases = [("2026-10-20", -.08, "FIRST_BASELINE"), ("2026-10-21", -.12, "NEW_THRESHOLD"),
             ("2026-10-22", -.24, "NEW_THRESHOLD"), ("2026-10-23", -.33, "NEW_THRESHOLD"),
             ("2026-10-26", -.18, "RECOVERY"), ("2026-10-27", -.24, "REENTRY")]
    for date, drawdown, expected in cases:
        current = {"trading_date": date, "drawdown": drawdown}
        event = signals.transition(previous, current)
        assert event["change_event"] == expected
        results.append({"synthetic": True, **current, **event})
        previous = {**current, **event}
    revisions = state.revisions({"history_prices": {"2026-10-19": 100}}, {"2026-10-19": 150})
    current = {"trading_date": "2026-10-28", "drawdown": 76/150-1}
    event = signals.transition(previous, current, revision=bool(revisions))
    assert event["change_event"] == "HISTORICAL_REVISION" and event["new_thresholds"] == []
    results.append({"synthetic": True, **current, **event, "revisions": revisions})
    before = json.dumps(previous, sort_keys=True)
    results.append({"synthetic": True, "change_event": "DATA_ERROR", "reason": "Injected missing Adj Close", "previous_state_preserved": before == json.dumps(previous, sort_keys=True)})
    output = Path(__file__).resolve().parents[1]/"simulations/phase3_state_changes.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"synthetic": True, "description": "Fixed test inputs, not market prices or formal monitor state", "results": results}, indent=2)+"\n")
    print(output)


if __name__ == "__main__":
    run()
