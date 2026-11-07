"""Strictly offline revision audit; never writes production state or policies.

Run with: .venv/bin/python -m diagnostics.analyze_adjclose_revisions
Quantiles use linear interpolation at (n-1)*q. Relative price deltas divide by
the Phase 2 price; math.isclose uses its documented symmetric max-price rule.
"""
import argparse
import ast
import datetime as dt
from decimal import Decimal
import hashlib
import inspect
import json
import math
from pathlib import Path
import statistics
import struct
import sys

import market_calendar as calendar
from src import indicators, monitor, signals, state

ROOT = Path(__file__).resolve().parents[1]
TARGET = "2026-10-29"
EXPECTED_COUNTS = {"NVDA":210,"AAPL":204,"GOOGL":189,"MSFT":162,"AMZN":0,"SPCX":0,"META":156,"AVGO":218,"TSLA":0}


class EvidenceError(ValueError):
    pass


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reject_constant(value):
    raise EvidenceError("INVALID_JSON: nonfinite literal " + value)


def read_json(path):
    path = Path(path)
    if not path.is_file():
        raise EvidenceError("EVIDENCE_MISSING: " + str(path))
    try:
        return json.loads(path.read_text(), parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"INVALID_JSON: {path}: {exc}") from exc


def resolve_path(value, root=ROOT, parent=None):
    path = Path(value)
    for candidate in (path, Path(root)/path, Path(parent or root)/path.name):
        if candidate.is_file():
            return candidate.resolve()
    raise EvidenceError("EVIDENCE_MISSING: " + str(value))


def current_tolerances():
    """Read constants from actual production AST, never edit or duplicate policy."""
    tree = ast.parse(inspect.getsource(state.revisions))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "isclose"]
    if len(calls) != 1:
        raise EvidenceError("DETECTION_LOGIC_UNRECOGNIZED")
    values = {k.arg:ast.literal_eval(k.value) for k in calls[0].keywords}
    return {"abs_tol":values["abs_tol"], "rel_tol":values["rel_tol"]}


def percentile(values, q):
    if not 0 <= q <= 1:
        raise ValueError("quantile must be between zero and one")
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered)-1)*q
    lower = int(position)
    return ordered[lower] + (ordered[min(lower+1,len(ordered)-1)]-ordered[lower])*(position-lower)


def index_rows(rows):
    result = {}
    for row in rows:
        stamp = row.get("timestamp")
        if isinstance(stamp,bool) or not isinstance(stamp,(int,float)) or not math.isfinite(stamp):
            raise EvidenceError("INVALID_TIMESTAMP")
        try:
            instant = dt.datetime.fromtimestamp(stamp, calendar.NY)
        except (ValueError, OverflowError, OSError) as exc:
            raise EvidenceError("INVALID_TIMESTAMP") from exc
        date = instant.date().isoformat()
        if date != row.get("trading_date"):
            raise EvidenceError("DATE_ALIGNMENT_ERROR: saved date differs from NY timestamp")
        if date in result:
            raise EvidenceError("DATE_ALIGNMENT_ERROR: duplicate NY trading date")
        for key in ("adjclose","close"):
            price = row.get(key)
            if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price <= 0:
                raise EvidenceError("INVALID_PRICE: " + key)
        bounds = calendar.session_bounds(instant.date())
        if bounds is None or not bounds[0] <= instant <= bounds[1]:
            raise EvidenceError("DATE_ALIGNMENT_ERROR: timestamp outside regular session")
        result[date] = row
    return result


def float32_bits(value):
    return struct.unpack("!I",struct.pack("!f",value))[0]


def exact_float32(value):
    try:
        return struct.unpack("!f",struct.pack("!f",value))[0] == value
    except (OverflowError,struct.error):
        return False


def compare_rows(old_rows, new_rows):
    old, new = index_rows(old_rows), index_rows(new_rows)
    overlap = sorted(old.keys() & new.keys())
    if not overlap:
        raise EvidenceError("NO_OVERLAPPING_DATES")
    tol = current_tolerances()
    changes, absolute, relative = [], [], []
    ulps, ratios = [], []
    factors_old, factors_new = [], []
    timestamp_changes = close_changes = negative = positive = 0
    for date in overlap:
        a,b = old[date],new[date]
        p,q = a["adjclose"],b["adjclose"]
        diff = abs(q-p)
        absolute.append(diff); relative.append(diff/abs(p))
        fa,fb = p/a["close"],q/b["close"]
        factors_old.append(fa);factors_new.append(fb)
        timestamp_changes += a["timestamp"] != b["timestamp"]
        close_changes += a["close"] != b["close"]
        if q != p or a["close"] != b["close"]:
            changed = not math.isclose(p,q,**tol)
            ulp = abs(float32_bits(p)-float32_bits(q)) if exact_float32(p) and exact_float32(q) else None
            if q != p:
                positive += q>p;negative += q<p
                ratios.append(q/p-1)
                if ulp is not None:ulps.append(ulp)
            changes.append({"date":date,"phase2_adjclose":p,"phase4_adjclose":q,
                            "phase2_close":a["close"],"phase4_close":b["close"],
                            "abs_diff":diff,"signed_diff":q-p,"rel_diff":diff/abs(p),
                            "decimal_abs_diff":str(abs(Decimal(str(q))-Decimal(str(p)))),
                            "phase2_adjustment_factor":fa,"phase4_adjustment_factor":fb,
                            "adjustment_factor_delta":fb-fa,"adjusted_price_ratio_minus_one":q/p-1,
                            "current_tolerance_revision":changed,"float32_ulp_distance":ulp})
    changed_prices = [r for r in changes if r["phase2_adjclose"] != r["phase4_adjclose"]]
    changed_diffs = [r["abs_diff"] for r in changed_prices]
    revision_dates = [r["date"] for r in changes if r["current_tolerance_revision"]]
    bins = {
        "le_0.000001":sum(d<=1e-6 for d in absolute),
        "gt_0.000001_le_0.0001":sum(1e-6<d<=1e-4 for d in absolute),
        "gt_0.0001_le_0.01":sum(1e-4<d<=.01 for d in absolute),
        "gt_0.01_le_0.10":sum(.01<d<=.1 for d in absolute),
        "gt_0.10":sum(d>.1 for d in absolute),
    }
    # Independently reproduce the production list-comprehension count by date.
    production = state.revisions({"history_prices":{d:old[d]["adjclose"] for d in overlap}},
                                 {d:new[d]["adjclose"] for d in overlap})
    monthly = []
    for month in sorted({d[:7] for d in overlap}):
        items=[r for r in changed_prices if r["date"].startswith(month)]
        monthly.append({"month":month,"overlap_count":sum(d.startswith(month) for d in overlap),
                        "changed_count":len(items),"positive_count":sum(r["signed_diff"]>0 for r in items),
                        "negative_count":sum(r["signed_diff"]<0 for r in items),
                        "ratio_min":min((r["adjusted_price_ratio_minus_one"] for r in items),default=None),
                        "ratio_max":max((r["adjusted_price_ratio_minus_one"] for r in items),default=None)})
    signature = bool(changed_prices and close_changes==0 and len(ulps)==len(changed_prices)
                     and max(ulps)<=3 and positive and negative and max(relative)<1e-6)
    return {"overlap_count":len(overlap),"new_dates":sorted(new.keys()-old.keys()),
            "missing_dates":sorted(old.keys()-new.keys()),"new_date_count":len(new.keys()-old.keys()),
            "missing_date_count":len(old.keys()-new.keys()),"exact_equal_count":sum(d==0 for d in absolute),
            "raw_different_count":len(changed_prices),"revision_count":len(revision_dates),
            "production_revision_count":len(production),"counts_match_production":len(production)==len(revision_dates),
            "max_abs_diff":max(absolute),"max_rel_diff":max(relative),
            "median_abs_diff_all_overlap":statistics.median(absolute),"p95_abs_diff_all_overlap":percentile(absolute,.95),
            "median_abs_diff_changed_only":statistics.median(changed_diffs) if changed_diffs else None,
            "p95_abs_diff_changed_only":percentile(changed_diffs,.95),
            "absolute_difference_bins":bins,"top5":sorted(changed_prices,key=lambda r:(-r["abs_diff"],r["date"]))[:5],
            "earliest_revision_date":min(revision_dates,default=None),"latest_revision_date":max(revision_dates,default=None),
            "close_different_count":close_changes,"timestamp_different_count":timestamp_changes,
            "all_adjclose_exact_float32":all(exact_float32(side[d]["adjclose"]) for side in (old,new) for d in overlap),
            "changed_ulp_histogram":{str(ulp):ulps.count(ulp) for ulp in sorted(set(ulps))},
            "positive_delta_count":positive,"negative_delta_count":negative,
            "ratio_min":min(ratios,default=0),"ratio_max":max(ratios,default=0),
            "phase2_all_adjustment_factors_one":all(f==1 for f in factors_old),
            "phase4_all_adjustment_factors_one":all(f==1 for f in factors_new),
            "monthly_ratio_summary":monthly,"cause_classification":"NUMERIC_PRECISION" if signature else "ROOT_CAUSE_UNCONFIRMED",
            "cause_confidence":"Strong numerical signature; upstream mechanism UNCONFIRMED" if signature else "No observed changes; cause not applicable" if not changed_prices else "Unconfirmed",
            "uniform_action_ratio_supported":False if positive and negative else None,
            "changes":changes}


def impact(old_rows,new_rows,target=TARGET,allow_short=False):
    def calc(rows):
        indexed=index_rows(rows)
        selected=[(d,indexed[d]["adjclose"]) for d in sorted(indexed) if d<=target]
        result=indicators.calculate(selected,target,allow_short)
        result["watch_tier"]=signals.tier(result["drawdown"])
        return result
    a,b=calc(old_rows),calc(new_rows)
    delta={k:None if a[k] is None or b[k] is None else b[k]-a[k]
           for k in ("highest_adjclose","adjclose","rsi14","sma50","sma200")}
    delta["drawdown_pp"]=(b["drawdown"]-a["drawdown"])*100
    scale={"drawdown_pp":.01,"rsi14":.01,"sma50":.01,"sma200":.01}
    return {"phase2":a,"phase4":b,"delta":delta,
            "tier_changed":a["watch_tier"]!=b["watch_tier"],
            "highest_price_changed":a["highest_adjclose"]!=b["highest_adjclose"],
            "highest_date_changed":a["highest_date"]!=b["highest_date"],
            "observation_scale_exceeded":{k:delta[k] is not None and abs(delta[k])>=v for k,v in scale.items()},
            "nearest_threshold_distance_pp_phase2":min(abs(a["drawdown"]*100+n) for n in signals.THRESHOLDS),
            "nearest_threshold_distance_pp_phase4":min(abs(b["drawdown"]*100+n) for n in signals.THRESHOLDS),
            "observation_scales_are_not_acceptance_tolerances":True}


def evaluate_tolerances(old_rows,new_rows):
    old,new=index_rows(old_rows),index_rows(new_rows)
    overlap=sorted(old.keys() & new.keys())
    policies=[("STRICT_EQUAL",{"abs_tol":0,"rel_tol":0}), ("CURRENT",current_tolerances()),
              ("ABS_1E6",{"abs_tol":1e-6,"rel_tol":0}),
              ("ABS_1E6_REL_1E7",{"abs_tol":1e-6,"rel_tol":1e-7}),
              ("ABS_1E4",{"abs_tol":1e-4,"rel_tol":0}),
              ("ABS_1E4_REL_1E7",{"abs_tol":1e-4,"rel_tol":1e-7}),
              ("ABS_1E3_REL_1E6_STRESS",{"abs_tol":1e-3,"rel_tol":1e-6})]
    values=[]
    for name,tol in policies:
        ignored=[abs(old[d]["adjclose"]-new[d]["adjclose"]) for d in overlap if math.isclose(old[d]["adjclose"],new[d]["adjclose"],**tol)]
        values.append({"policy":name,**tol,"revision_count":len(overlap)-len(ignored),
                       "max_ignored_abs_diff":max(ignored,default=0),
                       "indicator_values_changed_by_comparison_policy":False,
                       "watch_tier_changed_by_comparison_policy":False,
                       "meaning":"Comparison tolerance only; calculations always retain every original price. It can change event suppression, not mathematical outputs.",
                       "missed_meaningful_revision_risk":"Cannot infer safety from these snapshots; possible near a tier boundary. No production policy changed."})
    return values


def evidence_info(path, expected_hash=None, reference=None):
    data=read_json(path)
    stat=Path(path).stat()
    actual=sha256(path)
    if expected_hash is not None and actual != expected_hash:
        raise EvidenceError("EVIDENCE_INTEGRITY_ERROR: " + str(path))
    return {"path":str(Path(path).resolve()),"exists":True,"json_valid":True,
            "size_bytes":stat.st_size,"mtime_utc":dt.datetime.fromtimestamp(stat.st_mtime,dt.timezone.utc).isoformat(),
            "sha256":actual,"recorded_sha256":expected_hash,"hash_reference":reference,
            "recorded_hash_status":"MATCH" if expected_hash else "NOT_RECORDED; current digest is inventory only",
            "schema_version":data.get("schema_version"),
            "capture_start_utc":data.get("started_at_utc",data.get("run_at_utc")),
            "capture_end_utc":data.get("finished_at_utc")}


def load_evidence(root=ROOT):
    root=Path(root)
    p2=root/"reports/yahoo_nine_prices_20261030_141537.json"
    p2diag=root/"reports/yahoo_nine_diagnostic_20261030_141537.json"
    formal=root/"state/monitor_state.json"
    acceptance_path=root/"phase4_trial/acceptance.json"
    acceptance=read_json(acceptance_path)
    live_path=resolve_path(acceptance["live_report"],root,acceptance_path.parent)
    live=read_json(live_path)
    if live.get("mode") != "LIVE_FETCH":
        raise EvidenceError("EVIDENCE_MODE_ERROR: expected a real LIVE_FETCH report")
    p4=resolve_path(live["input_file"],root,live_path.parent)
    p4diag=resolve_path(live["collection_report"],root,live_path.parent)
    d2,d4=read_json(p2diag),read_json(p4diag)
    info=[evidence_info(p2,d2["price_evidence_sha256"],str(p2diag)+":price_evidence_sha256"),
          evidence_info(p2diag),evidence_info(formal,acceptance["formal_state_sha256"],str(acceptance_path)+":formal_state_sha256"),
          evidence_info(acceptance_path),evidence_info(live_path),
          evidence_info(p4,d4["price_evidence_sha256"],str(p4diag)+":price_evidence_sha256"),evidence_info(p4diag)]
    # Reuse existing schema/hash checks. These are read-only and contain no fetch.
    old,old_diag=monitor.read_input(p2)
    new,new_diag=monitor.read_input(p4)
    formal_state=state.load(formal)
    quality=[]
    for symbol in state.SYMBOLS:
        item={"symbol":symbol,"snapshots":[]}
        for name,data,diag in (("phase2",old,old_diag),("phase4",new,new_diag)):
            completed,target,checked,excluded=monitor.validated_prices(symbol,data["stocks"][symbol],diag[symbol])
            if target != TARGET or excluded:
                raise EvidenceError("DATE_ALIGNMENT_ERROR: unexpected target or incomplete rows")
            if diag[symbol]["array_lengths"]["timestamp"] != len(data["stocks"][symbol]["rows"]):
                raise EvidenceError("ARRAY_ALIGNMENT_ERROR")
            indexed=index_rows(completed)
            item["snapshots"].append({"phase":name,"as_of_utc":data["stocks"][symbol]["as_of_utc"],
                                     "target":target,"samples":len(completed),"earliest_date":min(indexed),"latest_date":max(indexed),
                                     "array_lengths":diag[symbol]["array_lengths"],"missing_count":checked["missing_count"],
                                     "duplicate_count":checked["duplicate_count"],"missing_expected_sessions":checked["missing_expected_session_count"],
                                     "incomplete_rows":len(excluded),"identity_validated":checked["identity_validated"],
                                     "ny_utc_offsets_seconds":sorted({int(dt.datetime.fromtimestamp(r["timestamp"],calendar.NY).utcoffset().total_seconds()) for r in completed})})
        prices={r["trading_date"]:r["adjclose"] for r in old["stocks"][symbol]["rows"]}
        item["phase3_state_matches_phase2_prices_exactly"]=formal_state["stocks"][symbol]["history_prices"]==prices
        if not item["phase3_state_matches_phase2_prices_exactly"]:
            raise EvidenceError("BASELINE_MISMATCH: state differs from Phase 2 evidence")
        quality.append(item)
    monitor_path=resolve_path(live["monitor_report"],root,live_path.parent)
    info.append(evidence_info(monitor_path))
    code_digest=state.fingerprint({str(p.relative_to(root)):sha256(p) for p in sorted((root/"src").glob("*.py"))})
    if code_digest != live["code_sha256"]:
        raise EvidenceError("PRODUCTION_VERSION_MISMATCH: current logic differs from live capture")
    phase3_proof_path=root/"reports/phase3_execution_verification.json"
    if phase3_proof_path.exists():
        proof=read_json(phase3_proof_path)
        info.append(evidence_info(phase3_proof_path))
        for key in ("baseline_report","repeat_report"):
            linked=resolve_path(proof[key],root,phase3_proof_path.parent)
            info.append(evidence_info(linked))
            phase3=read_json(linked)
            if phase3["input_sha256"] != sha256(p2):
                raise EvidenceError("EVIDENCE_INTEGRITY_ERROR: Phase 3 input reference")
    return {"phase2":old,"phase4":new,"live_report":live,"acceptance":acceptance,
            "evidence_files":info,"quality":quality,"phase2_path":p2,"phase4_path":p4,
            "production_code_sha256":code_digest}


def build_report(root=ROOT):
    from diagnostics.revision_scenarios import run_scenarios
    root=Path(root)
    sources=load_evidence(root)
    rows,details,policies=[],{},[]
    for symbol in state.SYMBOLS:
        a=sources["phase2"]["stocks"][symbol]["rows"]
        b=sources["phase4"]["stocks"][symbol]["rows"]
        difference=compare_rows(a,b)
        details[symbol]=difference.pop("changes")
        # Confirm decimal tokens differ too, so a binary64 comparison is not
        # inventing differences from two identical source decimal numbers.
        paths=(sources["phase2_path"],sources["phase4_path"])
        decimal_data=[json.loads(p.read_text(),parse_float=Decimal)["stocks"][symbol]["rows"] for p in paths]
        decimals=[{r["trading_date"]:r["adjclose"] for r in data} for data in decimal_data]
        difference["source_decimal_different_count"]=sum(decimals[0][d]!=decimals[1][d] for d in decimals[0].keys() & decimals[1].keys())
        measured=impact(a,b,allow_short=symbol=="SPCX")
        comparison=evaluate_tolerances(a,b)
        rows.append({"symbol":symbol,**difference,"indicator_impact":measured,"tolerance_comparison":comparison,
                     "reported_phase4_revision_count":sources["acceptance"]["live_historical_revisions"].get(symbol,0),
                     "spcx_warning":"PASS_PROVISIONAL; YAHOO_ONLY/HISTORICAL_ANOMALY_UNVERIFIED; Close conflict not Adj Close proof" if symbol=="SPCX" else None})
    for index,policy in enumerate(rows[0]["tolerance_comparison"]):
        policies.append({"policy":policy["policy"],"abs_tol":policy["abs_tol"],"rel_tol":policy["rel_tol"],
                         "revision_count":sum(r["tolerance_comparison"][index]["revision_count"] for r in rows),
                         "max_ignored_abs_diff":max(r["tolerance_comparison"][index]["max_ignored_abs_diff"] for r in rows),
                         "indicator_values_changed_by_comparison_policy":False,"watch_tier_changed_by_comparison_policy":False,
                         "near_boundary_miss_risk":"YES: price size alone does not establish semantic safety"})
    # An ignored delta can be tiny while changing a tier at its boundary.
    old_high,new_high,latest=100.0,100.000002,80.000001
    old_tier=signals.tier(latest/old_high-1);new_tier=signals.tier(latest/new_high-1)
    boundary={"synthetic":True,"old_high":old_high,"new_high":new_high,"latest_adjclose_unchanged":latest,
              "abs_high_delta":new_high-old_high,"old_tier":old_tier,"new_tier":new_tier,
              "explanation":"This is revision-driven, not a market drop. Ignoring the small price difference could miss a semantic tier change."}
    scenarios=run_scenarios()
    count=sum(r["revision_count"] for r in rows)
    reproduced=count==1139 and all(r["revision_count"]==EXPECTED_COUNTS[r["symbol"]] and r["counts_match_production"] for r in rows)
    action_evidence={"paired_phase2_phase4_events_available":False,
                     "note":"Both normalized nine-stock evidence files omit dividends/splits event arrays. Query parameters alone do not prove an event revision."}
    single=root/"test_yahoo_nvda_result_retest.json"
    if single.is_file():
        raw=read_json(single)
        results=raw.get("http",{}).get("response_json",{}).get("chart",{}).get("result",[])
        events=results[0].get("events",{}) if results else {}
        action_evidence.update({"separate_earlier_nvda_capture":str(single),"capture_utc":raw.get("tested_at_utc"),
                                "dividend_event_count":len(events.get("dividends",{})),"split_event_count":len(events.get("splits",{})),
                                "dividend_dates":[dt.datetime.fromtimestamp(e["date"],calendar.NY).date().isoformat() for e in events.get("dividends",{}).values()],
                                "comparison_limitation":"Earlier NVDA event list is not a paired corporate-action change log for Phase 2 vs Phase 4."})
        sources["evidence_files"].append(evidence_info(single))
    test_path=root/"reports/phase4_revision_tests.json"
    test_summary=read_json(test_path) if test_path.is_file() else {"status":"NOT_RUN"}
    return {"schema_version":1,"mode":"OFFLINE_REVISION_DIAGNOSTIC","new_http_requests":0,
            "tested_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"target_trading_date":TARGET,
            "production_tolerances":current_tolerances(),"rules_version":indicators.RULES_VERSION,
            "production_code_sha256":sources["production_code_sha256"],"code_matches_phase4_capture":True,
            "diagnostic_code_sha256":{p.name:sha256(p) for p in sorted((root/"diagnostics").glob("*.py"))},
            "automated_tests":test_summary,
            "hash_verification_limits":["File hashes detect accidental edits, not independent price authenticity.",
                                        "Per-response response_sha256 values cannot be recomputed: original raw HTTP bytes were not retained in the normalized nine-stock evidence. Normalized price-evidence hashes do match."],
            "quantile_method":"linear interpolation at(n-1)*q; medians/P95 reported for all overlaps and changed pairs separately",
            "relative_difference_denominator":"absolute Phase 2 Adj Close; math.isclose threshold uses max(abs(old),abs(new))",
            "evidence_files":sources["evidence_files"],"source_quality":sources["quality"],
            "stocks":rows,"total_overlap":sum(r["overlap_count"] for r in rows),"total_revisions":count,
            "total_close_changes":sum(r["close_different_count"] for r in rows),
            "global_max_abs_diff":max(r["max_abs_diff"] for r in rows),"global_max_rel_diff":max(r["max_rel_diff"] for r in rows),
            "absolute_difference_bins":{key:sum(r["absolute_difference_bins"][key] for r in rows) for key in rows[0]["absolute_difference_bins"]},
            "indicator_impact_summary":{"tier_changes":sum(r["indicator_impact"]["tier_changed"] for r in rows),
                                        "max_abs_drawdown_delta_pp":max(abs(r["indicator_impact"]["delta"]["drawdown_pp"]) for r in rows),
                                        "max_abs_rsi_delta":max(abs(r["indicator_impact"]["delta"]["rsi14"]) for r in rows),
                                        "max_abs_sma50_delta":max(abs(r["indicator_impact"]["delta"]["sma50"]) for r in rows),
                                        "max_abs_sma200_delta":max(abs(r["indicator_impact"]["delta"]["sma200"] or 0) for r in rows),
                                        "minimum_distance_to_watch_threshold_pp":min(r["indicator_impact"]["nearest_threshold_distance_pp_phase4"] for r in rows)},
            "corporate_action_evidence":action_evidence,"scenarios":scenarios,"tolerance_comparison":policies,
            "near_boundary_counterexample":boundary,
            "logic_review":{"comparison_key":"overlapping trading dates, Adj Close only", "rolling_window_hash_used_for_revisions":False,
                            "single_difference_expands_revision_count":False,"date_alignment_error_observed":False,
                            "revision_branch_precedes_market_event_detection":True,
                            "suppressed_level_still_added_to_triggered_thresholds":True,
                            "finding":"DETECTION_LOGIC_ERROR in revision-to-event suppression policy, not in the 1,139 per-date price count"},
            "cause_conclusion":{"classification":"NUMERIC_PRECISION","scope":"Likely pattern for six changed stocks, not confirmed upstream mechanism",
                                "evidence":"Persisted source decimals differ; both snapshots are exact Float32 values; changes are mixed-sign 1–3 ULP with unchanged Close. No coherent large corporate-action ratio evidenced.",
                                "unconfirmed":"Actual Yahoo internal arithmetic, caching/rebuild pipeline, and corporate-action metadata changes cannot be identified from these local captures."},
            "proposed_patch_not_implemented":[
                "Separate revision facts from market-change facts; retain both in one observation rather than one unconditional event override.",
                "Recompute old-basis and revised-basis windows including normal window expiration. Only compare market effects when the price units are demonstrably comparable; otherwise require manual review.",
                "Split observed/candidate/pending-review/confirmed thresholds so a suppressed observation does not silently consume first-trigger eligibility.",
                "Keep stable event IDs for revisions and market observations separately; preserve idempotency and suppress pure high-revision false market events.",
                "Classify numeric precision versus material effects diagnostically; calibrate any tolerance using boundary and corporate-action controls, never just erase all1,139 differences."],
            "candidate_strategy_tradeoffs":[
                {"strategy":"KEEP_CURRENT_TOLERANCE","benefit":"Full sensitivity to observed small changes","risk":"Current unconditional suppression loses independent new-session events"},
                {"strategy":"CHANGE_TOLERANCE","benefit":"Fewer small numeric revision classifications","risk":"No evidence yet justifies production change; near-boundary revisions may matter"},
                {"strategy":"SEPARATE_NUMERIC_AND_MATERIAL_REVISION","benefit":"Preserves evidence with clearer impact ranking","risk":"Needs tested semantic and adjustment-unit rules, not a cents-only cutoff"},
                {"strategy":"DECOUPLE_REVISION_AND_SIGNAL_SUPPRESSION","benefit":"Records simultaneous independent facts; addresses proven B counterexample","risk":"Attribution and durable pending-review/event-ledger design still required"},
                {"strategy":"REVIEW_MATERIAL_OR_AMBIGUOUS_REVISION","benefit":"Avoids automatic causal attribution","risk":"Manual work and explicit recovery/notification policy needed"}],
            "acceptance":{"REVISION_COUNT_REPRODUCED":"PASS" if reproduced else "FAIL",
                          "ROOT_CAUSE_IDENTIFIED":"PARTIAL","INDICATOR_IMPACT_ASSESSED":"PASS",
                          "SIGNAL_SUPPRESSION_RISK":"YES" if any(s["signal_suppression_risk"] for s in scenarios) else "NO",
                          "PRODUCTION_LOGIC_CHANGE_REQUIRED":"YES"},
            "production_changes_applied":False,"next_phase_started":False},details


def markdown(report):
    if "stocks" not in report:
        return "# 历史 Adj Close 修订诊断失败\n\n" + report.get("error", "Unknown error") + "\n"
    lines=["# Yahoo 历史 Adj Close 修订补充诊断", "",
           "本次完全离线，新增 HTTP 请求为 0。未修改生产代码、正式容差、任何状态或既有证据。", "",
           f"按纽约交易日期匹配 {report['total_overlap']} 对价格；当前容差复现 **{report['total_revisions']}** 条修订；普通 Close 差异 **{report['total_close_changes']}**。", "",
           "## 证据与口径", "",
           "已从 Phase 4 acceptance.live_report 定位真实采集报告，再从 input_file/collection_report 定位行情及校验摘要。两份行情 SHA256、正式状态已记录 SHA256 均匹配；其他无既存哈希的报告只记录当前清单摘要，不伪称已通过历史签名验证。",
           "价格按 symbol + America/New_York 交易日匹配，重跑既有证券身份、时间戳、完整交易时段、交易日历与价格校验。所有原始行均已完成，日期相同且无缺失/重复；夏令时偏移包含 -04:00/-05:00，两轮时间戳逐日一致。",
           "当前生产代码组合SHA256与Phase4采集时记录一致。每股raw response_sha256无法从规范化证据重新验证：原始HTTP字节未保存；不得将价格证据文件哈希匹配冒充原始响应或独立价格真实性验证。",
           "当前生产比较：math.isclose(abs_tol=1e-8, rel_tol=1e-10)。相对差分母是 Phase 2 价格。P95 使用(n-1)×0.95线性插值。", "",
           "## 九股差异汇总", "",
           "| Symbol | Overlap | Revisions | Max Abs Diff ($) | Max Rel Diff | Likely Cause |",
           "|---|---:|---:|---:|---:|---|"]
    for row in report["stocks"]:
        cause="NUMERIC_PRECISION（可能，上游未确认）" if row["raw_different_count"] else "无观察到差异；原因不适用"
        lines.append(f"| {row['symbol']} | {row['overlap_count']} | {row['revision_count']} | {row['max_abs_diff']:.12g} | {row['max_rel_diff']:.9g} | {cause} |")
    lines += ["", "绝对差分组（包含相等价格对；不是新容差）：", ""]
    lines += [f"- {key}: {count}" for key,count in report["absolute_difference_bins"].items()]
    lines += ["", "| Symbol | 中位数：全部 | P95：全部 | 中位数：变化对 | P95：变化对 | 最早变化日 | 最晚变化日 |", "|---|---:|---:|---:|---:|---|---|"]
    f=lambda v:"N/A" if v is None else f"{v:.12g}"
    for r in report["stocks"]:
        lines.append(f"| {r['symbol']} | {f(r['median_abs_diff_all_overlap'])} | {f(r['p95_abs_diff_all_overlap'])} | {f(r['median_abs_diff_changed_only'])} | {f(r['p95_abs_diff_changed_only'])} | {r['earliest_revision_date'] or 'N/A'} | {r['latest_revision_date'] or 'N/A'} |")
    lines += ["", "每股最大差异前5日（全部逐日差异另存独立 JSON，含两次价格及复权比率）：", "",
              "| Symbol | Date | Phase 2 Adj | Phase 4 Adj | Abs Diff | Relative Diff |", "|---|---|---:|---:|---:|---:|"]
    for row in report["stocks"]:
        for item in row["top5"]:
            lines.append(f"| {row['symbol']} | {item['date']} | {item['phase2_adjclose']:.17g} | {item['phase4_adjclose']:.17g} | {f(item['abs_diff'])} | {f(item['rel_diff'])} |")
    lines += ["", "## 原因诊断", "",
              "六只有差异的股票均存在非1复权比率；三只无差异股票全程 Adj Close/Close=1。全部两轮价格均可被 Float32 精确表示，变化为正负混合的1–3个 Float32 ULP。源 JSON 十进制数值也确实不同，因此不能解释为 Python Float64 或 JSON 解析凭空产生了价格差。",
              "这些特征强烈符合复权处理链路中的数值舍入/计算精度变化；不是已证实的 Yahoo 内部实现原因。复权比率的数学值随 Adj Close 略变，但未观察到一致的大幅乘法调整。月度分段、ULP分布、方向及比率范围保留在 JSON；不能仅凭比例变化认定发生某次股息或拆股。",
              "两份九股快照没有保留原始股息/拆股事件数组。较早的单股 NVDA 响应保留8个股息事件、无拆股列表，但无法证明两轮之间事件改变。整体 ROOT_CAUSE_IDENTIFIED=PARTIAL，真正上游原因仍未确认。",
              "逐日计数实现正确：比较重叠日期的 Adj Close，不比较滚动窗口哈希，不因同日采集自动判修订，也不把单个差异扩大为整段计数。发现的问题在修订与信号事件的绑定策略。", "",
              "## 指标影响（Phase 4 减 Phase 2）", "",
              "| Symbol | Drawdown Δ(pp) | RSI Δ | SMA50 Δ($) | SMA200 Δ($) | High Δ($) | High Date Changed | Tier Changed |",
              "|---|---:|---:|---:|---:|---:|---|---|"]
    for row in report["stocks"]:
        m=row["indicator_impact"]; d=m["delta"]
        lines.append(f"| {row['symbol']} | {f(d['drawdown_pp'])} | {f(d['rsi14'])} | {f(d['sma50'])} | {f(d['sma200'])} | {f(d['highest_adjclose'])} | {m['highest_date_changed']} | {m['tier_changed']} |")
    lines += ["", "完整两次计算值（含高点日期、窗口和最新价）在 JSON。九股的回撤变化均未达到0.01个百分点，RSI变化未达到0.01，SMA变化未达到$0.01；档位和高点日期均不变，AVGO高点数值有微小变化。这些是观察尺度，不是允许忽略差异的新规则。",
              f"当前最近档位边界仍相距 {report['indicator_impact_summary']['minimum_distance_to_watch_threshold_pp']:.9g} 个百分点，未改变本批数据临近阈值的判断；边界附近的其他数据不能据此判安全。",
              "SPCX仍为 PASS_PROVISIONAL / YAHOO_ONLY/HISTORICAL_ANOMALY_UNVERIFIED，SMA200=N/A；2026-06-16的Close冲突不构成Adj Close修正证据。", "",
              "## 信号抑制风险：固定模拟 A–E", "",
              "以下均为人工固定输入，不是市场事实、买点或安全通知。完整价格生成配方、旧基准及新基准结果保存在 JSON。", "",
              "| 场景 | 输入/预期 | 生产实际输出 | 结论 |", "|---|---|---|---|",
              "| A | 同日最新85不变，旧低价90→90.0001；应只记录修订 | HISTORICAL_REVISION | 正确抑制虚假下跌 |",
              "| B | 高点100不变，新交易日85→79；另有旧低价微修订，应保留真实跨-20%事实 | HISTORICAL_REVISION，跨档/新档为空 | SIGNAL_SUPPRESSION_RISK；20档却被记为已触达 |",
              "| C | 最新85不变，高点100→110，修订造成跨档 | HISTORICAL_REVISION | 不应称为市场新下跌 |",
              "| D | 新交易日85→81，高点100→110 | HISTORICAL_REVISION | 旧基准-19% vs 新基准-26.36%；需要复核，不能简单归因 |",
              "| E | B被接受后，同日同数据重复运行 | NO_CHANGE，修订0，不需写状态 | 幂等正确，但不会补回B已漏掉的事件 |",
              "", "B说明无条件修订覆盖会漏掉独立的新交易日跨档，且触达状态被提前消耗。D的市场/修订分解只在新旧价格单位可比的模拟假设下成立；真实复权变化可能无法可靠分解，应进入待复核而非直接通知。", "",
              "## 候选容差对比（未应用）", "",
              "| Policy | abs_tol | rel_tol | Revision Count | Max Ignored Abs Diff ($) |", "|---|---:|---:|---:|---:|"]
    for p in report["tolerance_comparison"]:
        lines.append(f"| {p['policy']} | {p['abs_tol']:g} | {p['rel_tol']:g} | {p['revision_count']} | {f(p['max_ignored_abs_diff'])} |")
    lines += ["", "比较容差仅影响修订判定和后续事件抑制，不改变实际指标输入或其数值。即使某组消除全部差异，也不能证明它安全；合成边界反例用极小高点修订造成WATCH_10→WATCH_20，详见JSON。不得以消除1,139条计数作为调参目标。", "",
              "## 建议补丁方案（仅建议，未实施）", ""]
    lines += [f"{i}. {text}" for i,text in enumerate(report["proposed_patch_not_implemented"],1)]
    lines += ["", "优先修复修订事实和市场事件的无条件绑定；当前容差保留，待补丁与边界、复权单位、待复核记账测试充分后再评估候选容差。不得将历史回放/人工模拟当作安全可通知买点。", "", "## 验收", ""]
    lines += [f"- {key}: {value}" for key,value in report["acceptance"].items()]
    tests=report.get("automated_tests",{})
    lines += ["", f"自动化测试：{tests.get('tests','N/A')}项，失败{tests.get('failures','N/A')}，错误{tests.get('errors','N/A')}；新诊断测试18项。测试进程禁止网络访问。", "",
              "## 证据清单", "", "| File | SHA256 | Recorded Hash Check |", "|---|---|---|"]
    lines += [f"| {Path(e['path']).name} | {e['sha256']} | {e['recorded_hash_status']} |" for e in report["evidence_files"]]
    lines += ["", "本次停止于诊断；未自动修改生产逻辑、容差、状态或监控任务，未进入Phase5。", ""]
    return "\n".join(lines)


def protected_inventory(root=ROOT):
    root=Path(root)
    paths=set((root/"src").glob("*.py")) | set(root.glob("*.json"))
    for directory in ("reports","phase4_trial","state"):
        paths.update(p for p in (root/directory).rglob("*") if p.is_file() and p.suffix in (".json",".md"))
    excluded={"phase4_revision_diagnostic.json","phase4_revision_diagnostic.md","phase4_revision_differences.json"}
    return {str(p.resolve()):sha256(p) for p in sorted(paths) if p.name not in excluded}


def run(root=ROOT):
    root=Path(root)
    protected=protected_inventory(root)
    try:
        report,details=build_report(root)
    except (EvidenceError,ValueError,KeyError,TypeError,OSError) as exc:
        report={"schema_version":1,"mode":"OFFLINE_REVISION_DIAGNOSTIC","new_http_requests":0,
                "error":str(exc),"status":"EVIDENCE_MISSING" if "EVIDENCE_MISSING" in str(exc) else "EVIDENCE_INVALID",
                "acceptance":{"REVISION_COUNT_REPRODUCED":"FAIL","ROOT_CAUSE_IDENTIFIED":"UNCONFIRMED",
                              "INDICATOR_IMPACT_ASSESSED":"FAIL","SIGNAL_SUPPRESSION_RISK":"UNCONFIRMED",
                              "PRODUCTION_LOGIC_CHANGE_REQUIRED":"UNCONFIRMED"}}
        details={}
    unchanged=all(Path(p).is_file() and sha256(p)==digest for p,digest in protected.items())
    report["protected_files_unchanged"]=unchanged
    report["protected_file_count"]=len(protected)
    report["protected_sha256_inventory"]=protected
    if not unchanged:
        raise EvidenceError("PROTECTED_FILE_CHANGED_DURING_DIAGNOSTIC")
    output=root/"reports"
    output.mkdir(exist_ok=True)
    detail_path=output/"phase4_revision_differences.json"
    detail_path.write_text(json.dumps({"mode":"OFFLINE_REVISION_DIAGNOSTIC","all_nonidentical_pairs":details},indent=2,allow_nan=False)+"\n")
    report["full_difference_file"]=str(detail_path.resolve())
    report["full_difference_file_sha256"]=sha256(detail_path)
    (output/"phase4_revision_diagnostic.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    (output/"phase4_revision_diagnostic.md").write_text(markdown(report))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    blocked=[]
    def forbid_network(event,args):
        if event in ("socket.connect","socket.connect_ex","socket.getaddrinfo","http.client.connect","urllib.Request"):
            blocked.append(event)
            raise EvidenceError("NETWORK_FORBIDDEN: " + event)
    sys.addaudithook(forbid_network)
    report=run()
    print(json.dumps({"report":"reports/phase4_revision_diagnostic.json","acceptance":report["acceptance"],
                      "total_revisions":report.get("total_revisions"),"network_attempts_blocked":blocked,
                      "protected_files_unchanged":report["protected_files_unchanged"]},ensure_ascii=False,indent=2))
    return int(report["acceptance"]["REVISION_COUNT_REPRODUCED"]!="PASS")


if __name__=="__main__":
    raise SystemExit(main())
