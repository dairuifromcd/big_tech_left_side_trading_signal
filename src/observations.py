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


def missing_sessions(previous_date, target):
    """Completed exchange sessions that must be processed before target."""
    if target <= previous_date:
        return []
    dates=calendar.sessions_between(dt.date.fromisoformat(previous_date),dt.date.fromisoformat(target))
    return [day.isoformat() for day in dates[1:-1]]


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


def depth_semantics(previous, current, candidate_type, status, latest_previous=None):
    """Display facts, not a new event identity or an automatic review decision."""
    daily_previous = latest_previous if latest_previous is not None else previous
    return {"daily_drawdown_change_pp": (current["drawdown"]-daily_previous["drawdown"])*100 if daily_previous else None,
            "daily_new_deepening": bool(daily_previous and current["drawdown"] < daily_previous["drawdown"]),
            "stored_previous_drawdown_change_pp": (current["drawdown"]-previous["drawdown"])*100 if previous else None,
            "cumulative_anchor_deepening_pp": (previous.get("deepening_anchor", previous["drawdown"])-current["drawdown"])*100 if previous else None,
            "daily_drawdown_change_basis": "LATEST_ADJCLOSE_SAME_BASIS_PREVIOUS_SESSION" if latest_previous is not None else "STORED_PREVIOUS_SESSION_DISPLAY_ONLY",
            "raw_market_candidate_type": candidate_type, "event_status": status,
            "candidate_confirmed": status == "CONFIRMED"}


def basis_comparison(previous, pairs, touched, significant_pp=1.0, allow_short=False):
    """Two same-basis transitions; old/new mixing stays separately labelled."""
    target = pairs[-1][0]
    old_prices = previous["history_prices"]
    old_current = indicators.calculate([(d, old_prices.get(d,p)) for d,p in pairs], target, allow_short)
    new_previous_prices = dict(old_prices)
    new_previous_prices.update({d:p for d,p in pairs if d <= previous["trading_date"]})
    new_previous = indicators.calculate(sorted(new_previous_prices.items()), previous["trading_date"], allow_short)
    current = indicators.calculate(pairs, target, allow_short)
    old_view = dict(previous, triggered_thresholds=touched)
    new_view = dict(old_view, **new_previous, watch_tier=signals.tier(new_previous["drawdown"]),
                    deepening_anchor=previous.get("deepening_anchor",previous["drawdown"])+new_previous["drawdown"]-previous["drawdown"])
    old_transition = signals.transition(old_view,old_current,significant_pp=significant_pp)
    new_transition = signals.transition(new_view,current,significant_pp=significant_pp)
    return {"old_previous": _metric_view(previous), "old_current": _metric_view(old_current),
            "latest_previous": _metric_view(new_previous), "latest_current": _metric_view(current),
            "old_transition":old_transition,"latest_transition":new_transition,
            "previous_metric_impacts":_impact(previous,new_previous),"current_metric_impacts":_impact(old_current,current),
            "anchor_rebase_is_conditional":True}


def revision_dependencies(previous, pairs, context, candidate_type):
    """Only complete, validated provenance outside both event windows is unrelated.

    Unknown legacy evidence remains blocking. This never changes a review status.
    Deepening also depends on its older confirmation anchor, so stays conservative.
    """
    refs = previous.get("revision_review_event_ids")
    symbol=previous.get("symbol") or previous.get("identity_snapshot",{}).get("symbol")
    inferred={key for key,event in context.items() if event.get("symbol")==symbol and event.get("event_type")=="REVISION_OBSERVATION" and event.get("status")=="PENDING_REVIEW"} if isinstance(context,dict) else set()
    if refs is None:
        refs = sorted(inferred) or (["LEGACY_UNKNOWN"] if previous.get("revision_observation",{}).get("requires_review") else [])
    else:
        refs=sorted(set(refs)|inferred)
    support = set(sorted(previous["history_prices"])[-252:]) | {d for d,p in pairs[-252:]}
    assessments=[]
    for key in refs:
        event = context.get(key) if isinstance(context,dict) else None
        versions = event.get("evidence_versions",[]) if event else []
        dates=set(); valid=bool(versions)
        for version in versions:
            evidence=version.get("evidence",{})
            revision_evidence=evidence.get("revision_observation",{})
            changes=revision_evidence.get("raw_differences",evidence.get("changes"))
            # New evidence explicitly distinguishes price-only uncertainty from
            # source, identity, Close or adjustment-unit risk. Legacy unknowns
            # cannot be silently discharged merely because a date rolled out.
            price_risks={"RELATIVE_REVISION_NOT_PRECISION_CANDIDATE","ROLLING_EXTREMUM_REVISED","PREVIOUS_EXTREMUM_REVISED",
                         "PREVIOUS_TIER_REVISED","COUNTERFACTUAL_EVENT_OR_TIER_DISAGREEMENT","SAME_BASIS_CROSSING_DISAGREEMENT",
                         "THRESHOLD_MARGIN_NOT_GREATER_THAN_REVISION_BOUND","DEEPENING_MARGIN_NOT_GREATER_THAN_REVISION_BOUND",
                         "UNRESOLVED_PRIOR_REVISION_REVIEW"}
            risks=revision_evidence.get("risk_reasons")
            legacy_index_price_only=bool(event and event.get("category")=="Market Indices" and "changes" in evidence and not revision_evidence)
            if not legacy_index_price_only and (not isinstance(risks,list) or not set(risks).issubset(price_risks)):
                valid=False
            if not isinstance(changes,list) or not changes:
                valid=False;continue
            for change in changes:
                try:
                    dt.date.fromisoformat(change["date"])
                    if not _finite_positive(change["previous"]) or not _finite_positive(change["current"]):raise ValueError()
                    dates.add(change["date"])
                except (ValueError,TypeError,KeyError):valid=False
        if event and (event.get("status") != "PENDING_REVIEW" or event.get("event_type") != "REVISION_OBSERVATION"):
            valid=False
        unrelated=valid and bool(dates) and not dates.intersection(support) and candidate_type != "DEEPER_DRAWDOWN"
        assessments.append({"event_id":key,"classification":"PROVEN_OUTSIDE_EVENT_WINDOWS" if unrelated else "RELATED_OR_UNPROVEN",
                            "revision_dates":sorted(dates),"review_status_unchanged":True})
    return assessments


def evaluate(symbol, pairs, closes, identity, previous_state, significant_pp=1.0, *, event_context=None, identity_policy="EQUITY"):
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
        "missing_sessions": missing_sessions(previous["trading_date"],target) if previous else [],
    }
    if previous is None:
        threshold_state["baseline"] = now_levels
        return {
            **depth_semantics(None,metrics,"FIRST_BASELINE","NO_EVENT"),
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
    if identity_policy not in ("EQUITY","INDEX"):
        raise ValueError("UNKNOWN_IDENTITY_POLICY")
    if identity_policy == "INDEX":
        from src.index_data import SYMBOLS as INDEX_SYMBOLS
        same_identity = symbol in INDEX_SYMBOLS and identity == previous.get("identity_snapshot")
    else:
        same_identity = _same_identity(symbol, identity, previous.get("identity_snapshot"))
    if not same_identity:
        reasons.append("IDENTITY_PROVENANCE_MISSING_OR_CHANGED")
    if symbol == "SPCX":
        reasons.append("SPCX_HISTORICAL_ANOMALY_UNVERIFIED")
    if is_new_session:
        days = calendar.sessions_between(dt.date.fromisoformat(previous_date), dt.date.fromisoformat(target))
        if len(days) != 2 or days[0].isoformat() != previous_date or days[1].isoformat() != target:
            reasons.append("NON_CONSECUTIVE_SESSIONS")
    if identity_policy == "INDEX":
        pass  # Index event units and all formulas are explicitly Adj Close only.
    elif not isinstance(old_close, dict) or any(not _finite_positive(old_close.get(date)) or not _finite_positive(closes.get(date)) for date in overlap):
        reasons.append("OVERLAP_CLOSE_EVIDENCE_MISSING")
    elif any(old_close[date] != closes[date] for date in overlap):
        reasons.append("OVERLAP_CLOSE_CHANGED")
    if previous_date not in current_prices or current_prices.get(previous_date) != previous["adjclose"]:
        reasons.append("PREVIOUS_LATEST_ADJCLOSE_CHANGED_OR_MISSING")
    anchor_factor = None
    current_factor = None
    if identity_policy == "INDEX":
        market["close_attribution_policy"] = "INDEX_ADJCLOSE_ONLY; Close retained as raw provenance"
    elif isinstance(old_close, dict) and _finite_positive(old_close.get(previous_date)) and _finite_positive(closes.get(previous_date)) and _finite_positive(closes.get(target)):
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
    basis = basis_comparison(previous,pairs,touched,significant_pp,allow_short=symbol=="SPCX")
    market["same_basis_comparison"] = basis
    market["mixed_basis_event_diagnostic_only"] = proposed["change_event"]
    latest = basis["latest_transition"]
    dependencies=revision_dependencies(previous,pairs,event_context,latest["change_event"])
    market["revision_dependency_assessment"]=dependencies
    if any(d["classification"] != "PROVEN_OUTSIDE_EVENT_WINDOWS" for d in dependencies):
        reasons.append("UNRESOLVED_PRIOR_REVISION_REVIEW")
    market["unrevised_basis_event"] = control["change_event"]
    market["revised_basis_event"] = proposed["change_event"]
    actual_price_move = metrics["adjclose"] != previous_recomputed["adjclose"]
    candidate_levels = sorted(set(control["crossed_thresholds_this_run"]) | set(latest["crossed_thresholds_this_run"])
                              | (set(proposed["crossed_thresholds_this_run"]) if actual_price_move else set()))
    market["old_basis_new_crossings"]=control["crossed_thresholds_this_run"]
    market["latest_basis_new_crossings"]=latest["crossed_thresholds_this_run"]
    market["latest_basis_event"]=latest["change_event"]
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
        if latest["change_event"] != control["change_event"] or latest["crossed_thresholds_this_run"] != control["crossed_thresholds_this_run"]:
            reasons.append("SAME_BASIS_CROSSING_DISAGREEMENT")
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
    revision["risk_reasons"]=list(reasons)
    # A revised old warmup row can change RSI without supporting today's drawdown
    # event. Keep the fact pending if material, but scope its market dependency.
    support=set(sorted(old_prices)[-252:]) | {d for d,p in pairs[-252:]}
    unrelated_current=bool(raw) and all(r["date"] not in support for r in raw) and latest["change_event"] != "DEEPER_DRAWDOWN"
    if unrelated_current:
        reasons[:]=[r for r in reasons if r not in ("RELATIVE_REVISION_NOT_PRECISION_CANDIDATE","THRESHOLD_MARGIN_NOT_GREATER_THAN_REVISION_BOUND")]
        revision["market_dependency"]="PROVEN_OUTSIDE_EVENT_WINDOWS"
    market["threshold_proofs"]={}
    soft={"ROLLING_EXTREMUM_REVISED","PREVIOUS_EXTREMUM_REVISED","PREVIOUS_TIER_REVISED","COUNTERFACTUAL_EVENT_OR_TIER_DISAGREEMENT",
          "SAME_BASIS_CROSSING_DISAGREEMENT","THRESHOLD_MARGIN_NOT_GREATER_THAN_REVISION_BOUND"}
    for level in candidate_levels:
        both=level in control["crossed_thresholds_this_run"] and level in latest["crossed_thresholds_this_run"]
        margin=min(abs(basis[k]["drawdown"]+level/100) for k in ("old_previous","old_current","latest_previous","latest_current"))
        bound=max(abs(metrics["drawdown"]-counterfactual["drawdown"]),max_rel*2) if not unrelated_current else 0.0
        # Preserve the legacy index extremum-review guard. Equity per-level proof
        # can retain an undisputed crossing alongside a contested boundary level.
        blockers=reasons if identity_policy=="INDEX" else [r for r in reasons if r not in soft]
        safe=is_new_session and both and (not raw or unrelated_current or margin>bound) and not blockers
        market["threshold_proofs"][str(level)]={"new_crossing_proven_in_both":both,"minimum_margin":margin,"revision_error_bound":bound,
                                              "blockers":list(blockers),"can_confirm":safe}
    market["comparability_proven"] = not reasons
    market["can_confirm"] = is_new_session and not reasons
    market["candidate_thresholds"] = candidate_levels
    market["crossed_thresholds"] = candidate_levels
    market["significant_deepening"] = proposed["change_event"] == "DEEPER_DRAWDOWN"
    market["recovery"] = proposed["change_event"] == "RECOVERY"
    market["reentry"] = proposed["change_event"] == "REENTRY"
    market["event_type"] = ("NEW_THRESHOLD" if set(candidate_levels)-set(touched) else "REENTRY") if candidate_levels else proposed["change_event"]
    candidates = []
    # Preserve disputed threshold candidates instead of dropping disagreement.
    # A mixed-only candidate needs an actual latest-basis price move and can
    # never be confirmed without proof of a new crossing on BOTH bases.
    has_candidate=bool(candidate_levels) or (proposed["change_event"] != "NO_CHANGE" and (not raw or actual_price_move or control["change_event"]==latest["change_event"]==proposed["change_event"]))
    if is_new_session and has_candidate:
        if candidate_levels:
            for level in candidate_levels:
                candidates.append({"symbol": symbol, "trading_date": target,
                                   "event_type": "THRESHOLD_CROSSING",
                                   "event_subtype": "REENTRY" if level in touched else "NEW_THRESHOLD",
                                   "threshold": level, "status": "CONFIRMED" if market["threshold_proofs"][str(level)]["can_confirm"] else "PENDING_REVIEW",
                                   "rules_version": indicators.RULES_VERSION})
        else:
            candidates.append({"symbol": symbol, "trading_date": target,
                               "event_type": proposed["change_event"],
                               "event_subtype": proposed["change_event"],
                               "threshold": None, "status": "CONFIRMED" if market["can_confirm"] and control["change_event"]==latest["change_event"]==proposed["change_event"] else "PENDING_REVIEW",
                               "rules_version": indicators.RULES_VERSION})
        for candidate in candidates:
            if isinstance(event_context,dict):
                if identity_policy=="INDEX":
                    semantic={"category":"Market Indices", "symbol":symbol,"trading_date":target,"event_type":candidate["event_type"],
                              "threshold":candidate["threshold"],"event_model_version":"indices-revision-market-v2","rules_version":indicators.RULES_VERSION}
                    existing=event_context.get(state.fingerprint(semantic))
                else:
                    existing=event_context.get(state.stable_id(candidate))
                if existing and existing["status"]=="REJECTED":
                    raise ValueError("REOPEN_REQUIRED: existing market decision requires explicit reopening")
                if existing and existing["status"]=="PENDING_REVIEW":candidate["status"]="PENDING_REVIEW"
        statuses={c["status"] for c in candidates}
        market["status"] = next(iter(statuses)) if len(statuses)==1 else "MIXED_CONFIRMED_PENDING"
        market["can_confirm"] = any(c["status"]=="CONFIRMED" for c in candidates)
    elif same_session:
        market["event_type"] = "NO_CHANGE"
    evidence = {"previous_trading_date": previous_date, "previous_adjclose": previous["adjclose"],
                "previous_drawdown": previous["drawdown"], "current_adjclose": metrics["adjclose"],
                "current_drawdown": metrics["drawdown"],
                "old_basis_counterfactual": market["old_basis_counterfactual"],
                "comparability_proven": market["comparability_proven"],
                "comparability_reasons": list(reasons),
                "revision_count": len(raw), "revision_dates": revision["dates"]}
    evidence["same_basis_comparison"]=basis
    evidence["threshold_proofs"]=market["threshold_proofs"]
    evidence["revision_dependency_assessment"]=dependencies
    for candidate in candidates:
        candidate["evidence"] = copy.deepcopy(evidence)
    confirmed_now = sorted(c["threshold"] for c in candidates if c["threshold"] is not None and c["status"]=="CONFIRMED")
    pending_now = sorted(c["threshold"] for c in candidates if c["threshold"] is not None and c["status"]=="PENDING_REVIEW")
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
        anchor = (metrics["drawdown"] if candidates and all(c['status']=='CONFIRMED' for c in candidates) else
                  anchor + previous_recomputed["drawdown"] - previous["drawdown"])
    return {
        **depth_semantics(previous,metrics,market["event_type"],market["status"],previous_recomputed),
        "latest_basis_daily_drawdown_change_pp": (metrics["drawdown"]-previous_recomputed["drawdown"])*100,
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
