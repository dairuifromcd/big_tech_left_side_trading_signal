"""Mutually exclusive observation tiers and deterministic transition events."""
import math

THRESHOLDS = (10, 20, 30)
SIGNIFICANT_DEEPENING_PP = 1.0


def crossed(drawdown):
    # Tolerance only protects floating arithmetic on exact threshold boundaries.
    return [n for n in THRESHOLDS if drawdown * 100 <= -n + 1e-10]


def tier(drawdown):
    levels = crossed(drawdown)
    return f"WATCH_{max(levels)}" if levels else "NONE"


def transition(previous, current, revision=False, significant_pp=SIGNIFICANT_DEEPENING_PP):
    """Legacy scalar transition; full monitoring uses observations.evaluate.

    `revision=True` can only summarize a revision-only legacy caller. It lacks
    price/identity context and must never be used to combine market and revision
    facts. The v2 observer calls this with revision=False after attribution.
    """
    if not math.isfinite(significant_pp) or significant_pp <= 0:
        raise ValueError("significant_pp must be positive percentage points")
    now = crossed(current["drawdown"])
    old = crossed(previous["drawdown"]) if previous else []
    entering = sorted(set(now) - set(old))
    touched = set(previous["triggered_thresholds"]) if previous else set()
    if previous is None:
        event = "FIRST_BASELINE"
        entering = []
    elif revision:
        event = "HISTORICAL_REVISION"
        entering = []
    elif current["trading_date"] == previous["trading_date"]:
        event = "NO_CHANGE"
        entering = []
    elif entering:
        event = "NEW_THRESHOLD" if set(entering) - touched else "REENTRY"
    elif len(now) < len(old):
        event = "RECOVERY"
    elif now and (previous.get("deepening_anchor", previous["drawdown"]) - current["drawdown"]) * 100 >= significant_pp - 1e-10:
        event = "DEEPER_DRAWDOWN"
    else:
        event = "NO_CHANGE"
    new = sorted(set(entering) - touched)
    reentered = sorted(set(entering) & touched)
    return {
        "change_event": event, "watch_tier": tier(current["drawdown"]),
        "previous_watch_tier": previous["watch_tier"] if previous else None,
        "crossed_thresholds_this_run": entering, "new_thresholds": new,
        "reentered_thresholds": reentered,
        "triggered_thresholds": sorted(touched | set(now)),
        "last_new_trigger_date": current["trading_date"] if new else (previous.get("last_new_trigger_date") if previous else None),
        "deepening_anchor": current["drawdown"] if event != "NO_CHANGE" else previous.get("deepening_anchor", previous["drawdown"]),
    }
