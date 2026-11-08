# Market Indices — independent technical observations

Universe: `^GSPC` (S&P 500), `^NDX` (NASDAQ-100), `^SOX` (PHLX Semiconductor).
The equity universe and equity identity rules are unchanged. All new state,
collection evidence and reports live inside `market_indices_trial/`.

Index-owner definitions: [S&P 500](https://www.spglobal.com/spdji/en/indices/equity/sp-500/),
[NDX](https://indexes.nasdaq.com/Index/Overview/NDX),
[SOX](https://indexes.nasdaq.com/Index/Overview/SOX).
Exact Yahoo dissemination identities are `SNP/SNP`, `NIM/Nasdaq GIDS`, and
`NIM/Nasdaq GIDS`, respectively. These are vendor venue labels, not constituent
equity listing exchanges. Identity validation also requires exact symbol/name,
INDEX, USD, and America/New_York. Owner definitions verify intended index identity;
they do not independently authenticate Yahoo's proprietary exchange code mapping.

Prices always use `indicators.adjclose[0].adjclose`. Missing Adj Close is a hard
failure; an independently approved Close-series policy would be required to change
this. Index volume is optional metadata. Actual SOX capture had 501 zero volumes;
both absent and null volume cases are verified offline. Full completed sessions,
weekends, holidays, early closes, invalid prices, duplicates and calendar gaps are
validated using the existing calendar; unfinished bars are excluded before complete
price validation. No short-history exception is available to these indices.

The one authorized live capture is durably claimed at
`market_indices_trial/collection/collection_ledger.json`; it permits only three
serial GETs, at least five seconds between starts, no retries, no proxies, verified
TLS, no redirects, and stop on HTTP429 or 401/403. Raw response SHA256s are checked
again during offline ingestion. Collection cannot be repeated using the same ledger.
No equity request or scheduler is used.

## State and events

```sh
# Explicit initialization only in a new, empty directory:
.venv/bin/python -B -m src.market_indices --init-state
# Offline processing of validated samples:
.venv/bin/python -B -m src.market_indices --input market_indices_trial/validated_indices.json
```

The initial state already exists after acceptance. Do not rerun initialization,
delete the checkpoint or remove the initialization marker. Missing/corrupt state
fails closed. Validation, flock, candidate validation, atomic replacement, fsync and
one prior validated backup protect the isolated state. State and report paths cannot
point outside the index sandbox. Equity loaders reject index state and vice versa.

Category `Market Indices`, schema2, event model `indices-revision-market-v2`.
The existing pure 252-day high/drawdown, full-history Wilder RSI14 and SMA50/200
formulas and tier-transition helper are reused unchanged. Initial baselines record
observed tiers without generating alerts. Confirmed thresholds are backed by
confirmed ledger events. Stable semantic IDs include category, symbol, date, event
type, threshold, rules version and event-model version. Identical replay preserves
state bytes. New evidence versions are retained; pending is sticky, rejected events
with new evidence require explicit reopening. No review decision is made by this
extension, especially for the existing seven equity pending records.

Current metrics always use the latest validated Adj Close. Attribution compares
previous/current sessions on both old and latest history bases, with full metric
impacts retained. Non-extremum micro revisions may coexist with confirmed market
events only after identity, consecutive-date, relative-error and boundary proofs.
Revised extrema, material related revisions, unknown provenance or disputed
crossings remain pending. Disagreement retains meaningful market candidates rather
than discarding them. Index Close-only changes update provenance without determining
Adj-Close events; equity Close and adjustment-factor checks remain stricter.
Pending price-only revisions proven outside both event windows need not block a
new independent threshold, but their review status never changes automatically.
Legacy unknown risks and unproven deepening-anchor dependencies remain fail-closed.
Old confirmed market decisions and semantic event IDs are retained.

`DEEPER_DRAWDOWN` retains the existing cumulative-anchor semantics; index rows also
display daily change on the latest same price basis, whether the day actually
deepened, cumulative anchor depth, raw candidate and confirmation status separately.
The stored-previous comparison remains separately labelled for audit. All events are
technical observations, never direct trading signals.

## Acceptance scope

See `market_indices_trial/acceptance.json` and `acceptance.md`, independent Decimal
reference values, original-system SHA256 preservation, and the AVGO read-only
diagnosis. Synthetic continuity tests are explicitly offline fixtures and do not
establish live cross-day index reliability. No task, deployment, external notification,
trading, equity event-model refactor, or automatic Phase5 promotion is performed.
