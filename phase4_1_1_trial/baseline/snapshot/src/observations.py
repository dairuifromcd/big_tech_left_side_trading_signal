"""Separate history-revision facts from confirmable market observations.

No formulas or revision tolerances are changed. Counterfactual old/new price
mixing is only diagnostic until the recorded comparability conditions pass.
"""

import copy
import datetime as dt
import math

import market_calendar as calendar
import test_yahoo_nine as phase2
from src import indicators, signals, state


PRECISION_CANDIDATE_MAX_RELATIVE = 1e-5
# Unit comparability is dimensionless and must remain strict for tiny factors.
# These proof constants do not replace or change the price revision detector.
FACTOR_REL_TOL = 1e-10
FACTOR_ABS_TOL = 0.0


def _same_identity(symbol, current, previous):
    if not isinstance(current, dict) or not isinstance(previous, dict):
        return False
    for value in (current, previous):
        checks = phase2.new_row(symbol, 1)
        phase2.validate_identity(checks, value)
        if not checks["identity_validated"]:
            return False
    fields = ("symbol", "instrumentType", "currency", "exchangeName", "fullExchangeName", "exchangeTimezoneName")
    return all(current.get(key) == previous.get(key) for key in fields)


def _finite_positive(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def _impact(old, new):
    keys = ("adjclose", "highest_adjclose", "highest_date", "drawdown", "rsi14", "sma50", "sma200")
    changed = {key: old[key] != new[key] for key in keys}
    changed["watch_tier"] = signals.tier(old["drawdown"]) != signals.tier(new["drawdown"])
    deltas = {key: new[key] - old[key] if old[key] is not None and new[key] is not None else None
              for key in ("adjclose", "highest_adjclose", "drawdown", "rsi14", "sma50", "sma200")}
    return {"changed": changed, "deltas": deltas}


def _metric_view(metrics):
    return {key: metrics[key] for key in ("trading_date", "adjclose", "window_samples", "highest_adjclose", "highest_date", "drawdown", "rsi14", "sma50", "sma200")}


def evaluate(symbol, pairs, closes, identity, previous_state, significant_pp=1.0):
    """Pure evaluation; caller validates the source and commits state/ledger.

    Previous state should contain history_prices, history_closes and
    identity_snapshot. Missing provenance never establishes comparability.
    Pending IDs are preserved here and finalized by the transaction's ledger.
    """
    previous = copy.deepcopy(previous_state)
    target = pairs[-1][0]
    current_prices = dict(pairs)
    metrics = indicators.calculate(pairs, target, allow_short=symbol == "SPCX")
    now_levels = signals.crossed(metrics["drawdown"])
    old_thresholds = (previous or {}).get("threshold_state", {})
    confirmed = sorted(set(old_thresholds.get("confirmed", (previous or {}).get("confirmed_thresholds", []))))
    baseline = sorted(set(old_thresholds.get("baseline", (previous or {}).get("baseline_observed_thresholds", []))))
    if previous and not old_thresholds and not baseline:
        # Legacy observed levels are a baseline, never proof of confirmation.
        baseline = signals.crossed(previous["drawdown"])
    pending_ids = list(old_thresholds.get("pending_event_ids", []))
    threshold_state = {"observed": now_levels, "confirmed": confirmed,
                       "baseline": baseline, "pending_event_ids": pending_ids}
    reasons = []
    raw = state.revisions(previous, current_prices) if previous else []
    max_abs = max((abs(item["current"] - item["previous"]) for item in raw), default=0.0)
    max_rel = max((abs(item["current"] / item["previous"] - 1) for item in raw), default=0.0)
    revision = {
        "detected": bool(raw), "classification": "NO_REVISION" if not raw else "REVISION_REVIEW_REQUIRED",
        "count": len(raw), "raw_differences": raw,
        "dates": [item["date"] for item in raw], "max_absolute_difference": max_abs,
        "max_relative_difference": max_rel, "requires_review": False,
        "confidence": "Observed overlapping-date differences; Yahoo upstream cause unconfirmed",
    }
    market = {
        "previous_trading_date": previous["trading_date"] if previous else None,
        "current_trading_date": target,
        "previous_adjclose": previous["adjclose"] if previous else None,
        "current_adjclose": metrics["adjclose"],
        "previous_drawdown": previous["drawdown"] if previous else None,
        "current_drawdown": metrics["drawdown"],
        "previous_watch_tier": previous["watch_tier"] if previous else None,
        "current_watch_tier": signals.tier(metrics["drawdown"]),
        "candidate_thresholds": [], "crossed_thresholds": [],
        "confirmed_thresholds_this_run": [], "pending_thresholds_this_run": [],
        "comparability_proven": False, "comparability_reasons": reasons,
        "event_type": "FIRST_BASELINE" if previous is None else "NO_CHANGE",
        "status": "NO_EVENT", "can_confirm": False,
        "old_basis_counterfactual": None, "previous_recomputed_metrics": None,
    }
    if previous is None:
        threshold_state["baseline"] = now_levels
        return {
            **metrics, "revision_observation": revision, "market_observation": market,
            "threshold_state": threshold_state, "market_events": [],
            "change_event": "FIRST_BASELINE", "watch_tier": signals.tier(metrics["drawdown"]),
            "previous_watch_tier": None, "crossed_thresholds_this_run": [], "new_thresholds": [],
            "reentered_thresholds": [], "triggered_thresholds": confirmed,
            "confirmed_thresholds": confirmed, "baseline_observed_thresholds": now_levels,
            "last_new_trigger_date": None, "deepening_anchor": metrics["drawdown"],
            "raw_revision_differences": raw,
        }

    old_prices = previous["history_prices"]
    old_close = previous.get("history_closes")
    overlap = sorted(old_prices.keys() & current_prices.keys())
    previous_date = previous["trading_date"]
    is_new_session = target > previous_date
    same_session = target == previous_date
    if target < previous_date:
        raise ValueError("STALE_DATA: cannot evaluate older observation")
    if (previous.get("revision_review_event_ids") or (
            "revision_review_event_ids" not in previous
            and previous.get("revision_observation", {}).get("requires_review"))):
        reasons.append("UNRESOLVED_PRIOR_REVISION_REVIEW")
    if not _same_identity(symbol, identity, previous.get("identity_snapshot")):
        reasons.append("IDENTITY_PROVENANCE_MISSING_OR_CHANGED")
    if symbol == "SPCX":
        reasons.append("SPCX_HISTORICAL_ANOMALY_UNVERIFIED")
    if is_new_session:
        days = calendar.sessions_between(dt.date.fromisoformat(previous_date), dt.date.fromisoformat(target))
        if len(days) != 2 or days[0].isoformat() != previous_date or days[1].isoformat() != target:
            reasons.append("NON_CONSECUTIVE_SESSIONS")
    if not isinstance(old_close, dict) or any(not _finite_positive(old_close.get(date)) or not _finite_positive(closes.get(date)) for date in overlap):
        reasons.append("OVERLAP_CLOSE_EVIDENCE_MISSING")
    elif any(old_close[date] != closes[date] for date in overlap):
        reasons.append("OVERLAP_CLOSE_CHANGED")
    if previous_date not in current_prices or current_prices.get(previous_date) != previous["adjclose"]:
        reasons.append("PREVIOUS_LATEST_ADJCLOSE_CHANGED_OR_MISSING")
    anchor_factor = None
    current_factor = None
    if isinstance(old_close, dict) and _finite_positive(old_close.get(previous_date)) and _finite_positive(closes.get(previous_date)) and _finite_positive(closes.get(target)):
        anchor_factor = previous["adjclose"] / old_close[previous_date]
        new_anchor_factor = current_prices.get(previous_date, previous["adjclose"]) / closes[previous_date]
        current_factor = metrics["adjclose"] / closes[target]
        if not math.isclose(anchor_factor, new_anchor_factor, rel_tol=FACTOR_REL_TOL, abs_tol=FACTOR_ABS_TOL):
            reasons.append("PREVIOUS_ADJUSTMENT_FACTOR_CHANGED")
        if not math.isclose(anchor_factor, current_factor, rel_tol=FACTOR_REL_TOL, abs_tol=FACTOR_ABS_TOL):
            reasons.append("CURRENT_ADJUSTMENT_FACTOR_INCOMPARABLE")
    else:
        reasons.append("ADJUSTMENT_FACTOR_ANCHOR_MISSING")
    market["adjustment_factor_evidence"] = {"previous_anchor_factor": anchor_factor,
                                             "current_factor": current_factor}

    # Calculate at the same target window. This correctly drops naturally expired
    # old highs and is distinct from comparison with the previous day's high.
    hybrid = [(date, old_prices.get(date, price)) for date, price in pairs]
    counterfactual = indicators.calculate(hybrid, target, allow_short=symbol == "SPCX")
    # Retain prior warmup rows that merely rolled out of the provider's fetch
    # range. Their disappearance is not a price revision and must not turn a
    # complete previous252-session window into251 samples.
    previous_recomputed_map = dict(old_prices)
    previous_recomputed_map.update({date: price for date, price in pairs if date <= previous_date})
    previous_recomputed_pairs = sorted(previous_recomputed_map.items())
    previous_recomputed = indicators.calculate(previous_recomputed_pairs, previous_date, allow_short=symbol == "SPCX")
    impacts = _impact(counterfactual, metrics)
    revision["impact_at_current_target"] = impacts
    revision["impact_on_previous_session"] = _impact(previous, previous_recomputed)
    market["old_basis_counterfactual"] = _metric_view(counterfactual)
    market["old_basis_counterfactual"]["conditional_only_until_comparability_proven"] = True
    market["previous_recomputed_metrics"] = _metric_view(previous_recomputed)
    market["window_high_expired_naturally"] = (previous["highest_date"] not in {date for date, _ in hybrid[-252:]})

    touched = sorted(set(baseline) | set(confirmed))
    transition_previous = dict(previous, triggered_thresholds=touched)
    proposed = signals.transition(transition_previous, metrics, revision=False, significant_pp=significant_pp)
    control = signals.transition(transition_previous, counterfactual, revision=False, significant_pp=significant_pp)
    market["unrevised_basis_event"] = control["change_event"]
    market["revised_basis_event"] = proposed["change_event"]
    candidate_levels = list(proposed["crossed_thresholds_this_run"])
    if raw:
        if max_rel > PRECISION_CANDIDATE_MAX_RELATIVE:
            reasons.append("RELATIVE_REVISION_NOT_PRECISION_CANDIDATE")
        if counterfactual["highest_adjclose"] != metrics["highest_adjclose"] or counterfactual["highest_date"] != metrics["highest_date"]:
            reasons.append("ROLLING_EXTREMUM_REVISED")
        if previous_recomputed["highest_adjclose"] != previous["highest_adjclose"] or previous_recomputed["highest_date"] != previous["highest_date"]:
            reasons.append("PREVIOUS_EXTREMUM_REVISED")
        if signals.tier(previous_recomputed["drawdown"]) != signals.tier(previous["drawdown"]):
            reasons.append("PREVIOUS_TIER_REVISED")
        if proposed["change_event"] != control["change_event"] or candidate_levels != control["crossed_thresholds_this_run"] or signals.tier(metrics["drawdown"]) != signals.tier(counterfactual["drawdown"]):
            reasons.append("COUNTERFACTUAL_EVENT_OR_TIER_DISAGREEMENT")
        # A tiny changed high or a near-boundary low difference is not excused
        # by its dollar amount. This relative bound is combined with extrema,
        # unit anchors, and crossing agreement, never a replacement tolerance.
        drawdown_bound = max(abs(metrics["drawdown"] - counterfactual["drawdown"]), max_rel * 2)
        tested_levels = candidate_levels or list(signals.THRESHOLDS)
        margin = min(abs(metrics["drawdown"] + level / 100) for level in tested_levels)
        market["revision_drawdown_error_bound"] = drawdown_bound
        market["nearest_tested_threshold_margin"] = margin
        if margin <= drawdown_bound:
            reasons.append("THRESHOLD_MARGIN_NOT_GREATER_THAN_REVISION_BOUND")
        if proposed["change_event"] == "DEEPER_DRAWDOWN":
            depth = (previous.get("deepening_anchor", previous["drawdown"]) - metrics["drawdown"]) * 100
            if abs(depth - significant_pp) <= drawdown_bound * 100:
                reasons.append("DEEPENING_MARGIN_NOT_GREATER_THAN_REVISION_BOUND")
        revision["classification"] = "NUMERIC_PRECISION_CANDIDATE" if not reasons else (
            "MATERIAL_REVISION" if max_rel > PRECISION_CANDIDATE_MAX_RELATIVE or impacts["changed"]["watch_tier"] else "REVISION_REVIEW_REQUIRED")
        revision["requires_review"] = bool(reasons)
    market["comparability_proven"] = not reasons
    market["can_confirm"] = is_new_session and not reasons
    market["candidate_thresholds"] = candidate_levels
    market["crossed_thresholds"] = candidate_levels
    market["significant_deepening"] = proposed["change_event"] == "DEEPER_DRAWDOWN"
    market["recovery"] = proposed["change_event"] == "RECOVERY"
    market["reentry"] = proposed["change_event"] == "REENTRY"
    market["event_type"] = proposed["change_event"]
    candidates = []
    if is_new_session and proposed["change_event"] != "NO_CHANGE":
        status = "CONFIRMED" if market["can_confirm"] else "PENDING_REVIEW"
        market["status"] = status
        if candidate_levels:
            for level in candidate_levels:
                candidates.append({"symbol": symbol, "trading_date": target,
                                   "event_type": "THRESHOLD_CROSSING",
                                   "event_subtype": "REENTRY" if level in touched else "NEW_THRESHOLD",
                                   "threshold": level, "status": status,
                                   "rules_version": indicators.RULES_VERSION})
        else:
            candidates.append({"symbol": symbol, "trading_date": target,
                               "event_type": proposed["change_event"],
                               "event_subtype": proposed["change_event"],
                               "threshold": None, "status": status,
                               "rules_version": indicators.RULES_VERSION})
    elif same_session:
        market["event_type"] = "NO_CHANGE"
    evidence = {"previous_trading_date": previous_date, "previous_adjclose": previous["adjclose"],
                "previous_drawdown": previous["drawdown"], "current_adjclose": metrics["adjclose"],
                "current_drawdown": metrics["drawdown"],
                "old_basis_counterfactual": market["old_basis_counterfactual"],
                "comparability_proven": market["comparability_proven"],
                "comparability_reasons": list(reasons),
                "revision_count": len(raw), "revision_dates": revision["dates"]}
    for candidate in candidates:
        candidate["evidence"] = copy.deepcopy(evidence)
    confirmed_now = candidate_levels if candidates and market["status"] == "CONFIRMED" else []
    pending_now = candidate_levels if candidates and market["status"] == "PENDING_REVIEW" else []
    confirmed = sorted(set(confirmed) | set(confirmed_now))
    threshold_state["confirmed"] = confirmed
    market["confirmed_thresholds_this_run"] = confirmed_now
    market["pending_thresholds_this_run"] = pending_now
    if candidates:
        summary = proposed["change_event"] if market["status"] == "CONFIRMED" else "PENDING_REVIEW"
    else:
        summary = "HISTORICAL_REVISION" if raw else "NO_CHANGE"
    # Rebase a pure revised anchor without asserting a new market event. An
    # unconfirmed market candidate must not consume significant-deepening scope.
    anchor = previous.get("deepening_anchor", previous["drawdown"])
    if summary not in ("NO_CHANGE", "PENDING_REVIEW"):
        # Preserve accumulated within-tier movement when only historical values
        # changed. Rebase by the revision's effect, do not reset to the last day.
        anchor = (metrics["drawdown"] if candidates else
                  anchor + previous_recomputed["drawdown"] - previous["drawdown"])
    return {
        **metrics, "revision_observation": revision, "market_observation": market,
        "threshold_state": threshold_state, "market_events": candidates,
        "change_event": summary, "watch_tier": signals.tier(metrics["drawdown"]),
        "previous_watch_tier": previous["watch_tier"],
        "crossed_thresholds_this_run": confirmed_now,
        "new_thresholds": sorted(set(confirmed_now) - set(touched)),
        "reentered_thresholds": sorted(set(confirmed_now) & set(touched)),
        "triggered_thresholds": confirmed, "confirmed_thresholds": confirmed,
        "baseline_observed_thresholds": baseline,
        "last_new_trigger_date": target if set(confirmed_now) - set(touched) else previous.get("last_new_trigger_date"),
        "deepening_anchor": anchor, "raw_revision_differences": raw,
    }
