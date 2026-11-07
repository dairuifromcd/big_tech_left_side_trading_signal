"""Offline synthetic counterexamples for revision/event handling.

This module calls production calculations without modifying production code,
writing monitor state, or requesting any network data. Counterfactual attribution
is diagnostic only and never constitutes a safe notification or trading signal.
"""

import copy
import datetime as dt

import market_calendar as calendar
import test_yahoo_nine as phase2
from src import indicators, monitor, signals, state


def _base_pairs():
    dates = calendar.sessions_between(dt.date(2025, 10, 1), dt.date(2026, 10, 29))[-253:]
    prices = [90.0] * 252
    # Keep the unique high inside both adjacent rolling windows. Otherwise a
    # 252-day expiration could confound the revision/new-market-price test.
    prices[0], prices[1], prices[-1] = 95.0, 100.0, 85.0
    return [(date.isoformat(), price) for date, price in zip(dates[:252], prices)], dates[-1].isoformat()


def _snapshot(pairs):
    target = dt.date.fromisoformat(pairs[-1][0])
    as_of = (calendar.session_bounds(target)[1] + dt.timedelta(minutes=1)).astimezone(dt.timezone.utc)
    payload = {"chart": {"error": None, "result": [{
        "meta": {"symbol": "NVDA", "longName": "NVIDIA Corporation",
                 "instrumentType": "EQUITY", "exchangeName": "NMS",
                 "fullExchangeName": "NasdaqGS", "currency": "USD",
                 "exchangeTimezoneName": "America/New_York"},
        "timestamp": [int(calendar.session_bounds(dt.date.fromisoformat(date))[0].timestamp()) for date, _ in pairs],
        "indicators": {"adjclose": [{"adjclose": [price for _, price in pairs]}],
                       "quote": [{"close": [price for _, price in pairs]}]},
    }]}}
    diagnostic = phase2.new_row("NVDA", 1)
    evidence = phase2.analyze_payload(diagnostic, payload, as_of)
    diagnostic["http_status"] = 200
    assert diagnostic["data_quality_pass"], diagnostic["errors"]
    return evidence, diagnostic


def _process(pairs, previous=None):
    stock, diagnostic = _snapshot(pairs)
    return monitor.process_symbol("NVDA", stock, diagnostic, previous, 1.0)


def _metrics_subset(observation):
    return {key: observation[key] for key in (
        "trading_date", "adjclose", "highest_adjclose", "highest_date",
        "drawdown", "rsi14", "sma50", "sma200", "watch_tier",
    )}


def _event_subset(observation):
    return {key: observation[key] for key in (
        "change_event", "crossed_thresholds_this_run", "new_thresholds",
        "reentered_thresholds", "triggered_thresholds", "last_new_trigger_date",
        "historical_revision_count", "historical_revision_examples",
    )}


def _counterfactual(previous_pairs, new_pairs):
    """Carry new observed Adj Close onto old overlapping prices, conditional on
    equal units. This is a diagnostic scenario, not a causal adjustment proof.
    """
    old = dict(previous_pairs)
    old_basis = [(date, old.get(date, price)) for date, price in new_pairs]
    result = indicators.calculate(old_basis, old_basis[-1][0])
    return {"drawdown": result["drawdown"], "watch_tier": signals.tier(result["drawdown"]),
            "highest_adjclose": result["highest_adjclose"], "latest_adjclose": result["adjclose"],
            "assumption": "New observed Adj Close is comparable in units to the old history; not generally established for real adjustment revisions."}


def _case(name, description, pairs, base_pairs, previous_observation, previous_state,
          expectation, assessment, suppression_risk=False, requires_review=False):
    observation, updated = _process(pairs, previous_state)
    market_only = _counterfactual(base_pairs, pairs)
    result = {
        "scenario": name, "synthetic": True, "symbol": "NVDA",
        "description": description, "expectation": expectation,
        "inputs": {"previous_session": base_pairs[-1][0], "current_session": pairs[-1][0],
                   "previous_latest_adjclose": base_pairs[-1][1], "current_latest_adjclose": pairs[-1][1],
                   "previous_samples": len(base_pairs), "current_samples": len(pairs),
                   "changed_overlap_dates": state.revisions(previous_state, dict(pairs))},
        "previous_metrics": _metrics_subset(previous_observation),
        "old_basis_counterfactual": market_only,
        "revised_basis_metrics": _metrics_subset(observation),
        "actual_production_result": _event_subset(observation),
        "diagnostic_assessment": assessment,
        "signal_suppression_risk": suppression_risk,
        "requires_review": requires_review,
        "safe_to_notify_as_buy_signal": False,
    }
    return result, observation, updated


def run_scenarios():
    """Return JSON-safe A--E cases under unchanged production rules."""
    base, new_date = _base_pairs()
    baseline, previous = _process(base)
    recipe = {"synthetic": True, "all_prices_are_adjclose": True,
              "session_start": base[0][0], "session_end": base[-1][0],
              "date_source": "252 consecutive calendar sessions ending before 2026-10-29",
              "default_price": 90.0,
              "exceptions_zero_based": {"0": 95.0, "1": 100.0, "251": 85.0},
              "revision_index": 10, "tiny_revision_from": 90.0, "tiny_revision_to": 90.0001,
              "note": "All timestamps are regular session opens; evaluated one minute after close. Close is synthetic and equal to Adj Close, but never used in indicator formulas."}
    results = []

    a_prices = copy.deepcopy(base)
    a_prices[10] = (a_prices[10][0], 90.0001)
    a, _, _ = _case("A", "Only an older low is microscopically revised; same latest date and price.",
                     a_prices, base, baseline, previous,
                     "Record revision without a new market-drop event.",
                     "EXPECTED_REVISION_ONLY")
    assert a["actual_production_result"]["change_event"] == "HISTORICAL_REVISION"
    assert a["actual_production_result"]["new_thresholds"] == []
    results.append(a)

    b_prices = a_prices + [(new_date, 79.0)]
    b, b_observation, b_state = _case("B", "Tiny old-low revision plus a new session falling from85 to79; unchanged100 high. Legacy fixture also changes old Close, requiring review in v2.",
                     b_prices, base, baseline, previous,
                     "Preserve separate revision evidence and market-only -20% crossing; never blindly treat it as a safe buy signal.",
                     "MARKET_CANDIDATE_PRESERVED_PENDING_REVIEW", suppression_risk=False, requires_review=True)
    b["unrevised_control_event"] = signals.transition(previous, indicators.calculate(base + [(new_date, 79.0)], new_date))["change_event"]
    b["suppressed_threshold_marked_triggered"] = 20 in b_state["triggered_thresholds"]
    assert b["unrevised_control_event"] == "NEW_THRESHOLD"
    assert b["old_basis_counterfactual"]["watch_tier"] == "WATCH_20"
    b["market_observation"] = b_observation["market_observation"]
    b["revision_observation"] = b_observation["revision_observation"]
    b["candidate_threshold_preserved"] = 20 in b_observation["market_observation"]["candidate_thresholds"]
    assert b["actual_production_result"]["change_event"] == "PENDING_REVIEW"
    assert b["actual_production_result"]["crossed_thresholds_this_run"] == []
    assert not b["suppressed_threshold_marked_triggered"]
    assert b["candidate_threshold_preserved"]
    results.append(b)

    c_prices = copy.deepcopy(base)
    c_prices[1] = (c_prices[1][0], 110.0)
    c, _, _ = _case("C", "Only historical high changes from100 to110; latest85 and date unchanged.",
                     c_prices, base, baseline, previous,
                     "High-driven -20% crossing must not be emitted as a fresh market decline.",
                     "EXPECTED_REVISION_DRIVEN_TIER_CHANGE")
    assert c["old_basis_counterfactual"]["watch_tier"] == "WATCH_10"
    assert c["revised_basis_metrics"]["watch_tier"] == "WATCH_20"
    assert c["actual_production_result"]["change_event"] == "HISTORICAL_REVISION"
    results.append(c)

    d_prices = c_prices + [(new_date, 81.0)]
    d, _, _ = _case("D", "New session85->81 plus historical high100->110. Old and revised bases disagree on -20% crossing.",
                     d_prices, base, baseline, previous,
                     "Report both bases and require review; attribution is conditional because real adjustment revisions can alter units.",
                     "MIXED_REVISION_AND_MARKET_MOVE_REQUIRES_REVIEW", requires_review=True)
    d["conditional_market_effect_pp"] = (d["old_basis_counterfactual"]["drawdown"] - baseline["drawdown"]) * 100
    d["conditional_revision_effect_pp"] = (d["revised_basis_metrics"]["drawdown"] - d["old_basis_counterfactual"]["drawdown"]) * 100
    d["causal_attribution_confirmed"] = False
    assert d["old_basis_counterfactual"]["watch_tier"] == "WATCH_10"
    assert d["revised_basis_metrics"]["watch_tier"] == "WATCH_20"
    assert d["actual_production_result"]["change_event"] == "PENDING_REVIEW"
    results.append(d)

    e_observation, e_updated = _process(b_prices, b_state)
    revisions = state.revisions(b_state, dict(b_prices))
    would_write = (e_observation["change_event"] != "NO_CHANGE"
                   or e_updated["history_fingerprint"] != b_state["history_fingerprint"])
    e = {"scenario": "E", "synthetic": True, "symbol": "NVDA",
         "description": "Repeat exactly the same B snapshot after accepting its revised state; no file writes performed.",
         "inputs": {"snapshot_from_scenario": "B", "current_session": b_prices[-1][0],
                    "latest_adjclose": b_prices[-1][1], "samples": len(b_prices)},
         "expectation": "NO_CHANGE, no repeated revision or market event, monitor would not rewrite state.",
         "actual_production_result": _event_subset(e_observation),
         "overlap_revision_count": len(revisions),
         "history_fingerprint_equal": e_updated["history_fingerprint"] == b_state["history_fingerprint"],
         "production_monitor_would_write_state": would_write,
         "diagnostic_assessment": "IDEMPOTENT_SAME_SNAPSHOT",
         "signal_suppression_risk": False, "requires_review": False,
         "safe_to_notify_as_buy_signal": False}
    assert e_observation["change_event"] == "NO_CHANGE"
    assert not revisions and not would_write
    results.append(e)

    for result in results:
        result["fixture_recipe"] = recipe
        result["production_logic_modified"] = False
    return results


if __name__ == "__main__":
    import json
    print(json.dumps(run_scenarios(), ensure_ascii=False, indent=2, allow_nan=False))
